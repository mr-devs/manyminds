"""Errors raised by the model layer."""

from manyminds.core.models import ErrorKind


class ModelError(Exception):
    """A model call failed in a way we can name. The message is safe to show the user."""

    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
