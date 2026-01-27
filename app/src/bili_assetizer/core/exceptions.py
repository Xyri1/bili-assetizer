"""Custom exceptions for bili-assetizer."""


class BiliAssetizerError(Exception):
    """Base exception for all bili-assetizer errors."""

    pass


class InvalidUrlError(BiliAssetizerError):
    """Raised when a URL cannot be parsed or is not a valid Bilibili URL."""

    pass


class BilibiliApiError(BiliAssetizerError):
    """Raised when a Bilibili API request fails."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code
