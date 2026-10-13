"""The explorer filter language: a Python-like expression, parsed with `ast`, checked against a
whitelist, and translated to SQL. The expression is never executed; every literal reaches the
database as a bound parameter.

Examples:
    run.name == 'baseline' and run.hparams.lr > 0.01
    run.archived == False or run.status in ['running']     (not a valid mix: see below)
    any(t.name in ['vision'] for t in run.tags)
    metric.name == 'loss' and metric.context.subset == 'val'   (search/metric only)

Run and metric clauses cannot be joined by `or` or `not`, because they filter different rows.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from mlops_common.schemas import TERMINAL_STATUSES
from sqlalchemy import Float, and_, case, cast, false, func, not_, or_, select, true
from sqlalchemy.sql.elements import ColumnElement

from mlops_server.models import Experiment, MetricSeries, Project, Run, RunTag, Tag

MAX_LENGTH = 2000
DEFAULT_EXPERIMENT = "general"
RUN_NAMESPACE = "run"
METRIC_NAMESPACE = "metric"
SEQUENCE_NAMESPACES = {"images", "audios", "texts", "figures", "distributions"}
# Fields of a run that are not parameters. Any other `run.<key>` reads the run's params.
RUN_FIELDS = {"name", "hash", "id", "experiment", "project", "active", "archived", "creation_time"}
# Operators allowed per kind of value.
TEXT_OPS = {ast.Eq, ast.NotEq, ast.In, ast.NotIn, ast.Lt, ast.LtE, ast.Gt, ast.GtE}
EQUALITY_OPS = {ast.Eq, ast.NotEq, ast.In, ast.NotIn}
ORDER_OPS = {ast.Lt, ast.LtE, ast.Gt, ast.GtE}
BOOL_OPS = {ast.Eq, ast.NotEq}
COMPARE_SYMBOL = {
    ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
    ast.In: "in", ast.NotIn: "not in",
}


class FilterError(ValueError):
    """The filter is not valid. The message says why, and is shown to the user."""


@dataclass(frozen=True)
class Compiled:
    """SQL for the two row kinds a filter can select: runs, and metric series."""

    run: ColumnElement | None = None
    metric: ColumnElement | None = None


def compile_filter(text: str | None) -> Compiled:
    if text is None or not text.strip():
        return Compiled()
    if len(text) > MAX_LENGTH:
        raise FilterError(f"the filter is longer than {MAX_LENGTH} characters")
    try:
        tree = ast.parse(text.strip(), mode="eval").body
    except (SyntaxError, RecursionError, ValueError):
        raise FilterError("the filter is not a valid expression") from None
    run_parts, metric_parts = [], []
    for part in _top_level_and(tree):
        namespace = _namespace(part)
        expr = _Translator(namespace).boolean(part)
        (run_parts if namespace == RUN_NAMESPACE else metric_parts).append(expr)
    return Compiled(
        run=and_(*run_parts) if run_parts else None,
        metric=and_(*metric_parts) if metric_parts else None,
    )


def _top_level_and(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return [leaf for value in node.values for leaf in _top_level_and(value)]
    return [node]


def _namespace(node: ast.expr) -> str:
    """The one namespace a clause uses. A clause that mixes run and metric is refused."""
    namespaces = _namespaces(node)
    if len(namespaces) != 1:
        raise FilterError(
            "run and metric clauses cannot be combined with 'or' or 'not'; "
            "join them with 'and'"
        )
    return namespaces.pop()


def _namespaces(node: ast.expr) -> set[str]:
    if isinstance(node, ast.BoolOp):
        return set().union(*(_namespaces(value) for value in node.values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _namespaces(node.operand)
    if isinstance(node, ast.Compare):
        _check_compare(node)
        return {_leaf_namespace(node.left)}
    if isinstance(node, ast.Call):
        if _is_any(node):
            return {RUN_NAMESPACE}
        if isinstance(node.func, ast.Attribute) and node.func.attr == "startswith":
            return {_leaf_namespace(node.func.value)}
        raise FilterError("only startswith() and any(... for t in run.tags) are allowed as calls")
    if isinstance(node, ast.Attribute):
        return {_leaf_namespace(node)}
    raise FilterError(f"{type(node).__name__} is not allowed in a filter")


def _check_compare(node: ast.Compare) -> None:
    if len(node.ops) != 1:
        raise FilterError("chained comparisons are not supported; join them with 'and'")
    if not isinstance(node.left, ast.Attribute | ast.Name):
        raise FilterError("the left side of a comparison must be a field such as run.name")


def _leaf_namespace(node: ast.expr) -> str:
    path = _path(node)
    head = path[0]
    if head == RUN_NAMESPACE:
        return RUN_NAMESPACE
    if head == METRIC_NAMESPACE:
        return METRIC_NAMESPACE
    if head in SEQUENCE_NAMESPACES:
        raise FilterError(f"{head}.* filters are not supported yet (sequences arrive in Phase 5)")
    raise FilterError(f"unknown name {head!r}; use run.* or metric.*")


def _path(node: ast.expr) -> list[str]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        raise FilterError("only names and attributes such as run.name may be used")
    parts.append(node.id)
    return list(reversed(parts))


def _is_any(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "any"
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.GeneratorExp)
    )


def _literal(node: ast.expr) -> Any:
    """A constant, a negative number, or a list or tuple of them."""
    if isinstance(node, ast.Constant) and (
        node.value is None or isinstance(node.value, str | int | float | bool)
    ):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal(node.operand)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return -value
    if isinstance(node, ast.List | ast.Tuple):
        return [_literal(element) for element in node.elts]
    raise FilterError("values must be strings, numbers, booleans, None, or lists of them")


class _Translator:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def boolean(self, node: ast.expr) -> ColumnElement:
        if isinstance(node, ast.BoolOp):
            parts = [self.boolean(value) for value in node.values]
            return and_(*parts) if isinstance(node.op, ast.And) else or_(*parts)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not_(self.boolean(node.operand))
        if isinstance(node, ast.Compare):
            return self.compare(node)
        if isinstance(node, ast.Call):
            if _is_any(node):
                return self.any_tag(node)
            return self.startswith(node)
        if isinstance(node, ast.Attribute):
            # A bare boolean field, such as run.archived, means "== True".
            as_compare = ast.Compare(
                left=node, ops=[ast.Eq()], comparators=[ast.Constant(True)]
            )
            return self.compare(as_compare)
        raise FilterError(f"{type(node).__name__} is not allowed in a filter")

    # ----- comparisons -----
    def compare(self, node: ast.Compare) -> ColumnElement:
        _check_compare(node)
        op = type(node.ops[0])
        if op not in COMPARE_SYMBOL:
            raise FilterError("only ==, !=, <, <=, >, >=, in and not in are allowed")
        return self.field(_path(node.left), op, _literal(node.comparators[0]))

    def startswith(self, node: ast.Call) -> ColumnElement:
        if not (isinstance(node.func, ast.Attribute) and len(node.args) == 1):
            raise FilterError("startswith() takes one string")
        value = _literal(node.args[0])
        if not isinstance(value, str):
            raise FilterError("startswith() takes a string")
        return self.text_column(_path(node.func.value)).startswith(value, autoescape=True)

    def any_tag(self, node: ast.Call) -> ColumnElement:
        gen = node.args[0]
        if len(gen.generators) != 1 or gen.generators[0].ifs or gen.generators[0].is_async:
            raise FilterError("any() takes one 'for t in run.tags' with no conditions")
        comp = gen.generators[0]
        if not (isinstance(comp.target, ast.Name) and _path(comp.iter) == [RUN_NAMESPACE, "tags"]):
            raise FilterError("any() must iterate over run.tags")
        variable = comp.target.id
        if not (isinstance(gen.elt, ast.Compare) and len(gen.elt.ops) == 1):
            raise FilterError("inside any(), write one comparison such as t.name in ['vision']")
        left = _path(gen.elt.left)
        if left != [variable, "name"]:
            raise FilterError(f"inside any(), compare {variable}.name")
        op = type(gen.elt.ops[0])
        if op not in EQUALITY_OPS:
            raise FilterError("tag names take ==, !=, in or not in")
        value = _literal(gen.elt.comparators[0])
        if op in (ast.In, ast.NotIn):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise FilterError("'in' takes a list of strings")
            names = Tag.name.in_(value)
        else:
            if not isinstance(value, str):
                raise FilterError("tag names are strings")
            names = Tag.name == value
        if op in (ast.NotEq, ast.NotIn):
            names = not_(names)
        tagged = select(RunTag.run_id).join(Tag, Tag.id == RunTag.tag_id).where(names)
        return Run.id.in_(tagged)

    # ----- fields -----
    def field(self, path: list[str], op: type, value: Any) -> ColumnElement:
        head, rest = path[0], path[1:]
        if self.namespace == METRIC_NAMESPACE:
            return self.metric_field(rest, op, value)
        if head != RUN_NAMESPACE or not rest:
            raise FilterError(f"{'.'.join(path)} is not a run field")
        key = rest[0]
        if key == "tags":
            raise FilterError("tags are compared inside any(t.name in [...] for t in run.tags)")
        if key in RUN_FIELDS and len(rest) == 1:
            return self.run_field(key, op, value)
        if key in RUN_FIELDS:
            raise FilterError(f"{'.'.join(path)}: {key} has no attributes")
        return self.param(rest, op, value)

    def text_column(self, path: list[str]) -> ColumnElement:
        """The text a startswith() reads: a run text field, a parameter, or a metric name."""
        if self.namespace == METRIC_NAMESPACE or path[0] == METRIC_NAMESPACE:
            return _metric_text_column(path[1:])
        if path[0] != RUN_NAMESPACE or len(path) < 2:
            raise FilterError(f"{'.'.join(path)} is not a text field")
        if path[1] in _RUN_TEXT_COLUMNS and len(path) == 2:
            return _RUN_TEXT_COLUMNS[path[1]]()
        if path[1] in RUN_FIELDS:
            raise FilterError(f"{'.'.join(path)} is not a text field")
        return Run.params[tuple(path[1:])].as_string()

    def run_field(self, key: str, op: type, value: Any) -> ColumnElement:
        if key in _RUN_TEXT_COLUMNS:
            return _text_compare(_RUN_TEXT_COLUMNS[key](), op, value)
        if key == "active":
            return _bool_compare(Run.status.notin_(sorted(TERMINAL_STATUSES)), op, value)
        if key == "archived":
            return _bool_compare(Run.archived, op, value)
        # creation_time is seconds since the epoch.
        if op not in ORDER_OPS | EQUALITY_OPS or not _is_number(value):
            raise FilterError("creation_time compares with a number of seconds since 1970")
        return _number_compare(func.extract("epoch", Run.created_at), op, value)

    def param(self, path: list[str], op: type, value: Any) -> ColumnElement:
        json_value = Run.params[tuple(path)]
        text = json_value.as_string()
        if value is None:
            if op not in EQUALITY_OPS - {ast.In, ast.NotIn}:
                raise FilterError("None only takes == or !=")
            return text.is_(None) if op is ast.Eq else text.isnot(None)
        if isinstance(value, bool):
            return _text_compare(text, op, "true" if value else "false", bool_only=True)
        if isinstance(value, str):
            return _text_compare(text, op, value)
        if _is_number(value):
            return _number_compare(_as_number(json_value), op, value)
        if isinstance(value, list):
            if not value or op not in (ast.In, ast.NotIn):
                raise FilterError("lists take 'in' or 'not in' and must not be empty")
            if all(isinstance(v, str) for v in value):
                return _text_compare(text, op, value)
            if all(_is_number(v) for v in value):
                return _number_compare(_as_number(json_value), op, value)
            raise FilterError("a list must hold only strings or only numbers")
        raise FilterError("unsupported value")

    def metric_field(self, rest: list[str], op: type, value: Any) -> ColumnElement:
        column = _metric_text_column(rest)
        if not (isinstance(value, str) or (isinstance(value, list) and all(
            isinstance(v, str) for v in value
        ))):
            raise FilterError("metric names and contexts compare with strings")
        return _text_compare(column, op, value)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _as_number(json_value) -> ColumnElement:
    """The JSON value as a float, or NULL when it is not a JSON number. Non-numbers never
    reach the cast, so a string param cannot make the query fail."""
    return case(
        (func.json_typeof(json_value) == "number", cast(json_value.as_string(), Float)),
        else_=None,
    )


def _text_compare(column, op: type, value, bool_only: bool = False) -> ColumnElement:
    if bool_only and op not in BOOL_OPS:
        raise FilterError("booleans take == or !=")
    if isinstance(value, bool) and not bool_only:
        raise FilterError("this field compares with strings or numbers, not booleans")
    if op in (ast.In, ast.NotIn):
        if not isinstance(value, list):
            raise FilterError("'in' takes a list")
        expr = column.in_(value)
        return not_(expr) if op is ast.NotIn else expr
    if isinstance(value, list):
        raise FilterError("only 'in' and 'not in' take a list")
    if op not in TEXT_OPS:
        raise FilterError("this field compares with ==, !=, <, <=, >, >=, in or not in")
    return _compare_with(column, op, value)


def _number_compare(column, op: type, value) -> ColumnElement:
    # Numbers bind as floats: an integer literal would be sent as a 32-bit INTEGER, which
    # overflows against epoch seconds and large parameter values.
    if op in (ast.In, ast.NotIn):
        if not isinstance(value, list):
            raise FilterError("'in' takes a list")
        expr = column.in_([float(v) for v in value])
        return not_(expr) if op is ast.NotIn else expr
    if isinstance(value, list):
        raise FilterError("lists take 'in' or 'not in'")
    return _compare_with(column, op, float(value))


_RUN_TEXT_COLUMNS = {
    "name": lambda: Run.name,
    "hash": lambda: Run.id,
    "id": lambda: Run.id,
    "experiment": lambda: func.coalesce(
        select(Experiment.name).where(Experiment.id == Run.experiment_id).scalar_subquery(),
        DEFAULT_EXPERIMENT,
    ),
    "project": lambda: select(Project.slug).where(Project.id == Run.project_id).scalar_subquery(),
}


def _metric_text_column(rest: list[str]) -> ColumnElement:
    if rest == ["name"]:
        return MetricSeries.name
    if len(rest) == 2 and rest[0] == "context":
        return MetricSeries.context[rest[1]].astext
    if rest == ["last"]:
        raise FilterError("metric.last is not supported yet")
    raise FilterError(f"metric.{'.'.join(rest)} is not a metric field")


def _bool_compare(column, op: type, value) -> ColumnElement:
    if not isinstance(value, bool) or op not in BOOL_OPS:
        raise FilterError("this field takes == True or == False")
    if op is ast.Eq:
        return column.is_(true()) if value else column.is_(false())
    return column.is_(false()) if value else column.is_(true())


def _compare_with(column, op: type, value) -> ColumnElement:
    if op is ast.Eq:
        return column == value
    if op is ast.NotEq:
        return column != value
    if op is ast.Lt:
        return column < value
    if op is ast.LtE:
        return column <= value
    if op is ast.Gt:
        return column > value
    if op is ast.GtE:
        return column >= value
    raise FilterError("unsupported comparison")
