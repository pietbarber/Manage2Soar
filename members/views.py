import base64
import os
from datetime import date, timedelta
from django.utils import timezone
import re

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
from members.utils import can_view_personal_info as can_view_personal_info_fn
from members.utils import is_privileged_viewer
from django.urls import reverse

try:
    from notifications.models import Notification
except Exception:
    Notification = None

#########################
# member_list() View

# Renders a list of all members, typically grouped or filtered by membership status
# or role (e.g., instructor, tow pilot, director). Intended for logged-in users.

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
# Renders the detail page for a specific member.
# Displays member profile details including roles, contact info, badges,
# QR code, biography, qualifications, and solo/checkride need buttons when applicable.
# Access restricted to active members via @active_member_required.
#
# Arguments:
# - request: the HTTP request object
# - member_id: the primary key of the Member object to display
#
# Context Variables Provided to Template:
# - member: Member instance
# - show_need_buttons: bool indicating whether to display solo/checkride buttons
# - qr_base64: Base64-encoded QR code for vCard download
# - form: MemberProfilePhotoForm instance (if editing own profile) or None
# - is_self: bool, True if the viewer is the member
# - can_edit: bool, True if the user can edit this profile
# - biography: MemberBiography instance or None
# - qualifications: QuerySet of MemberQualification objects
# - today: current date
#
# Raises:
# - Http404 if no Member exists with the given member_id
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

    # Determine whether the requester can view personal info, and generate
    # a QR code accordingly (redacted QR omits contact fields).
    can_view_personal = can_view_personal_info_fn(request.user, member)
    qr_png = generate_vcard_qr(member, include_contact=can_view_personal)
    qr_base64 = base64.b64encode(qr_png).decode("utf-8")

    # Compute phone/mobile display values. Use the canonical can_view_personal
    # check (which includes member self, staff, and privileged viewers).
    phone_display = member.phone if member.phone and can_view_personal else None
    phone_link = bool(phone_display)

    mobile_display = member.mobile_phone if member.mobile_phone and can_view_personal else None
    mobile_link = bool(mobile_display)

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
        "can_view_personal_info": can_view_personal,
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
        "phone_display": phone_display,
        "phone_link": phone_link,
        "mobile_display": mobile_display,
        "mobile_link": mobile_link,
    }
    return render(request, "members/member_view.html", context)


@active_member_required
def toggle_redaction(request, member_id):
    """Toggle the redact_contact flag for a member.

    Only the member themselves or a superuser may perform this action.
    The view accepts POST requests from the member profile form and redirects
    back to the member view after updating the flag.
    """
    member = get_object_or_404(Member, pk=member_id)

    # Only the member themselves or superusers may toggle this flag
    if request.user != member and not request.user.is_superuser:
        return render(request, "403.html", status=403)

    if request.method == "POST":
        member.redact_contact = not member.redact_contact
        member.save()
        # Create a notification for all member_managers so they are aware
        # that a member has toggled their redaction flag.
        try:
            if Notification is not None:
                # Build a human-friendly message. If the actor is the member themself
                # we phrase it as 'Member X has hidden...'; if an admin toggled for
                # someone else we include both actor and subject.
                if request.user == member:
                    actor_name = member.full_display_name
                    action = "hidden" if member.redact_contact else "made visible"
                    message = f"Member {actor_name} has {action} their personal contact information on the members site."
                else:
                    actor_name = request.user.full_display_name
                    subject_name = member.full_display_name
                    action = "hidden" if member.redact_contact else "made visible"
                    message = f"{actor_name} has {action} personal contact information for member {subject_name}."

                url = request.build_absolute_uri(
                    reverse("members:member_view", kwargs={"member_id": member.id}))

                # Notify every user with member_manager privilege, but dedupe
                # so we don't spam them if the same member toggles repeatedly.


                # Notify member managers so club managers
                # are alerted when a member toggles redaction.
                member_managers = Member.objects.filter(member_manager=True)
                # Dedupe window: configurable via settings.REDACTION_NOTIFICATION_DEDUPE_MINUTES
                # (integer minutes). For backward compatibility, a settings value
                # REDACTION_NOTIFICATION_DEDUPE_HOURS may be provided. Default = 60 minutes.
                cutoff = None
                # Prefer SiteConfiguration value when available
                try:
                    from siteconfig.models import SiteConfiguration

                    sc = SiteConfiguration.objects.first()
                    if sc and getattr(sc, "redaction_notification_dedupe_minutes", None):
                        cutoff = timezone.now() - timedelta(minutes=int(sc.redaction_notification_dedupe_minutes))
                except Exception:
                    sc = None

                if cutoff is None:
                    try:
                        minutes = getattr(
                            settings, "REDACTION_NOTIFICATION_DEDUPE_MINUTES", None)
                        if minutes is not None:
                            cutoff = timezone.now() - timedelta(minutes=int(minutes))
                        else:
                            hours = getattr(
                                settings, "REDACTION_NOTIFICATION_DEDUPE_HOURS", 1)
                            cutoff = timezone.now() - timedelta(hours=float(hours))
                    except Exception:
                        cutoff = timezone.now() - timedelta(hours=1)
                for rm in member_managers:
                    try:
                        # If a recent notification exists for this recipient and URL,
                        # skip creating another one.
                        exists = Notification.objects.filter(
                            user=rm, url=url, created_at__gte=cutoff
                        ).exists()
                        if exists:
                            continue
                        Notification.objects.create(user=rm, message=message, url=url)
                    except Exception:
                        # Fail softly if notification creation fails for any recipient
                        continue
        except Exception:
            # Defensive: don't let notification failures break the toggle flow
            pass
        if member.redact_contact:
            messages.success(
                request, "Your personal contact information is now redacted.")
        else:
            messages.success(
                request, "Your personal contact information is now visible to other members.")

    return redirect("members:member_view", member_id=member.id)


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
        {"form": form, "biography": biography, "member": member, "can_edit": can_edit},
    )


#########################
# home() View
#
# Renders the homepage template (home.html). This view handles the root URL ("/")
# and requires no authentication to access. It now also calculates and provides
# the count of pending written tests assigned to the current user as
# 'pending_tests_count' in the template context.
#
# Defined in members/views.py and mapped in the project-wide urls.py:
#     path("", member_views.home, name="home")
#
# Future enhancements may include turning this into a full dashboard,
# displaying pending tests, recent instruction reports, and other user-specific data.


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
    # Only accept POSTs with a file named 'file'
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]
        # Save to 'tinymce/<filename>' in the default storage (GCS or local)
        save_path = os.path.join("tinymce", f.name)
        saved_name = default_storage.save(save_path, ContentFile(f.read()))
        # Always return the public GCS URL
        from urllib.parse import urljoin

        url = urljoin(settings.MEDIA_URL, saved_name)
        return JsonResponse({"location": url})

    # For any other request method or missing file, return an error
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
