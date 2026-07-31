"""Keep machine-readable stdout clean while sending operational logs to stderr."""

from contextlib import contextmanager, redirect_stdout
import sys


@contextmanager
def progress_to_stderr():
    target = sys.stderr
    try:
        with redirect_stdout(target):
            yield
    finally:
        target.flush()
