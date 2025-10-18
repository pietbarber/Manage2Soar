import base64
import os
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import F, Func, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from cms.models import HomePageContent
from instructors.models import MemberQualification
from members.constants.membership import DEFAULT_ACTIVE_STATUSES, STATUS_ALIASES

from .decorators import active_member_required
from .forms import BiographyForm, MemberProfilePhotoForm, SetPasswordForm
from .models import Badge, Biography, Member, MemberBadge
from .utils.vcard_tools import generate_vcard_qr

#########################
# member_list() View

# Renders a list of all members, typically grouped or filtered by membership
# status or role (e.g., instructor, tow pilot, director). Intended for logged-in
# users.

# Can be used to browse, link to member profiles, or assign operational roles.


@active_member_required
def member_list(request):
    selected_statuses = request.GET.getlist("status")

    raw_statuses = request.GET.getlist("status")

    # If no status selected, default to "Active"
    if not raw_statuses:
        raw_statuses = ["active"]

    selected_statuses = []
    for s in raw_statuses:
        selected_statuses.extend(STATUS_ALIASES.get(s, [s]))

    members = Member.objects.filter(membership_status__in=selected_statuses)

    selected_roles = request.GET.getlist("role")
    if "towpilot" in selected_roles:
        members = members.filter(towpilot=True)
    if "instructor" in selected_roles:
        members = members.filter(instructor=True)
    if "director" in selected_roles:
        members = members.filter(director=True)
    if "dutyofficer" in selected_roles:
        members = members.filter(duty_officer=True)

    members = members.annotate(
        last_name_lower=Func(F("last_name"), function="LOWER")
    ).order_by("last_name_lower", "first_name")

    paginator = Paginator(members, 150)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "members/member_list.html",
        {
            "page_obj": page_obj,
            "paginator": paginator,
            "members": page_obj.object_list,
            "selected_statuses": selected_statuses,
            "selected_roles": selected_roles,
        },
    )


#########################
# member_view() View
#
# Renders the detail page for a specific member. The page displays profile
# details such as roles, contact info, badges, the member's QR code, the
# biography, qualifications, and (when applicable) solo/checkride buttons.
# Access is restricted via the @active_member_required decorator.
#
# Context passed to the template includes:
# - member, show_need_buttons, qr_base64, form, is_self, can_edit,
#   biography, qualifications, and today
#
#########################


@active_member_required
def member_view(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    is_self = request.user == member
    can_edit = is_self or request.user.is_superuser

    # Decide whether to show solo/checkride buttons
    show_need_buttons = member.glider_rating not in ("private", "commercial")

    # Biography logic
    biography = getattr(member, "biography", None)

    # QR code generation
    qr_png = generate_vcard_qr(member)
    qr_base64 = base64.b64encode(qr_png).decode("utf-8")

    qualifications = (
        MemberQualification.objects.filter(member=member, is_qualified=True)
        .select_related("qualification", "instructor")
        .order_by("qualification__code")
    )

    if is_self and request.method == "POST":
        form = MemberProfilePhotoForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile photo updated.")
            return redirect("members:member_view", member_id=member.id)
    else:
        form = MemberProfilePhotoForm(instance=member) if is_self else None

    context = {
        "member": member,
        "qr_base64": qr_base64,
        "form": form,
        "is_self": is_self,
        "can_edit": can_edit,
        "biography": biography,
        "qualifications": qualifications,
        "today": date.today(),
        # new flag for template
        "show_need_buttons": show_need_buttons,
        "pilot_certificate_number": member.pilot_certificate_number,
        "private_glider_checkride_date": member.private_glider_checkride_date,
    }

    template = "members/member_view.html"
    return render(request, template, context)


#########################
# biography_view() View

# Displays the HTML biography of a given member, if one exists.
# Supports optional image uploads and rich text formatting.

# Variables:
# - username: slug used to identify the member
# - member: the Member object matching the username
# - biography: associated Biography model object for the member, if present

# Raises:
# - Http404 if the member or biography does not exist


@active_member_required
def biography_view(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    biography, _ = Biography.objects.get_or_create(member=member)

    can_edit = request.user == member or request.user.is_superuser

    if request.method == "POST" and can_edit:
        form = BiographyForm(request.POST, request.FILES, instance=biography)
        if form.is_valid():
            form.save()
            return redirect("members:member_view", member_id=member.id)
    else:
        form = BiographyForm(instance=biography)

    return render(
        request,
        "members/biography.html",
        {
            "form": form,
            "biography": biography,
            "member": member,
            "can_edit": can_edit,
        },
    )


#########################
# home() View
#
# Renders the homepage template (home.html). This view handles the root URL
# ("/") and requires no authentication. It also provides the count of pending
# written tests assigned to the current user as 'pending_tests_count'.
#
# Defined in members/views.py and mapped in the project-wide urls.py:
#     path("", member_views.home, name="home")
#
# Future enhancements may include turning this into a full dashboard,
# displaying pending tests, recent instruction reports, and other user-specific
# data.


def home(request):
    pending_count = 0
    if request.user.is_authenticated:
        pending_count = request.user.assigned_written_tests.filter(
            completed=False
        ).count()
    # Fetch homepage content (latest)
    homepage_content = HomePageContent.objects.order_by("-updated_at").first()
    return render(
        request,
        "home.html",
        {
            "pending_tests_count": pending_count,
            "homepage_content": homepage_content,
        },
    )


#########################
# set_password() View

# Allows a logged-in user to set or change their password. This is typically
# used when a member is transitioning from OAuth or legacy authentication
# to a Django-managed password.

# Methods:
# - GET: renders a password change form
# - POST: processes the password form and saves the new password

# Variables:
# - form: instance of PasswordChangeForm bound to the logged-in user
# - messages.success: displays a confirmation if the password is successfully changed

# Redirects to home page on success.


@active_member_required
def set_password(request):
    member = request.user
    if request.method == "POST":
        form = SetPasswordForm(request.POST)
        if form.is_valid():
            member.set_password(form.cleaned_data["new_password1"])
            member.save()
            messages.success(request, "Password changed successfully.")
            return redirect("members:member_list")
    else:
        form = SetPasswordForm()
    return render(request, "members/set_password.html", {"form": form})


#########################
# tinymce_image_upload() View

# Handles image uploads via TinyMCE's file picker. Stores images under
# media/biography/<username>/ for the currently logged-in user.

# Methods:
# - POST: accepts an image file uploaded from the TinyMCE editor

# Variables:
# - image: the uploaded file from the POST request
# - fs: Django FileSystemStorage instance targeting the user's biography folder
# - filename: saved filename with a sanitized name
# - url: public URL to the uploaded image

# Returns a JSON response containing the file URL for use in the editor.
# Only accessible to logged-in users.


@active_member_required
@csrf_exempt
def tinymce_image_upload(request):
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]
        # Save to 'tinymce/<filename>' in the default storage (GCS or local)
    save_path = os.path.join("tinymce", f.name)
    saved_name = default_storage.save(save_path, ContentFile(f.read()))
    # Always return the public GCS URL
    from urllib.parse import urljoin

    url = urljoin(settings.MEDIA_URL, saved_name)
    return JsonResponse({"location": url})

    # Fallback error response (should be unreachable because of the early return)
    return JsonResponse({"error": "Invalid request"}, status=400)


#########################
# badge_board() View

# Displays a public-facing badge leaderboard showing members and their earned badges.
# Members are typically grouped or ranked by the number of badges, categories, or date awarded.

# Only accessible to logged-in users.

# Variables:
# - members: queryset of all members, prefetching badge relationships


@active_member_required
def badge_board(request):
    active_members = Member.objects.filter(
        membership_status__in=DEFAULT_ACTIVE_STATUSES
    )

    badges = Badge.objects.prefetch_related(
        Prefetch(
            "memberbadge_set",
            queryset=MemberBadge.objects.filter(member__in=active_members)
            .select_related("member")
            .order_by("member__last_name", "member__first_name"),
            to_attr="filtered_memberbadges",
        )
    ).order_by("order")

    return render(request, "members/badges.html", {"badges": badges})
