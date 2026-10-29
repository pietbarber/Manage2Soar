"""
Shared helpers for extracting the real client IP from an incoming request.

Security note:
    The app is deployed on a **GKE private cluster** with a managed L7 load
    balancer in front of the pods.  ``request.META['REMOTE_ADDR']`` inside the
    pod is therefore the *load balancer node* IP, not the end-user IP.  All
    per-IP logic (login throttling, access logs, kiosk usage tracking) MUST
    derive the client IP from the ``X-Forwarded-For`` (XFF) header.

    Which XFF entry is the real client?
        Per the GCP external Application Load Balancer docs, the load balancer
        does **not** overwrite a client-supplied XFF header — it *appends* its
        own values to the end.  If the client sends ``XFF: 8.8.8.8`` the LB
        forwards ``8.8.8.8, <client-ip>, <load-balancer-ip>``.  In other words:

            <existing client-controlled entries>, <client-ip>, <load-balancer-ip>

        So the **right-most** entry is the *shared load-balancer IP* (shared by
        every client, useless for per-IP throttling), the entries to the left
        of it that the client sent are **spoofable**, and the single entry
        immediately to the left of the LB IP — ``[-2]`` — is the address the LB
        itself observed as the connecting client.  That is the value we trust.

    Configurable trusted-hops:
        ``CLIENT_IP_TRAILING_PROXIES`` (default ``1``) is the number of
        trusted proxy addresses that sit *after* the real client in the XFF
        chain (for the GKE path that is just the LB IP).  The helper picks
        ``parts[-(N + 1)]``.  This preserves the single-host nginx
        single-hop topology, where nginx sets XFF to the direct peer and the
        real client is the last entry (``N = 0``).
        See ``manage2soar/settings.py`` for the GKE value and
        ``manage2soar/settings_single_host.py`` for the single-host value.

    Trust model:
        - The GKE cluster is not internet-reachable directly; the managed LB
          (and any CDN, e.g. Cloudflare, added later) is the only upstream, so
          the LB-observed entry (second from the right) is the most-trusted
          client hop.
        - If a future change exposes the pod directly to the internet, this
          helper becomes spoofable and must be replaced with a
          trust-list based implementation (e.g. ``django-ipware`` with
          ``PROXY_LIST``).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

# Number of trusted proxy addresses appended after the real client in the XFF
# chain.  GKE global external LB appends exactly one (the LB IP), so the real
# client is second from the right.  The single-host single-hop nginx topology
# appends none (nginx sets XFF to the peer), so the real client is last.
DEFAULT_TRAILING_PROXIES = 1


def _trusted_trailing_proxies() -> int:
    """Return the configured number of trusted proxy entries after the client."""
    try:
        n = getattr(settings, "CLIENT_IP_TRAILING_PROXIES", DEFAULT_TRAILING_PROXIES)
    except Exception:  # pragma: no cover - settings not configured (e.g. no Django)
        n = DEFAULT_TRAILING_PROXIES
    try:
        return max(0, int(n))
    except (TypeError, ValueError):
        return DEFAULT_TRAILING_PROXIES


def get_client_ip(request: HttpRequest) -> str:
    """Return the real client IP for ``request``.

    Prefers the client entry of ``X-Forwarded-For`` as observed by the trusted
    upstream proxy.  Per the GCP external LB docs the LB appends
    ``<client-ip>, <load-balancer-ip>`` to the right of any client-supplied
    value, so the trustworthy client entry is ``CLIENT_IP_TRAILING_PROXIES``
    entries from the right (default second-from-right = ``[-2]`` for the GKE
    path).  This avoids both the spoofable client-controlled left entries and
    the shared (every-client) right-most LB IP.  Falls back to
    ``REMOTE_ADDR`` when no ``X-Forwarded-For`` header is present (tests, local
    development without a proxy, or a misbehaving upstream).
    """
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        parts = [part.strip() for part in x_forwarded_for.split(",") if part.strip()]
        if parts:
            trailing = _trusted_trailing_proxies()
            index = -(trailing + 1)
            # If the chain is shorter than expected (e.g. single-hop proxy that
            # appended only the real client), fall back to the last entry.
            if len(parts) >= trailing + 1:
                return parts[index]
            return parts[-1]
    return request.META.get("REMOTE_ADDR", "") or ""
