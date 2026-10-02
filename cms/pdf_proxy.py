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
from urllib.parse import urljoin, urlparse, urlunparse

import urllib3
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.signing import BadSignature, Signer
from django.db import IntegrityError
from django.utils import timezone

from .models import ExternalPdfCache

MAX_RESPONSE_BYTES = 25 * 1024 * 1024  # 25 MB
FETCH_TIMEOUT_SECONDS = (5, 15)  # (connect, read)
MAX_REDIRECTS = 3
PDF_SIGNATURE = b"%PDF-"
_proxy_signer = Signer(salt="cms.external-pdf-proxy")


class ExternalPdfFetchError(Exception):
    """Raised when an external PDF URL cannot be safely fetched or validated."""


def sign_external_pdf_url(url):
    return _proxy_signer.sign(url)


def verify_external_pdf_url(url, signature):
    if not url or not signature:
        return False
    try:
        return _proxy_signer.unsign(signature) == url
    except BadSignature:
        return False


def _public_addresses(hostname):
    """Return unique public IPs for `hostname`, or an empty list if unsafe."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OverflowError):
        return []
    if not infos:
        return []
    addresses = []
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return []
        if not ip.is_global:
            return []
        if str(ip) not in addresses:
            addresses.append(str(ip))
    return addresses


def is_proxyable_external_url(url):
    """Return True if `url` is https, on the configured host allowlist, and resolves publicly."""
    allowed_hosts = settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS
    if not allowed_hosts or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname or port not in (None, 443):
        return False
    if parsed.hostname.lower() not in allowed_hosts:
        return False
    return bool(_public_addresses(parsed.hostname))


def _request_pinned_pdf(url):
    """Fetch a validated URL through a public-IP-pinned HTTPS connection."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    addresses = _public_addresses(hostname)
    if not addresses:
        raise ExternalPdfFetchError("URL no longer resolves to a public address.")

    path = urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    pool = urllib3.HTTPSConnectionPool(
        addresses[0],
        port=443,
        timeout=urllib3.Timeout(
            connect=FETCH_TIMEOUT_SECONDS[0], read=FETCH_TIMEOUT_SECONDS[1]
        ),
        cert_reqs="CERT_REQUIRED",
        assert_hostname=hostname,
        server_hostname=hostname,
        retries=False,
    )
    try:
        return pool.request(
            "GET",
            path,
            headers={"Host": hostname},
            preload_content=False,
        )
    except urllib3.exceptions.HTTPError as exc:
        raise ExternalPdfFetchError(f"Fetch failed: {exc}") from exc


def _fetch_validated_pdf_bytes(url):
    """Fetch `url`, following only allowlisted redirects, and return validated PDF bytes."""
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        if not is_proxyable_external_url(current_url):
            raise ExternalPdfFetchError(
                "URL is not on the allowed external PDF host list."
            )
        response = _request_pinned_pdf(current_url)

        try:
            if response.status in (
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

            if response.status != 200:
                raise ExternalPdfFetchError(
                    f"Unexpected status code {response.status}."
                )

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    content_length_value = int(content_length)
                except (TypeError, ValueError) as exc:
                    raise ExternalPdfFetchError(
                        "Response has an invalid Content-Length."
                    ) from exc
                if content_length_value > MAX_RESPONSE_BYTES:
                    raise ExternalPdfFetchError(
                        "Response exceeds the maximum allowed size."
                    )

            chunks = []
            total = 0
            try:
                for chunk in response.stream(65536):
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise ExternalPdfFetchError(
                            "Response exceeds the maximum allowed size."
                        )
                    chunks.append(chunk)
            except urllib3.exceptions.HTTPError as exc:
                raise ExternalPdfFetchError("PDF response stream failed.") from exc
        finally:
            response.release_conn()

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
    try:
        cached.save()
    except IntegrityError:
        # Another worker won the unique URL race while this request fetched.
        cached = ExternalPdfCache.objects.get(url=url)
    return cached
