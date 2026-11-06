"""
Shared helpers for extracting the real client IP from an incoming request.

Security note:
    The app is deployed on a **GKE private cluster** with a managed L7 load
    balancer in front of the pods.  ``request.META['REMOTE_ADDR']`` inside the
    pod is therefore the *load balancer node* IP, not the end-user IP.  All
    per-IP logic (login throttling, access logs, kiosk usage tracking) uses
    ``X-Forwarded-For`` (XFF) only for verified proxy peers; other requests
    use their direct REMOTE_ADDR.

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
        XFF is accepted only if REMOTE_ADDR belongs to a configured
        CLIENT_IP_TRUSTED_PROXIES CIDR. Empty allowlists and invalid chains
        fall back to REMOTE_ADDR. GKE must configure the pod-facing peer CIDRs
        explicitly; single-host trusts only local nginx by default.
"""

from __future__ import annotations

import ipaddress

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

    Uses the client entry of ``X-Forwarded-For`` only when the immediate peer
    is in CLIENT_IP_TRUSTED_PROXIES. Per the GCP external LB docs the LB appends
    ``<client-ip>, <load-balancer-ip>`` to the right of any client-supplied
    value, so the trustworthy client entry is ``CLIENT_IP_TRAILING_PROXIES``
    entries from the right (default second-from-right = ``[-2]`` for the GKE
    path).  This avoids both the spoofable client-controlled left entries and
    the shared (every-client) right-most LB IP. Falls back to
    ``REMOTE_ADDR`` for untrusted peers, missing or malformed XFF, or a short
    chain. The proxy must enforce its documented append/replace behavior.
    """
    remote = request.META.get("REMOTE_ADDR", "") or ""
    try:
        peer = ipaddress.ip_address(remote)
    except ValueError:
        return remote
    networks = getattr(settings, "CLIENT_IP_TRUSTED_PROXIES", ())
    if isinstance(networks, str):
        networks = networks.split(",")
    # No configured peers means no header trust, even when the request supplies XFF.
    trusted = []
    for network in networks:
        if network.strip():
            try:
                trusted.append(ipaddress.ip_network(network.strip(), strict=False))
            except ValueError:
                # A bad deployment value must not make a forged XFF usable.
                return remote
    if not any(peer in network for network in trusted):
        return remote

    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return remote
    parts = [part.strip() for part in xff.split(",")]
    trailing = _trusted_trailing_proxies()
    if len(parts) <= trailing or any(not part for part in parts):
        return remote
    try:
        addresses = [ipaddress.ip_address(part) for part in parts]
    except ValueError:
        return remote
    # GKE's proxy appends the right-most hop; the observed client precedes it.
    return str(addresses[-(trailing + 1)])
