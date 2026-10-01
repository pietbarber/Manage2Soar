"""Tests for the external PDF proxy (Issue #1069 Phase 3)."""

from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse

from cms.models import ExternalPdfCache
from cms.pdf_proxy import (
    ExternalPdfFetchError,
    _request_pinned_pdf,
    get_or_fetch_cached_pdf,
    is_proxyable_external_url,
    sign_external_pdf_url,
)

ALLOWED_URL = "https://pdfs.example.com/bylaws.pdf"


class _FakeResponse:
    def __init__(self, status_code, content=b"", headers=None, is_redirect=False):
        self.status = status_code
        self._content = content
        self.headers = headers or {}
        self.closed = False

    def stream(self, chunk_size=65536):
        for start in range(0, len(self._content), chunk_size):
            yield self._content[start : start + chunk_size]

    def release_conn(self):
        self.closed = True


def _patch_public_dns(monkeypatch, ip="93.184.216.34"):
    """Make every hostname resolve to a fixed public IP (SSRF checks pass)."""
    monkeypatch.setattr(
        "cms.pdf_proxy.socket.getaddrinfo",
        lambda hostname, port: [(2, 1, 6, "", (ip, 0))],
    )


def _local_storage_settings(tmp_path):
    return override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    )


# --- is_proxyable_external_url -------------------------------------------------


def test_disabled_by_default_with_empty_allowlist(settings):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = []
    assert is_proxyable_external_url(ALLOWED_URL) is False


def test_rejects_non_https_scheme(settings, monkeypatch):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)
    assert is_proxyable_external_url("http://pdfs.example.com/bylaws.pdf") is False


def test_rejects_host_not_on_allowlist(settings, monkeypatch):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)
    assert is_proxyable_external_url("https://attacker.example/evil.pdf") is False


def test_rejects_hostname_resolving_to_loopback(settings):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["localhost"]
    # "localhost" reliably resolves to a loopback address without mocking DNS.
    assert is_proxyable_external_url("https://localhost/bylaws.pdf") is False


def test_rejects_hostname_resolving_to_private_ip(settings, monkeypatch):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["internal.example.com"]
    monkeypatch.setattr(
        "cms.pdf_proxy.socket.getaddrinfo",
        lambda hostname, port: [(2, 1, 6, "", ("10.0.0.5", 0))],
    )
    assert is_proxyable_external_url("https://internal.example.com/x.pdf") is False


def test_allows_allowlisted_host_resolving_publicly(settings, monkeypatch):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)
    assert is_proxyable_external_url(ALLOWED_URL) is True


def test_pinned_request_uses_public_ip_and_relative_path(monkeypatch):
    class FakePool:
        def __init__(self, host, **kwargs):
            self.host = host
            self.kwargs = kwargs

        def request(self, method, path, **kwargs):
            assert method == "GET"
            assert path == "/bylaws.pdf"
            assert kwargs["headers"] == {"Host": "pdfs.example.com"}
            return "response"

    _patch_public_dns(monkeypatch, ip="93.184.216.34")
    pool = FakePool
    monkeypatch.setattr("cms.pdf_proxy.urllib3.HTTPSConnectionPool", pool)

    response = _request_pinned_pdf(ALLOWED_URL)

    assert response == "response"


# --- get_or_fetch_cached_pdf / _fetch_validated_pdf_bytes ----------------------


@pytest.mark.django_db
def test_fetch_caches_valid_pdf(settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)

    with _local_storage_settings(tmp_path):
        with patch(
            "cms.pdf_proxy._request_pinned_pdf",
            return_value=_FakeResponse(200, content=b"%PDF-1.7 hello"),
        ) as mock_get:
            cached = get_or_fetch_cached_pdf(ALLOWED_URL)

        assert mock_get.call_count == 1
        assert ExternalPdfCache.objects.filter(url=ALLOWED_URL).count() == 1
        with cached.file.open("rb") as fh:
            assert fh.read() == b"%PDF-1.7 hello"


@pytest.mark.django_db
def test_fetch_rejects_non_pdf_content(settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)

    with _local_storage_settings(tmp_path):
        with patch(
            "cms.pdf_proxy._request_pinned_pdf",
            return_value=_FakeResponse(200, content=b"<html>not a pdf</html>"),
        ):
            with pytest.raises(ExternalPdfFetchError):
                get_or_fetch_cached_pdf(ALLOWED_URL)

        assert ExternalPdfCache.objects.filter(url=ALLOWED_URL).count() == 0


@pytest.mark.django_db
def test_fetch_rejects_oversized_response(settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)
    monkeypatch.setattr("cms.pdf_proxy.MAX_RESPONSE_BYTES", 8)

    with _local_storage_settings(tmp_path):
        with patch(
            "cms.pdf_proxy._request_pinned_pdf",
            return_value=_FakeResponse(200, content=b"%PDF-1.7 way too big"),
        ):
            with pytest.raises(ExternalPdfFetchError):
                get_or_fetch_cached_pdf(ALLOWED_URL)


@pytest.mark.django_db
def test_fetch_follows_allowlisted_redirect(settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)
    redirected_url = "https://pdfs.example.com/final.pdf"

    responses = [
        _FakeResponse(302, headers={"Location": redirected_url}, is_redirect=True),
        _FakeResponse(200, content=b"%PDF-1.7 redirected"),
    ]

    with _local_storage_settings(tmp_path):
        with patch("cms.pdf_proxy._request_pinned_pdf", side_effect=responses):
            cached = get_or_fetch_cached_pdf(ALLOWED_URL)

        with cached.file.open("rb") as fh:
            assert fh.read() == b"%PDF-1.7 redirected"


@pytest.mark.django_db
def test_fetch_rejects_redirect_to_disallowed_host(settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)

    responses = [
        _FakeResponse(
            302,
            headers={"Location": "https://attacker.example/evil.pdf"},
            is_redirect=True,
        ),
    ]

    with _local_storage_settings(tmp_path):
        with patch("cms.pdf_proxy._request_pinned_pdf", side_effect=responses):
            with pytest.raises(ExternalPdfFetchError):
                get_or_fetch_cached_pdf(ALLOWED_URL)


@pytest.mark.django_db
def test_cached_copy_is_reused_within_ttl(settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    settings.CMS_EXTERNAL_PDF_PROXY_CACHE_TTL_SECONDS = 3600
    _patch_public_dns(monkeypatch)

    with _local_storage_settings(tmp_path):
        with patch(
            "cms.pdf_proxy._request_pinned_pdf",
            return_value=_FakeResponse(200, content=b"%PDF-1.7 hello"),
        ) as mock_get:
            get_or_fetch_cached_pdf(ALLOWED_URL)
            get_or_fetch_cached_pdf(ALLOWED_URL)

        assert mock_get.call_count == 1


@pytest.mark.django_db
def test_stale_cache_served_when_refresh_fetch_fails(settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    settings.CMS_EXTERNAL_PDF_PROXY_CACHE_TTL_SECONDS = 0
    _patch_public_dns(monkeypatch)

    with _local_storage_settings(tmp_path):
        with patch(
            "cms.pdf_proxy._request_pinned_pdf",
            return_value=_FakeResponse(200, content=b"%PDF-1.7 hello"),
        ):
            get_or_fetch_cached_pdf(ALLOWED_URL)

        with patch(
            "cms.pdf_proxy._request_pinned_pdf",
            side_effect=ExternalPdfFetchError("network down"),
        ):
            cached = get_or_fetch_cached_pdf(ALLOWED_URL)

        with cached.file.open("rb") as fh:
            assert fh.read() == b"%PDF-1.7 hello"


# --- view: cms:external_pdf_proxy ----------------------------------------------


@pytest.mark.django_db
def test_view_rejects_missing_url(client):
    response = client.get(reverse("cms:external_pdf_proxy"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_view_rejects_unsigned_url(client, settings, monkeypatch):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)
    response = client.get(reverse("cms:external_pdf_proxy"), {"url": ALLOWED_URL})
    assert response.status_code == 403


@pytest.mark.django_db
def test_view_rejects_disallowed_host(client, settings):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    response = client.get(
        reverse("cms:external_pdf_proxy"), {"url": "https://attacker.example/x.pdf"}
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_view_serves_allowlisted_pdf(client, settings, monkeypatch, tmp_path):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)

    with _local_storage_settings(tmp_path):
        with patch(
            "cms.pdf_proxy._request_pinned_pdf",
            return_value=_FakeResponse(200, content=b"%PDF-1.7 hello"),
        ):
            response = client.get(
                reverse("cms:external_pdf_proxy"),
                {"url": ALLOWED_URL, "signature": sign_external_pdf_url(ALLOWED_URL)},
            )

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "SAMEORIGIN"
        assert response["Content-Security-Policy"] == "frame-ancestors 'self'"
        assert b"".join(response.streaming_content) == b"%PDF-1.7 hello"


@pytest.mark.django_db
def test_view_returns_403_when_fetch_fails_and_nothing_cached(
    client, settings, monkeypatch
):
    settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS = ["pdfs.example.com"]
    _patch_public_dns(monkeypatch)

    with patch(
        "cms.pdf_proxy._request_pinned_pdf",
        return_value=_FakeResponse(200, content=b"not a pdf"),
    ):
        response = client.get(
            reverse("cms:external_pdf_proxy"),
            {"url": ALLOWED_URL, "signature": sign_external_pdf_url(ALLOWED_URL)},
        )

    assert response.status_code == 403
