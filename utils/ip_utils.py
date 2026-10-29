"""
Shared helpers for extracting the real client IP from an incoming request.

Security note:
    The app is deployed on a **GKE private cluster** with a managed L7 load
    balancer in front of the pods.  ``request.META['REMOTE_ADDR']`` inside the
    pod is therefore the *load balancer node* IP, not the end-user IP.  All
    per-IP logic (login throttling, access logs, kiosk usage tracking) MUST
    derive the client IP from the ``X-Forwarded-For`` header that the LB
    maintains.

    Which XFF entry is the real client?
        GCP's external L7 (HTTPS) load balancer does NOT overwrite a
        client-supplied ``X-Forwarded-For`` header.  It *appends* the
        connection source address it actually observed to the **right** of
        whatever the client sent.  An untrusted client is therefore free to
        spoof the left-most entries (e.g. ``X-Forwarded-For: 8.8.8.8``); the
        LB then yields ``8.8.8.8, <real-client>``.  The one value the LB
        cannot be tricked into producing is the *last* (right-most) entry it
        appended itself, which reflects the true connecting address.

    Trust model:
        - The GKE cluster is not internet-reachable directly; the managed LB
          (and any CDN, e.g. Cloudflare, added later) is the only upstream.
          The right-most XFF entry is the most-trusted client hop.
        - If a future change exposes the pod directly to the internet, this
          helper becomes spoofable and must be replaced with a
          trust-list based implementation (e.g. ``django-ipware`` with
          ``PROXY_LIST``).
"""

from __future__ import annotations

from django.http import HttpRequest


def get_client_ip(request: HttpRequest) -> str:
    """Return the real client IP for ``request``.

    Prefers the **right-most** entry of ``X-Forwarded-For``.  The GCP external
    L7 load balancer appends the true connecting address to the right of any
    client-supplied ``X-Forwarded-For`` value, so the right-most entry is the
    one we trust (the left-most entries are client-controlled and spoofable).
    Falls back to ``REMOTE_ADDR`` when no ``X-Forwarded-For`` header is present
    (e.g. in tests, local development without a proxy, or a misbehaving
    upstream).
    """
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "") or ""
