# instructors/decorators.py
from functools import wraps
from django.shortcuts import redirect, render

def instructor_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # ✅ Allow all superusers
        if user.is_superuser:
            return view_func(request, *args, **kwargs)

        allowed_statuses = [
            "Full Member", "Student Member", "Family Member", "Service Member",
            "Founding Member", "Honorary Member", "Emeritus Member",
            "SSEF Member", "Temporary Member", "Introductory Member"
        ]

        if getattr(user, "membership_status", None) not in allowed_statuses:
            return render(request, "403.html", status=403)

        if not getattr(user, "instructor", False):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper
