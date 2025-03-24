from django.core.exceptions import PermissionDenied
from functools import wraps

def active_member_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("You must be logged in.")
        if request.user.membership_status in ["Non-Member", "Inactive"]:
            raise PermissionDenied("Your account is not currently active.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
