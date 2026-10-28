"""
Shared helpers for extracting the real client IP from an incoming request.

Security note:
    The app is deployed on a **GKE private cluster** with a managed L7 load
    balancer in front of the pods.  ``request.META['REMOTE_ADDR']`` inside the
    pod is therefore the *load balancer node* IP, not the end-user IP.  All
    per-IP logic (login throttling, access logs, kiosk usage tracking) MUST use
    the left-most entry of the ``X-Forwarded-For`` header, which the LB sets
    to the real client address.

    Trust model:
        - The GKE cluster is not internet-reachable directly; the LB (and any
          CDN, e.g. Cloudflare, added later) is the only upstream, so the
          left-most XFF entry is the most-trusted client hop.
        - If a future change exposes the pod directly to the internet, this
          helper becomes spoofable and must be replaced with a
          trust-list based implementation (e.g. ``django-ipware`` with
          ``PROXY_LIST``).
"""

from __future__ import annotations

from django.http import HttpRequest


def get_client_ip(request: HttpRequest) -> str:
    """Return the real client IP for ``request``.

    Prefers the left-most entry of ``X-Forwarded-For`` (set by the GKE
    load balancer / any CDN in front of the app).  Falls back to
    ``REMOTE_ADDR`` when no ``X-Forwarded-For`` header is present (e.g. in
    tests, local development without a proxy, or a misbehaving upstream).
    """
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""
