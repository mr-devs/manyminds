"""Errors raised by the model layer."""

from manyminds.core.models import ErrorKind


class ModelError(Exception):
    """A model call failed in a way we can name. The message is safe to show the user."""

    def __init__(self, kind: ErrorKind, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after
        """Seconds the server asked us to wait before trying again, when it said."""
