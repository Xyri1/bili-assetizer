"""Tests for Bilibili HTTP client."""

import pytest
from unittest.mock import patch, MagicMock
import httpx

from bili_assetizer.core.bilibili_client import BilibiliClient
from bili_assetizer.core.exceptions import BilibiliApiError


class TestBilibiliClientInit:
    """Tests for BilibiliClient initialization."""

    def test_default_values(self):
        """Default values are set correctly."""
        client = BilibiliClient()
        assert client.timeout == 30.0
        assert client.retries == 3
        assert client._client is None

    def test_custom_values(self):
        """Custom values are accepted."""
        client = BilibiliClient(timeout=60.0, retries=5)
        assert client.timeout == 60.0
        assert client.retries == 5


class TestBilibiliClientContextManager:
    """Tests for context manager usage."""

    def test_context_manager_returns_self(self):
        """__enter__ returns the client instance."""
        client = BilibiliClient()
        with client as c:
            assert c is client

    def test_context_manager_closes_client(self):
        """__exit__ closes the HTTP client."""
        client = BilibiliClient()
        with client:
            # Force client creation
            _ = client._get_client()
            assert client._client is not None

        assert client._client is None

    def test_close_on_uninitialized_client(self):
        """close() handles uninitialized client."""
        client = BilibiliClient()
        client.close()  # Should not raise


class TestGetVideoView:
    """Tests for get_video_view method."""

    @patch.object(BilibiliClient, "_request_with_retry")
    def test_success(self, mock_request, sample_view_response):
        """Returns response on success."""
        mock_request.return_value = sample_view_response

        with BilibiliClient() as client:
            result = client.get_video_view("BV1vCzDBYEEa")

        assert result == sample_view_response
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "BV1vCzDBYEEa" in str(call_args)

    @patch.object(BilibiliClient, "_request_with_retry")
    def test_uses_correct_endpoint(self, mock_request, sample_view_response):
        """Uses correct API endpoint."""
        mock_request.return_value = sample_view_response

        with BilibiliClient() as client:
            client.get_video_view("BV1test")

        url = mock_request.call_args[0][0]
        assert "/x/web-interface/view" in url

    @patch.object(BilibiliClient, "_request_with_retry")
    def test_passes_bvid_param(self, mock_request, sample_view_response):
        """Passes bvid as query parameter."""
        mock_request.return_value = sample_view_response

        with BilibiliClient() as client:
            client.get_video_view("BV1param")

        params = mock_request.call_args[0][1]
        assert params["bvid"] == "BV1param"


class TestGetPlayurl:
    """Tests for get_playurl method."""

    @patch.object(BilibiliClient, "_request_with_retry")
    def test_success(self, mock_request, sample_playurl_response):
        """Returns response on success."""
        mock_request.return_value = sample_playurl_response

        with BilibiliClient() as client:
            result = client.get_playurl("BV1test", 12345)

        assert result == sample_playurl_response

    @patch.object(BilibiliClient, "_request_with_retry")
    def test_uses_correct_endpoint(self, mock_request, sample_playurl_response):
        """Uses correct API endpoint."""
        mock_request.return_value = sample_playurl_response

        with BilibiliClient() as client:
            client.get_playurl("BV1test", 12345)

        url = mock_request.call_args[0][0]
        assert "/x/player/playurl" in url

    @patch.object(BilibiliClient, "_request_with_retry")
    def test_passes_all_params(self, mock_request, sample_playurl_response):
        """Passes all query parameters."""
        mock_request.return_value = sample_playurl_response

        with BilibiliClient() as client:
            client.get_playurl("BV1test", 12345, qn=80, fnval=32)

        params = mock_request.call_args[0][1]
        assert params["bvid"] == "BV1test"
        assert params["cid"] == 12345
        assert params["qn"] == 80
        assert params["fnval"] == 32

    @patch.object(BilibiliClient, "_request_with_retry")
    def test_default_quality_params(self, mock_request, sample_playurl_response):
        """Uses default quality parameters."""
        mock_request.return_value = sample_playurl_response

        with BilibiliClient() as client:
            client.get_playurl("BV1test", 12345)

        params = mock_request.call_args[0][1]
        assert params["qn"] == 64
        assert params["fnval"] == 16


class TestRequestWithRetry:
    """Tests for _request_with_retry method."""

    def test_success_on_first_try(self, sample_view_response):
        """Returns response on successful first attempt."""
        with BilibiliClient() as client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_view_response
            mock_response.raise_for_status.return_value = None

            with patch.object(client._get_client(), "get", return_value=mock_response):
                result = client._request_with_retry("http://test.com", {})

        assert result == sample_view_response

    def test_api_error_code_raises(self):
        """API error code raises BilibiliApiError."""
        with BilibiliClient() as client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"code": -400, "message": "Invalid request"}
            mock_response.raise_for_status.return_value = None

            with patch.object(client._get_client(), "get", return_value=mock_response):
                with pytest.raises(BilibiliApiError) as exc_info:
                    client._request_with_retry("http://test.com", {})

            assert "-400" in str(exc_info.value) or "Invalid request" in str(exc_info.value)

    def test_http_error_retries(self):
        """HTTP errors trigger retries."""
        with BilibiliClient(retries=3) as client:
            http_client = client._get_client()

            # Fail twice, succeed on third
            fail_response = MagicMock()
            fail_response.status_code = 500
            fail_response.text = "Server error"
            fail_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Error", request=MagicMock(), response=fail_response
            )

            success_response = MagicMock()
            success_response.json.return_value = {"code": 0, "data": {}}
            success_response.raise_for_status.return_value = None

            with patch.object(
                http_client, "get", side_effect=[fail_response, fail_response, success_response]
            ):
                result = client._request_with_retry("http://test.com", {})

            assert result["code"] == 0

    def test_all_retries_exhausted_raises(self):
        """Raises after all retries exhausted."""
        with BilibiliClient(retries=2) as client:
            http_client = client._get_client()

            fail_response = MagicMock()
            fail_response.status_code = 500
            fail_response.text = "Server error"
            fail_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Error", request=MagicMock(), response=fail_response
            )

            with patch.object(http_client, "get", return_value=fail_response):
                with pytest.raises(BilibiliApiError):
                    client._request_with_retry("http://test.com", {})

    def test_network_error_retries(self):
        """Network errors trigger retries."""
        with BilibiliClient(retries=2) as client:
            http_client = client._get_client()

            success_response = MagicMock()
            success_response.json.return_value = {"code": 0, "data": {}}
            success_response.raise_for_status.return_value = None

            with patch.object(
                http_client,
                "get",
                side_effect=[httpx.ConnectError("Connection failed"), success_response],
            ):
                result = client._request_with_retry("http://test.com", {})

            assert result["code"] == 0


class TestClientConfiguration:
    """Tests for client configuration."""

    def test_base_url(self):
        """BASE_URL is set correctly."""
        assert BilibiliClient.BASE_URL == "https://api.bilibili.com"

    def test_default_headers(self):
        """DEFAULT_HEADERS are set."""
        headers = BilibiliClient.DEFAULT_HEADERS
        assert "User-Agent" in headers
        assert "Referer" in headers
        assert "bilibili" in headers["Referer"]

    def test_get_client_creates_httpx_client(self):
        """_get_client creates httpx.Client with correct config."""
        with BilibiliClient(timeout=45.0) as client:
            http_client = client._get_client()

            assert http_client is not None
            assert client._client is http_client
            # Second call returns same instance
            assert client._get_client() is http_client
