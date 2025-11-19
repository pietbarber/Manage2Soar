"""
Health check views for Kubernetes and load balancer monitoring
"""

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt


class HealthCheckView(View):
    """
    Health check endpoint that always returns HTTP 200 OK
    Used by Kubernetes/GKE load balancer health checks
    """

    @method_decorator(csrf_exempt)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return HttpResponse("OK", content_type="text/plain", status=200)

    def post(self, request):
        return HttpResponse("OK", content_type="text/plain", status=200)

    def head(self, request):
        return HttpResponse("", content_type="text/plain", status=200)


# Simple function view as backup
@csrf_exempt
@never_cache
def health_check(request):
    """Simple health check that returns OK"""
    return HttpResponse("OK", content_type="text/plain", status=200)
