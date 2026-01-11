"""
Custom middleware for health checks and other utilities.
"""

import logging

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpResponse

logger = logging.getLogger(__name__)


class HealthCheckMiddleware:
    """
    Middleware that handles health check requests without SSL redirects.
    This allows GKE load balancer health checks to work properly.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle health check requests directly, bypassing SSL redirects
        if request.path == "/health/":
            return HttpResponse("OK", content_type="text/plain")

        response = self.get_response(request)
        return response


class KioskAutoLoginMiddleware:
    """
    Middleware for automatic kiosk re-authentication (Issue #364).

    If the user is not authenticated but has valid kiosk cookies (token + fingerprint),
    automatically log them in. This enables seamless re-authentication after session
    expiry without requiring user intervention.

    This middleware should be placed AFTER AuthenticationMiddleware in MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only process if user is not already authenticated
        if not request.user.is_authenticated:
            kiosk_token_value = request.COOKIES.get("kiosk_token")
            kiosk_fingerprint = request.COOKIES.get("kiosk_fingerprint")

            if kiosk_token_value and kiosk_fingerprint:
                user = self._authenticate_kiosk(
                    request, kiosk_token_value, kiosk_fingerprint
                )
                if user:
                    # Successfully authenticated via kiosk token
                    user.backend = "django.contrib.auth.backends.ModelBackend"
                    login(request, user)
                    logger.debug(
                        f"Kiosk auto-login successful for user: {user.username}"
                    )

        response = self.get_response(request)
        return response

    def _authenticate_kiosk(self, request, token_value, fingerprint_hash):
        """
        Authenticate a kiosk user via token and fingerprint cookies.

        Returns the user if authentication succeeds, None otherwise.
        """
        # Import here to avoid circular imports
        from members.models import KioskAccessLog, KioskToken

        # Look up the kiosk token for this request
        try:
            # Query with select_related to reduce database hits
            # Note: token field has unique=True index. Consider caching valid
            # tokens if this becomes a performance bottleneck in production.
            kiosk_token = KioskToken.objects.select_related("user").get(
                token=token_value,
                is_active=True,
            )
        except KioskToken.DoesNotExist:
            logger.debug("Kiosk auto-login failed: invalid token")
            return None

        # Validate fingerprint matches
        if not kiosk_token.validate_fingerprint(fingerprint_hash):
            logger.warning(
                f"Kiosk auto-login fingerprint mismatch for token: {kiosk_token.name}"
            )
            # Log the failed attempt
            KioskAccessLog.objects.create(
                kiosk_token=kiosk_token,
                token_value=token_value[:64],
                ip_address=self._get_client_ip(request),
                user_agent=request.headers.get("user-agent", "")[:256],
                device_fingerprint=fingerprint_hash[:64],
                status="fingerprint_mismatch",
                details="Auto-reauth fingerprint mismatch",
            )
            return None

        # Record successful usage
        kiosk_token.record_usage(self._get_client_ip(request))

        # Log successful auto-reauth
        KioskAccessLog.objects.create(
            kiosk_token=kiosk_token,
            token_value=token_value[:64],
            ip_address=self._get_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:256],
            device_fingerprint=fingerprint_hash[:64],
            status="success",
            details="Auto-reauth via middleware",
        )
        # Note: Consider implementing rate limiting for success logs if database
        # growth becomes an issue (e.g., log once per session vs every request)

        return kiosk_token.user

    def _get_client_ip(self, request):
        """Extract client IP address from request, handling proxies."""
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
