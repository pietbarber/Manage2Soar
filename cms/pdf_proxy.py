"""SSRF-hardened fetch/cache for externally-hosted PDF embeds (Issue #1069 Phase 3).

``CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS`` gates which external hostnames may be
proxied at all; every resolved address (including redirect targets) is also
checked against private/loopback/link-local/reserved IP ranges, so an
allowlisted hostname can never be used to pivot into internal infrastructure
via DNS rebinding or an open redirect to another host.

Fetched bytes are validated against the PDF file signature and cached in
``ExternalPdfCache`` so a page view never triggers a fresh outbound fetch for
every visitor; see ``CMS_EXTERNAL_PDF_PROXY_CACHE_TTL_SECONDS``.
"""

import hashlib
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import ExternalPdfCache

MAX_RESPONSE_BYTES = 25 * 1024 * 1024  # 25 MB
FETCH_TIMEOUT_SECONDS = (5, 15)  # (connect, read)
MAX_REDIRECTS = 3
PDF_SIGNATURE = b"%PDF-"


class ExternalPdfFetchError(Exception):
    """Raised when an external PDF URL cannot be safely fetched or validated."""


def _resolves_to_public_address(hostname):
    """Reject hostnames that resolve to any private/loopback/link-local/reserved IP."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OverflowError):
        return False
    if not infos:
        return False
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def is_proxyable_external_url(url):
    """Return True if `url` is https, on the configured host allowlist, and resolves publicly."""
    allowed_hosts = settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS
    if not allowed_hosts or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    if parsed.hostname.lower() not in allowed_hosts:
        return False
    return _resolves_to_public_address(parsed.hostname)


def _fetch_validated_pdf_bytes(url):
    """Fetch `url`, following only allowlisted redirects, and return validated PDF bytes."""
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        if not is_proxyable_external_url(current_url):
            raise ExternalPdfFetchError(
                "URL is not on the allowed external PDF host list."
            )
        try:
            response = requests.get(
                current_url,
                stream=True,
                timeout=FETCH_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ExternalPdfFetchError(f"Fetch failed: {exc}") from exc

        try:
            if response.is_redirect or response.status_code in (
                301,
                302,
                303,
                307,
                308,
            ):
                location = response.headers.get("Location")
                if not location:
                    raise ExternalPdfFetchError("Redirect without a Location header.")
                current_url = urljoin(current_url, location)
                continue

            if response.status_code != 200:
                raise ExternalPdfFetchError(
                    f"Unexpected status code {response.status_code}."
                )

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                raise ExternalPdfFetchError(
                    "Response exceeds the maximum allowed size."
                )

            chunks = []
            total = 0
            for chunk in response.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ExternalPdfFetchError(
                        "Response exceeds the maximum allowed size."
                    )
                chunks.append(chunk)
        finally:
            response.close()

        content = b"".join(chunks)
        if not content.startswith(PDF_SIGNATURE):
            raise ExternalPdfFetchError("Response is not a valid PDF.")
        return content

    raise ExternalPdfFetchError("Too many redirects.")


def get_or_fetch_cached_pdf(url):
    """Return an up-to-date ExternalPdfCache row for `url`, fetching/refreshing as needed.

    Raises ExternalPdfFetchError if there is no usable cached copy and a
    fresh fetch fails validation.
    """
    ttl = timezone.timedelta(seconds=settings.CMS_EXTERNAL_PDF_PROXY_CACHE_TTL_SECONDS)
    cached = ExternalPdfCache.objects.filter(url=url).first()
    if cached and timezone.now() - cached.fetched_at < ttl:
        return cached

    try:
        content = _fetch_validated_pdf_bytes(url)
    except ExternalPdfFetchError:
        if cached:
            # Serve the stale copy rather than break a previously-working embed.
            return cached
        raise

    digest = hashlib.sha256(content).hexdigest()
    if cached is None:
        cached = ExternalPdfCache(url=url)
    if cached.content_hash != digest:
        cached.file.save(f"{digest}.pdf", ContentFile(content), save=False)
        cached.content_hash = digest
        cached.size_bytes = len(content)
    cached.save()
    return cached
