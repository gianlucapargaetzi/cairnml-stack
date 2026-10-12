import logging as _logging

__version__ = "0.1.0"

# SDK warnings must never reach the user's stderr, the stdout/stderr tees (which would
# send them to the server as run logs) or a root handler, so the logger is isolated.
_sdk_log = _logging.getLogger("mlops")
_sdk_log.addHandler(_logging.NullHandler())
_sdk_log.propagate = False

from mlops.experiment import Experiment, ExperimentError, current_experiment, init  # noqa: E402

__all__ = ["Experiment", "ExperimentError", "current_experiment", "init", "__version__"]
