# instructors/decorators.py
from functools import wraps

from django.shortcuts import get_object_or_404, redirect, render

from members.models import Member
from members.utils import is_active_member

####################################################
# instructor_required
#
# Decorator to restrict view access to authenticated instructors.
# Allows superusers, then checks:
# - membership_status in ALLOWED_MEMBERSHIP_STATUSES
# - user.instructor flag True
# Redirects unauthenticated users to login;
# renders 403.html for forbidden access.
#
# Usage:
# @instructor_required
# def my_view(request, ...):
#     ...
####################################################


def instructor_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # Centralized check which handles superuser logic and statuses
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        if not getattr(user, "instructor", False):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


####################################################
# member_or_instructor_required
#
# Decorator to restrict view access to either:
# - the member matching member_id URL arg
# - any instructor (or superuser)
# Ensures authenticated, valid membership, then
# checks user == member or user.instructor.
# Redirects unauthenticated to login;
# renders 403.html for forbidden access.
#
# Usage:
# @member_or_instructor_required
# def my_view(request, member_id, ...):
#     ...
####################################################


def member_or_instructor_required(view_func):
    @wraps(view_func)
    def wrapper(request, member_id, *args, **kwargs):
        member = get_object_or_404(Member, pk=member_id)
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # Centralized check which handles superuser logic and statuses
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        if user == member or getattr(user, "instructor", False):
            return view_func(request, member_id, *args, **kwargs)

        return render(request, "403.html", status=403)

    return wrapper


####################################################
# instructor_or_safety_officer_required
#
# Decorator to restrict view access to instructors or safety officers.
# Allows superusers, then checks:
# - membership_status in ALLOWED_MEMBERSHIP_STATUSES
# - user.instructor flag True OR user.safety_officer flag True
# Redirects unauthenticated users to login;
# renders 403.html for forbidden access.
#
# Usage:
# @instructor_or_safety_officer_required
# def my_view(request, ...):
#     ...
####################################################


def instructor_or_safety_officer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # Superusers always have access
        if user.is_superuser:
            return view_func(request, *args, **kwargs)

        # Centralized check which handles active membership statuses
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        # Check if user has instructor or safety_officer flag
        if not (
            getattr(user, "instructor", False) or getattr(user, "safety_officer", False)
        ):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper
