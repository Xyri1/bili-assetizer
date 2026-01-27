"""Tests for URL parsing utilities."""

import pytest

from bili_assetizer.core.url_parser import extract_bvid, normalize_bilibili_url
from bili_assetizer.core.exceptions import InvalidUrlError


class TestExtractBvid:
    """Tests for extract_bvid function."""

    # Valid URL tests
    def test_full_url(self):
        """Extracts BVID from full Bilibili URL."""
        url = "https://www.bilibili.com/video/BV1vCzDBYEEa"
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    def test_url_with_trailing_slash(self):
        """Extracts BVID from URL with trailing slash."""
        url = "https://www.bilibili.com/video/BV1vCzDBYEEa/"
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    def test_url_with_query_params(self):
        """Extracts BVID from URL with query parameters."""
        url = "https://www.bilibili.com/video/BV1vCzDBYEEa?p=1&vd_source=abc123"
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    def test_short_url(self):
        """Extracts BVID from short b23.tv URL."""
        url = "https://b23.tv/BV1vCzDBYEEa"
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    def test_bare_bvid(self):
        """Extracts bare BVID without URL."""
        bvid = "BV1vCzDBYEEa"
        assert extract_bvid(bvid) == "BV1vCzDBYEEa"

    def test_http_url(self):
        """Extracts BVID from HTTP URL (non-HTTPS)."""
        url = "http://www.bilibili.com/video/BV1vCzDBYEEa"
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    def test_mobile_url(self):
        """Extracts BVID from mobile URL."""
        url = "https://m.bilibili.com/video/BV1vCzDBYEEa"
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    def test_url_without_www(self):
        """Extracts BVID from URL without www."""
        url = "https://bilibili.com/video/BV1vCzDBYEEa"
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    # Invalid URL tests
    def test_empty_url_raises(self):
        """Empty URL raises InvalidUrlError."""
        with pytest.raises(InvalidUrlError) as exc_info:
            extract_bvid("")
        assert "Empty URL" in str(exc_info.value)

    def test_whitespace_only_raises(self):
        """Whitespace-only URL raises InvalidUrlError."""
        with pytest.raises(InvalidUrlError) as exc_info:
            extract_bvid("   ")
        assert "Empty URL" in str(exc_info.value)

    def test_non_bilibili_domain_raises(self):
        """Non-Bilibili domain raises InvalidUrlError."""
        with pytest.raises(InvalidUrlError) as exc_info:
            extract_bvid("https://youtube.com/watch?v=12345")
        assert "Bilibili" in str(exc_info.value) or "BVID" in str(exc_info.value)

    def test_missing_bvid_raises(self):
        """URL without BVID raises InvalidUrlError."""
        with pytest.raises(InvalidUrlError):
            extract_bvid("https://www.bilibili.com/video/")

    def test_invalid_bvid_format_raises(self):
        """Invalid BVID format raises InvalidUrlError."""
        with pytest.raises(InvalidUrlError):
            extract_bvid("https://www.bilibili.com/video/av12345")

    def test_random_text_raises(self):
        """Random text without BVID raises InvalidUrlError."""
        with pytest.raises(InvalidUrlError):
            extract_bvid("this is not a url at all")

    # Edge cases
    def test_url_with_whitespace_is_trimmed(self):
        """URL with leading/trailing whitespace is trimmed."""
        url = "  https://www.bilibili.com/video/BV1vCzDBYEEa  "
        assert extract_bvid(url) == "BV1vCzDBYEEa"

    def test_multiple_bvids_returns_first(self):
        """URL with multiple BVIDs returns first one."""
        url = "https://www.bilibili.com/video/BV1first123?ref=BV2second456"
        assert extract_bvid(url) == "BV1first123"

    def test_different_bvid_lengths(self):
        """Different BVID lengths are extracted."""
        # Short BVID
        assert extract_bvid("BV1abc") == "BV1abc"
        # Long BVID
        assert extract_bvid("BV1abcdefghij12345") == "BV1abcdefghij12345"


class TestNormalizeBilibiliUrl:
    """Tests for normalize_bilibili_url function."""

    def test_basic_normalization(self):
        """Creates normalized URL from BVID."""
        bvid = "BV1vCzDBYEEa"
        expected = "https://www.bilibili.com/video/BV1vCzDBYEEa"
        assert normalize_bilibili_url(bvid) == expected

    def test_different_bvids(self):
        """Works with different BVIDs."""
        assert normalize_bilibili_url("BV1abc123") == "https://www.bilibili.com/video/BV1abc123"
        assert normalize_bilibili_url("BV2xyz789") == "https://www.bilibili.com/video/BV2xyz789"
