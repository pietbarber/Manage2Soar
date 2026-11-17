# instructors/decorators.py
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import get_object_or_404, redirect, render

from members.authorization import (
    can_manage_ground_instruction,
    has_bulk_qualification_access,
    has_syllabus_edit_access,
    has_training_record_access,
    has_training_record_action,
)
from members.models import Member
from members.utils import is_active_member

####################################################
# instructor_required
#
# Restrict instructor-facing read views to members who can view training
# records, retaining the legacy instructor fallback in the authorization
# helper.
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
            return redirect_to_login(request.get_full_path())

        # Centralized check which handles superuser logic and statuses
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        if not has_training_record_access(user):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


def training_record_action_required(view_func):
    """Require permission to create or update training records."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if not is_active_member(user) or not has_training_record_action(user):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


def syllabus_document_edit_required(view_func):
    """Require syllabus edit permission or the legacy instructor role."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if not is_active_member(user):
            return render(request, "403.html", status=403)

        if not has_syllabus_edit_access(user):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


def ground_instruction_required(view_func):
    """Require the scoped ground-instruction capability or legacy instructor role."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if not can_manage_ground_instruction(user):
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
            return redirect_to_login(request.get_full_path())

        # Centralized check which handles superuser logic and statuses
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        if user == member or has_training_record_access(user):
            return view_func(request, member_id, *args, **kwargs)

        return render(request, "403.html", status=403)

    return wrapper


####################################################
# instructor_or_safety_officer_required
#
# Restrict bulk qualification assignment to its dedicated capability or the
# legacy instructor/safety-officer roles.
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
            return redirect_to_login(request.get_full_path())

        # Superusers always have access
        if user.is_superuser:
            return view_func(request, *args, **kwargs)

        # Centralized check which handles active membership statuses
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        # Instructors retain their existing role behavior; safety access is an
        # explicit capability rather than a legacy boolean authorization read.
        if not has_bulk_qualification_access(user):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper
