from functools import wraps

from django.contrib import messages
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
