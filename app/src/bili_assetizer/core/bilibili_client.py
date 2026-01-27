"""HTTP client for Bilibili API."""

import httpx
from typing import Any

from .exceptions import BilibiliApiError


class BilibiliClient:
    """Client for interacting with Bilibili public APIs."""

    BASE_URL = "https://api.bilibili.com"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com",
    }

    def __init__(self, timeout: float = 30.0, retries: int = 3):
        """Initialize the Bilibili client.

        Args:
            timeout: Request timeout in seconds.
            retries: Number of retry attempts for failed requests.
        """
        self.timeout = timeout
        self.retries = retries
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                headers=self.DEFAULT_HEADERS,
                follow_redirects=True,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "BilibiliClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _request_with_retry(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """Make a request with retry logic.

        Args:
            url: The URL to request.
            params: Query parameters.

        Returns:
            The JSON response data.

        Raises:
            BilibiliApiError: If the request fails after all retries.
        """
        client = self._get_client()
        last_error: Exception | None = None

        for attempt in range(self.retries):
            try:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Check Bilibili API response code
                code = data.get("code", 0)
                if code != 0:
                    message = data.get("message", "Unknown error")
                    raise BilibiliApiError(f"Bilibili API error: {message}", code=code)

                return data

            except httpx.HTTPStatusError as e:
                last_error = BilibiliApiError(
                    f"HTTP error {e.response.status_code}: {e.response.text}"
                )
            except httpx.RequestError as e:
                last_error = BilibiliApiError(f"Request failed: {e}")
            except BilibiliApiError:
                raise
            except Exception as e:
                last_error = BilibiliApiError(f"Unexpected error: {e}")

        raise last_error or BilibiliApiError("Request failed after all retries")

    def get_video_view(self, bvid: str) -> dict[str, Any]:
        """Get video view information.

        Args:
            bvid: The video's BVID.

        Returns:
            The raw API response including 'data' field.

        Raises:
            BilibiliApiError: If the API request fails.
        """
        url = f"{self.BASE_URL}/x/web-interface/view"
        return self._request_with_retry(url, {"bvid": bvid})

    def get_playurl(
        self, bvid: str, cid: int, qn: int = 64, fnval: int = 16
    ) -> dict[str, Any]:
        """Get video play URL information.

        Args:
            bvid: The video's BVID.
            cid: The content ID (from video view).
            qn: Quality number (default 64 = 720P).
            fnval: Format flag (16 = DASH format).

        Returns:
            The raw API response including 'data' field.

        Raises:
            BilibiliApiError: If the API request fails.
        """
        url = f"{self.BASE_URL}/x/player/playurl"
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": qn,
            "fnval": fnval,
        }
        return self._request_with_retry(url, params)
