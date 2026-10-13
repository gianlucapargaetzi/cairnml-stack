from __future__ import annotations

from mlops_agent.config import AgentSettings
from mlops_agent.executors.base import BaseExecutor


def make_executor(kind: str, client, settings: AgentSettings) -> BaseExecutor:
    if kind == "python":
        from mlops_agent.executors.python import PythonExecutor

        return PythonExecutor(client)
    if kind == "image":
        from mlops_agent.executors.image import ImageExecutor

        return ImageExecutor(client, settings)
    if kind == "compose":
        from mlops_agent.executors.compose import ComposeExecutor

        return ComposeExecutor()
    raise ValueError(f"unsupported runtime {kind!r}")
