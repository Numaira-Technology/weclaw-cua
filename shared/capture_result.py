"""Structured capture outcome that remains list-compatible for existing callers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CaptureFailure:
    chat_name: str
    stage: str
    error: str


class CaptureRunResult(list[str]):
    """Successful JSON paths plus failures collected during one capture run."""

    def __init__(self, paths=()) -> None:
        super().__init__(paths)
        self.failures: list[CaptureFailure] = []

    def add_failure(self, chat_name: str, error: str, *, stage: str = "capture") -> None:
        failure = CaptureFailure(
            chat_name=str(chat_name or "unknown"),
            stage=str(stage or "capture"),
            error=str(error or "unknown error"),
        )
        if failure not in self.failures:
            self.failures.append(failure)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def status(self) -> str:
        if self.ok:
            return "ok"
        return "partial" if self else "failed"

    def failure_dicts(self) -> list[dict]:
        return [asdict(failure) for failure in self.failures]


def record_capture_failure(
    result: list[str],
    chat_name: str,
    error: str,
    *,
    stage: str = "capture",
) -> None:
    add_failure = getattr(result, "add_failure", None)
    if callable(add_failure):
        add_failure(chat_name, error, stage=stage)


def capture_failures(result: list[str]) -> list[dict]:
    failure_dicts = getattr(result, "failure_dicts", None)
    if callable(failure_dicts):
        return failure_dicts()
    return []


def capture_status(result: list[str]) -> str:
    status = getattr(result, "status", None)
    if isinstance(status, str):
        return status
    return "ok"
