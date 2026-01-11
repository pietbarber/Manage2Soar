"""
Kiosk authentication views (Issue #364).

Provides passwordless authentication for dedicated kiosk devices using
magic URLs with device fingerprinting for security.
"""

import hashlib
import json
import logging

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import KioskAccessLog, KioskToken

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract client IP address from request, handling proxies."""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_kiosk_access(
    token_value, kiosk_token, request, status, fingerprint="", details=""
):
    """Log a kiosk access attempt for auditing with rate limiting."""
    # Rate limiting: Only log once per session + status combination
    # This prevents log spam while still capturing unique events
    session_key = request.session.session_key or "no-session"
    rate_limit_key = f"kiosk_log_{session_key}_{status}"

    # Check if we've logged this recently (within session)
    if rate_limit_key in request.session:
        return  # Skip duplicate logs

    KioskAccessLog.objects.create(
        kiosk_token=kiosk_token,
        token_value=token_value[:64] if token_value else "",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:256],
        device_fingerprint=fingerprint[:64] if fingerprint else "",
        status=status,
        details=details,
    )

    # Mark as logged in session to prevent duplicates
    # Note: This will create a session if one doesn't exist yet.
    # This is intentional for kiosk rate limiting to work across
    # multiple access attempts within the same browser session.
    request.session[rate_limit_key] = True


@require_GET
def kiosk_login(request, token):
    """
    Magic URL login for kiosk devices.

    This view handles the initial login and redirects to the device binding
    page if fingerprinting is needed, or directly logs in if already bound.
    """
    # Look up the token
    try:
        kiosk_token = KioskToken.objects.get(token=token)
    except KioskToken.DoesNotExist:
        log_kiosk_access(token, None, request, "invalid_token")
        logger.warning("Invalid kiosk token attempted: %s", token[:16])
        return render(
            request,
            "members/kiosk/error.html",
            {
                "title": "Access Denied",
                "message": "This kiosk access link is not available.",
            },
            status=403,
        )

    # Check if token is active
    if not kiosk_token.is_active:
        log_kiosk_access(token, kiosk_token, request, "inactive_token")
        logger.warning("Inactive kiosk token attempted: %s", kiosk_token.name)
        return render(
            request,
            "members/kiosk/error.html",
            {
                "title": "Access Denied",
                "message": "This kiosk access link has been disabled. Please contact an administrator.",
            },
            status=403,
        )

    # If device is not bound yet, show the binding page
    if not kiosk_token.is_device_bound():
        return render(
            request,
            "members/kiosk/bind_device.html",
            {
                "kiosk_token": kiosk_token,
                "token": token,
            },
        )

    # Device is bound - check if we have a fingerprint from JS
    # (This is for auto-reauth via cookie, fingerprint comes via middleware)
    # For initial magic URL visits, redirect to binding check
    return render(
        request,
        "members/kiosk/verify_device.html",
        {
            "kiosk_token": kiosk_token,
            "token": token,
        },
    )


@require_POST
@transaction.atomic
def kiosk_bind_device(request, token):
    """
    Bind a kiosk token to a specific device fingerprint.

    Called via AJAX from the binding page after JavaScript collects
    the device fingerprint.
    """
    try:
        # Use select_for_update() to prevent concurrent binding attempts
        # Lock the row for this token until the surrounding transaction commits
        kiosk_token = KioskToken.objects.select_for_update().get(
            token=token, is_active=True
        )
    except KioskToken.DoesNotExist:
        return JsonResponse({"error": "Access denied"}, status=403)

    # Get fingerprint from request
    try:
        data = json.loads(request.body)
        fingerprint = data.get("fingerprint", "")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request"}, status=400)

    if not fingerprint:
        return JsonResponse({"error": "No fingerprint provided"}, status=400)

    # Hash the fingerprint for storage
    fingerprint_hash = hashlib.sha256(fingerprint.encode()).hexdigest()

    # Validate fingerprint first to prevent TOCTOU race condition
    # Note: validate_fingerprint has dual semantics - it validates bound tokens
    # AND allows unbound tokens (for first-time binding). Consider using
    # should_allow_fingerprint() for clarity in new code.
    if not kiosk_token.validate_fingerprint(fingerprint_hash):
        log_kiosk_access(
            token,
            kiosk_token,
            request,
            "fingerprint_mismatch",
            fingerprint_hash,
            "Attempted to rebind to different device",
        )
        logger.warning("Fingerprint mismatch for kiosk token: %s", kiosk_token.name)
        return JsonResponse({"error": "Device verification failed"}, status=403)

    # If not yet bound, bind this device now
    if not kiosk_token.is_device_bound():
        kiosk_token.bind_device(fingerprint_hash)
        log_kiosk_access(
            token,
            kiosk_token,
            request,
            "bound",
            fingerprint_hash,
            f"Device bound: {request.headers.get('user-agent', '')[:100]}",
        )
        logger.info("Device bound to kiosk token: %s", kiosk_token.name)

    # Log the user in
    user = kiosk_token.user
    # Set backend attribute required by Django's login()
    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, user)

    # Record usage
    kiosk_token.record_usage(get_client_ip(request))

    # Log successful access
    log_kiosk_access(
        token, kiosk_token, request, "success", fingerprint_hash, "Device binding login"
    )

    # Ensure fingerprint exists (guaranteed after bind_device call)
    if kiosk_token.device_fingerprint is None:
        raise RuntimeError(
            f"Device fingerprint is not set after binding for kiosk token "
            f"'{kiosk_token.name}' (token={kiosk_token.token})"
        )

    # Set cookie for auto-reauth
    response = JsonResponse(
        {
            "success": True,
            "redirect": reverse(kiosk_token.landing_page),
            "message": f"Welcome! Logged in as {user.get_full_name() or user.username}",
        }
    )

    # Store token in cookie for auto-reauth (1 year expiry)
    response.set_cookie(
        "kiosk_token",
        kiosk_token.token,  # Use DB value, not user-supplied parameter
        max_age=365 * 24 * 60 * 60,
        httponly=True,  # Protect from XSS - JS doesn't need to read this
        samesite="Lax",
        secure=settings.KIOSK_COOKIE_SECURE,
    )

    # Store fingerprint hash in cookie for verification
    response.set_cookie(
        "kiosk_fingerprint",
        kiosk_token.device_fingerprint,  # Use DB value after binding
        max_age=365 * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        secure=settings.KIOSK_COOKIE_SECURE,
    )

    return response


@require_POST
def kiosk_verify_device(request, token):
    """
    Verify a device fingerprint matches the bound device.

    Called via AJAX from the verify page for already-bound devices.
    """
    try:
        kiosk_token = KioskToken.objects.get(token=token, is_active=True)
    except KioskToken.DoesNotExist:
        return JsonResponse({"error": "Access denied"}, status=403)

    # Get fingerprint from request
    try:
        data = json.loads(request.body)
        fingerprint = data.get("fingerprint", "")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request"}, status=400)

    if not fingerprint:
        return JsonResponse({"error": "No fingerprint provided"}, status=400)

    # Hash the fingerprint
    fingerprint_hash = hashlib.sha256(fingerprint.encode()).hexdigest()

    # Validate fingerprint (Note: validate_fingerprint is backwards-compatible
    # wrapper with dual semantics. Consider using should_allow_fingerprint())
    if not kiosk_token.validate_fingerprint(fingerprint_hash):
        log_kiosk_access(
            token,
            kiosk_token,
            request,
            "fingerprint_mismatch",
            fingerprint_hash,
            "Device verification failed",
        )
        logger.warning("Fingerprint mismatch for kiosk token: %s", kiosk_token.name)
        return JsonResponse({"error": "Device verification failed"}, status=403)

    # Log the user in
    user = kiosk_token.user
    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, user)

    # Record usage
    kiosk_token.record_usage(get_client_ip(request))

    # Log successful access
    log_kiosk_access(
        token, kiosk_token, request, "success", fingerprint_hash, "Device verification"
    )

    # Ensure fingerprint exists (guaranteed after validation)
    if kiosk_token.device_fingerprint is None:
        raise RuntimeError("Fingerprint must exist for bound token")

    # Set cookies for auto-reauth
    response = JsonResponse(
        {
            "success": True,
            "redirect": reverse(kiosk_token.landing_page),
        }
    )

    response.set_cookie(
        "kiosk_token",
        kiosk_token.token,  # Use DB value, not user-supplied parameter
        max_age=365 * 24 * 60 * 60,
        httponly=True,  # Protect from XSS - JS doesn't need to read this
        samesite="Lax",
        secure=settings.KIOSK_COOKIE_SECURE,
    )

    # Refresh fingerprint cookie
    response.set_cookie(
        "kiosk_fingerprint",
        kiosk_token.device_fingerprint,  # Use DB value after validation
        max_age=365 * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        secure=settings.KIOSK_COOKIE_SECURE,
    )

    return response


def kiosk_error(request):
    """Generic kiosk error page."""
    return render(
        request,
        "members/kiosk/error.html",
        {
            "title": "Kiosk Error",
            "message": "An error occurred with kiosk authentication.",
        },
    )
