"""
Custom middleware for health checks and other utilities.
"""

from django.conf import settings
from django.http import HttpResponse


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
