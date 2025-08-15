from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from members.constants.membership import DEFAULT_ACTIVE_STATUSES  # ✅ single source of truth

def is_active_member(user):
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return getattr(user, "membership_status", None) in DEFAULT_ACTIVE_STATUSES

@user_passes_test(is_active_member, login_url="login")
def dashboard(request):
    ctx = {
        "year": request.GET.get("year", ""),
        "user_name": getattr(request.user, "full_display_name", request.user.get_username()),
    }
    return render(request, "analytics/dashboard.html", ctx)
