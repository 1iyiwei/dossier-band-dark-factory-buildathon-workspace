"""The error type every layer raises; the HTTP layer turns it into the spec's error body."""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ")


def validation_failed(message: str) -> ApiError:
    return ApiError(422, "validation_failed", message)


def malformed(message: str) -> ApiError:
    return ApiError(400, "malformed_request", message)
