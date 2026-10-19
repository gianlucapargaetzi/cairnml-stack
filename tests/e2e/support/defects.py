"""What an expected failure (a known defect) may raise.

A test marked as a known defect is expected to fail on the defect itself: an assertion that does not hold, a wait
that times out, or a test that reports the failure with pytest.fail. Any other exception (a stack that does not start,
a sign-in that breaks, a setup error) is an error of the suite, and is reported as one, not as the known defect.
"""

import pytest

DEFECT_FAILURES = (AssertionError, TimeoutError, pytest.fail.Exception)
