"""
Custom API error hierarchy.
"""

from __future__ import annotations


class LucyCodeAPIError(Exception):
    """Base class for all API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(LucyCodeAPIError):
    """Invalid or missing API key."""

    def __init__(self, message: str = "Invalid API key") -> None:
        super().__init__(message, status_code=401)


class RateLimitError(LucyCodeAPIError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class OverloadedError(LucyCodeAPIError):
    """Server overloaded (529)."""

    def __init__(self, message: str = "API is overloaded") -> None:
        super().__init__(message, status_code=529)


class PromptTooLongError(LucyCodeAPIError):
    """Request prompt exceeds the model's context window."""

    def __init__(self, message: str = "Prompt is too long") -> None:
        super().__init__(message, status_code=400)


class MaxOutputTokensError(LucyCodeAPIError):
    """Response was truncated due to max_tokens."""

    def __init__(self, message: str = "Response hit max output tokens") -> None:
        super().__init__(message)


class ConnectionError_(LucyCodeAPIError):
    """Failed to connect to the API."""

    def __init__(self, message: str = "Failed to connect to API") -> None:
        super().__init__(message)


class UserAbortError(LucyCodeAPIError):
    """User cancelled the request."""

    def __init__(self, message: str = "Request cancelled by user") -> None:
        super().__init__(message)


PROMPT_TOO_LONG_MESSAGE = (
    "The conversation has exceeded the model's context window. "
    "Please use /compact to summarize the conversation, or /clear to start fresh."
)
