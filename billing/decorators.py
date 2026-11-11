from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from siteconfig.models import SiteConfiguration


def billing_app_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not SiteConfiguration.objects.filter(billing_app_enabled=True).exists():
            messages.info(request, "Billing is disabled for this site.")
            return redirect("/")
        return view_func(request, *args, **kwargs)

    return wrapper


def treasurer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_superuser or request.user.treasurer):
            return HttpResponseForbidden("Treasurer access is required.")
        return view_func(request, *args, **kwargs)

    return wrapper


def club_accounting_required(view_func):
    """Send treasurers back to Member Billing while the club books are off."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not SiteConfiguration.objects.filter(
            billing_app_enabled=True, club_accounting_enabled=True
        ).exists():
            messages.info(
                request,
                "Club accounting is disabled. Enable it in Site Configuration.",
            )
            return redirect("billing:ledger_list")
        return view_func(request, *args, **kwargs)

    return wrapper
