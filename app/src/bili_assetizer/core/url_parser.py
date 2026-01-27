"""URL parsing utilities for Bilibili URLs."""

import re
from urllib.parse import urlparse, parse_qs

from .exceptions import InvalidUrlError

# BVID pattern: starts with BV followed by alphanumeric characters
BVID_PATTERN = re.compile(r"BV[a-zA-Z0-9]+")


def extract_bvid(url: str) -> str:
    """Extract BVID from a Bilibili video URL.

    Handles various URL formats:
    - https://www.bilibili.com/video/BV1vCzDBYEEa
    - https://www.bilibili.com/video/BV1vCzDBYEEa/
    - https://www.bilibili.com/video/BV1vCzDBYEEa?p=1
    - https://b23.tv/BV1vCzDBYEEa
    - BV1vCzDBYEEa (bare BVID)

    Args:
        url: A Bilibili video URL or bare BVID.

    Returns:
        The extracted BVID string.

    Raises:
        InvalidUrlError: If no valid BVID can be extracted.
    """
    url = url.strip()

    if not url:
        raise InvalidUrlError("Empty URL provided")

    # Try to find BVID anywhere in the string
    match = BVID_PATTERN.search(url)
    if match:
        return match.group(0)

    # If no BVID found, provide helpful error message
    try:
        parsed = urlparse(url)
        if parsed.netloc and "bilibili" not in parsed.netloc.lower():
            raise InvalidUrlError(f"URL does not appear to be a Bilibili URL: {url}")
    except Exception:
        pass

    raise InvalidUrlError(f"Could not extract BVID from URL: {url}")


def normalize_bilibili_url(bvid: str) -> str:
    """Create a normalized Bilibili URL from a BVID.

    Args:
        bvid: A valid BVID string.

    Returns:
        Normalized URL in the format https://www.bilibili.com/video/{bvid}
    """
    return f"https://www.bilibili.com/video/{bvid}"
