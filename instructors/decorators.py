# instructors/decorators.py
from functools import wraps
from django.shortcuts import get_object_or_404, render, redirect
from members.models import Member
from members.constants.membership import ALLOWED_MEMBERSHIP_STATUSES
from django.http import HttpResponseForbidden

def instructor_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # ✅ Allow all superusers
        if user.is_superuser:
            return view_func(request, *args, **kwargs)

        if getattr(user, "membership_status", None) not in ALLOWED_MEMBERSHIP_STATUSES:
            return render(request, "403.html", status=403)

        if not getattr(user, "instructor", False):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper



def member_or_instructor_required(view_func):
    @wraps(view_func)
    def wrapper(request, member_id, *args, **kwargs):
        member = get_object_or_404(Member, pk=member_id)
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # ✅ Allow superusers
        if user.is_superuser:
            return view_func(request, member_id, *args, **kwargs)

        if getattr(user, "membership_status", None) not in ALLOWED_MEMBERSHIP_STATUSES:
            return render(request, "403.html", status=403)

        if user == member or getattr(user, "instructor", False):
            return view_func(request, member_id, *args, **kwargs)

        return render(request, "403.html", status=403)

    return wrapper