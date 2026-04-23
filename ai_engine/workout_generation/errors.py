from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class WorkoutGenerationError:
    """
    Structured error payload for logging/UI/debugging.

    This is intentionally small: avoid dumping full LLM responses into DB.
    """

    kind: str
    message: str
    details: Optional[dict[str, Any]] = None


class WorkoutGenerationException(Exception):
    """
    Raised for unrecoverable generation failures.
    """

    def __init__(self, err: WorkoutGenerationError):
        super().__init__(f"{err.kind}: {err.message}")
        self.err = err


class OpenAIRequestException(WorkoutGenerationException):
    pass


class OpenAIResponseParseException(WorkoutGenerationException):
    pass


class WorkoutValidationException(WorkoutGenerationException):
    pass

