import pytest
from mlops_common.schemas import PythonRuntime
from pydantic import ValidationError


@pytest.mark.parametrize(
    "path", ["../../var/lib/x", "/etc/passwd", "a/../b", "a\\b", "a\x00b", "a//b"]
)
def test_requirements_file_must_be_a_safe_relative_path(path):
    with pytest.raises(ValidationError):
        PythonRuntime(requirements_file=path, command=["python", "x.py"])


def test_safe_requirements_file_is_accepted():
    runtime = PythonRuntime(requirements_file="reqs/dev.txt", command=["python", "x.py"])
    assert runtime.requirements_file == "reqs/dev.txt"


@pytest.mark.parametrize("entry", ["-r /etc/passwd", "--index-url http://x", "-e .", "numpy\nrich"])
def test_requirements_entries_cannot_be_pip_options_or_multiline(entry):
    with pytest.raises(ValidationError):
        PythonRuntime(requirements=[entry], command=["python", "x.py"])


def test_plain_requirement_specifiers_are_accepted():
    runtime = PythonRuntime(requirements=["numpy==1.26.4", "torch>=2"], command=["python", "x.py"])
    assert runtime.requirements == ["numpy==1.26.4", "torch>=2"]
