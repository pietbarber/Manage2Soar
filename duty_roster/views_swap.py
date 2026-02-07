"""
Views for Duty Swap Request and Offer functionality.

These views handle the workflow for duty crew members to request coverage
for their scheduled duties and for other members to offer help.
"""

import logging
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.db import models, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from members.decorators import active_member_required
from members.models import Member
from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title
from utils.email import get_dev_mode_info, send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import get_canonical_url

from .forms import DutySwapOfferForm, DutySwapRequestForm
from .models import DutyAssignment, DutySwapOffer, DutySwapRequest, MemberBlackout
from .utils.ics import generate_swap_ics

logger = logging.getLogger("duty_roster.views_swap")


def get_scheduling_config():
    """Get site config flags for which roles are scheduled."""
    config = SiteConfiguration.objects.first()
    if not config:
        return {
            "INSTRUCTOR": False,
            "TOW": False,
            "DO": False,
            "ADO": False,
        }
    return {
        "INSTRUCTOR": config.schedule_instructors,
        "TOW": config.schedule_tow_pilots,
        "DO": config.schedule_duty_officers,
        "ADO": config.schedule_assistant_duty_officers,
    }


def is_role_scheduled(role):
    """Check if a role is scheduled (swap requests allowed)."""
    return get_scheduling_config().get(role, False)


def get_eligible_members_for_role(role, exclude_member=None):
    """Get members who are eligible to fill a specific role."""
    role_attr_map = {
        "DO": "duty_officer",
        "ADO": "assistant_duty_officer",
        "INSTRUCTOR": "instructor",
        "TOW": "towpilot",
    }
    role_attr = role_attr_map.get(role)

    if not role_attr:
        return Member.objects.none()

    queryset = Member.objects.filter(
        **{role_attr: True}, membership_status__in=["Full Member", "Family Member"]
    )

    if exclude_member:
        queryset = queryset.exclude(pk=exclude_member.pk)

    return queryset


# =============================================================================
# SWAP REQUEST VIEWS
# =============================================================================


@active_member_required
def create_swap_request(request, year, month, day, role):
    """Create a new swap request for a specific duty date and role."""
    duty_date = date(year, month, day)
    today = timezone.now().date()

    # Validate the role
    if role not in dict(DutySwapRequest.ROLE_CHOICES):
        messages.error(request, "Invalid role specified.")
        return redirect("duty_roster:duty_calendar")

    # Check if this role is scheduled (not ad-hoc)
    if not is_role_scheduled(role):
        role_title = get_role_title(
            {
                "DO": "duty_officer",
                "ADO": "assistant_duty_officer",
                "INSTRUCTOR": "instructor",
                "TOW": "towpilot",
            }.get(role, role)
        )
        messages.error(
            request,
            f"{role_title} is not scheduled ahead of time. "
            "Swap requests are only available for scheduled roles.",
        )
        return redirect("duty_roster:duty_calendar")

    # Validate date is in the future
    if duty_date < today:
        messages.error(request, "Cannot create swap request for past dates.")
        return redirect("duty_roster:duty_calendar")

    # Check if there's an existing open request
    existing = DutySwapRequest.objects.filter(
        requester=request.user, original_date=duty_date, role=role, status="open"
    ).first()

    if existing:
        messages.info(request, "You already have an open request for this duty.")
        return redirect("duty_roster:my_swap_requests")

    # Verify the user is actually assigned this role on this date
    assignment = DutyAssignment.objects.filter(date=duty_date).first()
    if assignment:
        role_field_map = {
            "DO": "duty_officer",
            "ADO": "assistant_duty_officer",
            "INSTRUCTOR": "instructor",
            "TOW": "tow_pilot",
        }
        role_field = role_field_map.get(role)
        if not role_field:
            messages.error(request, "Invalid role specified.")
            return redirect("duty_roster:duty_calendar")
        assigned_member = getattr(assignment, role_field, None)
        if assigned_member != request.user:
            messages.error(request, "You are not assigned this role on this date.")
            return redirect("duty_roster:duty_calendar")
    else:
        messages.error(request, "No duty assignment exists for this date.")
        return redirect("duty_roster:duty_calendar")

    if request.method == "POST":
        form = DutySwapRequestForm(
            request.POST, role=role, date=duty_date, requester=request.user
        )
        if form.is_valid():
            swap_request = form.save()

            # Send notification emails
            send_swap_request_notifications(swap_request)

            messages.success(
                request,
                "Your swap request has been created. "
                "Eligible members have been notified.",
            )
            return redirect("duty_roster:my_swap_requests")
    else:
        # Pre-check if this is less than 48 hours out
        days_until = (duty_date - today).days
        initial = {"is_emergency": days_until <= 2}
        form = DutySwapRequestForm(
            role=role, date=duty_date, requester=request.user, initial=initial
        )

    role_title = get_role_title(
        {
            "DO": "duty_officer",
            "ADO": "assistant_duty_officer",
            "INSTRUCTOR": "instructor",
            "TOW": "towpilot",
        }.get(role, role)
    )

    context = {
        "form": form,
        "duty_date": duty_date,
        "role": role,
        "role_title": role_title,
        "days_until": (duty_date - today).days,
    }
    return render(request, "duty_roster/swap/create_request.html", context)


@active_member_required
def my_swap_requests(request):
    """View all swap requests created by the current user."""
    member = request.user
    today = timezone.now().date()

    # Get all requests by this user
    open_requests = DutySwapRequest.objects.filter(
        requester=member, status="open"
    ).prefetch_related("offers", "offers__offered_by")

    # Get past/resolved requests
    resolved_requests = DutySwapRequest.objects.filter(requester=member).exclude(
        status="open"
    )[:10]

    context = {
        "open_requests": open_requests,
        "resolved_requests": resolved_requests,
        "today": today,
    }
    return render(request, "duty_roster/swap/my_requests.html", context)


@active_member_required
def open_swap_requests(request):
    """View all open swap requests that the user could help with."""
    member = request.user
    today = timezone.now().date()

    # Get open requests from other members
    # Exclude requests where user already made an offer
    open_requests = (
        DutySwapRequest.objects.filter(status="open", original_date__gte=today)
        .exclude(requester=member)
        .exclude(offers__offered_by=member)
        .prefetch_related("offers")
        .select_related("requester")
    )

    # Filter to roles the user is qualified for
    qualified_roles = []
    if member.instructor:
        qualified_roles.append("INSTRUCTOR")
    if member.towpilot:
        qualified_roles.append("TOW")
    if member.duty_officer:
        qualified_roles.append("DO")
    if member.assistant_duty_officer:
        qualified_roles.append("ADO")

    if qualified_roles:
        open_requests = open_requests.filter(role__in=qualified_roles)
    else:
        open_requests = open_requests.none()

    # Also filter: if direct request, only show to the target member
    open_requests = open_requests.filter(
        models.Q(request_type="general") | models.Q(direct_request_to=member)
    )

    context = {
        "open_requests": open_requests,
        "today": today,
    }
    return render(request, "duty_roster/swap/open_requests.html", context)


@active_member_required
def swap_request_detail(request, request_id):
    """View details of a specific swap request."""
    swap_request = get_object_or_404(DutySwapRequest, pk=request_id)
    member = request.user

    # Check if user can view this request
    is_requester = swap_request.requester == member
    is_offerer = swap_request.offers.filter(offered_by=member).exists()
    is_eligible = member in get_eligible_members_for_role(
        swap_request.role, exclude_member=swap_request.requester
    )
    is_target = swap_request.direct_request_to == member

    if (
        not is_requester
        and not is_offerer
        and not is_eligible
        and not is_target
        and not member.is_staff
    ):
        messages.error(request, "You don't have permission to view this request.")
        return redirect("duty_roster:duty_calendar")

    # Check for blackout conflicts on any swap offers
    for offer in swap_request.offers.filter(offer_type="swap"):
        if offer.proposed_swap_date:
            offer.has_blackout_conflict = MemberBlackout.objects.filter(
                member=swap_request.requester, date=offer.proposed_swap_date
            ).exists()

    context = {
        "swap_request": swap_request,
        "is_requester": is_requester,
        "is_offerer": is_offerer,
        "is_eligible": is_eligible,
        "can_make_offer": is_eligible
        and not is_offerer
        and swap_request.status == "open",
        "today": timezone.now().date(),
    }
    return render(request, "duty_roster/swap/request_detail.html", context)


@active_member_required
@require_POST
def cancel_swap_request(request, request_id):
    """Cancel an open swap request."""
    swap_request = get_object_or_404(DutySwapRequest, pk=request_id)

    if swap_request.requester != request.user:
        return HttpResponseForbidden("You can only cancel your own requests.")

    if swap_request.status != "open":
        messages.error(request, "This request is no longer open.")
        return redirect("duty_roster:my_swap_requests")

    with transaction.atomic():
        swap_request.status = "cancelled"
        swap_request.save()

        # Notify all offerers
        for offer in swap_request.offers.filter(status="pending"):
            offer.status = "declined"
            offer.responded_at = timezone.now()
            offer.save()

        send_request_cancelled_notifications(swap_request)

    messages.success(request, "Your swap request has been cancelled.")
    return redirect("duty_roster:my_swap_requests")


@active_member_required
@require_POST
def convert_to_general(request, request_id):
    """Convert a direct request to a general broadcast."""
    swap_request = get_object_or_404(DutySwapRequest, pk=request_id)

    if swap_request.requester != request.user:
        return HttpResponseForbidden("You can only modify your own requests.")

    if swap_request.status != "open":
        messages.error(request, "This request is no longer open.")
        return redirect("duty_roster:my_swap_requests")

    if swap_request.request_type != "direct":
        messages.info(request, "This request is already a general broadcast.")
        return redirect("duty_roster:swap_request_detail", request_id=request_id)

    swap_request.request_type = "general"
    swap_request.direct_request_to = None
    swap_request.save()

    # Send notifications to all eligible members
    send_swap_request_notifications(swap_request)

    messages.success(
        request,
        "Your request has been converted to a general broadcast. "
        "All eligible members have been notified.",
    )
    return redirect("duty_roster:swap_request_detail", request_id=request_id)


# =============================================================================
# SWAP OFFER VIEWS
# =============================================================================


@active_member_required
def make_offer(request, request_id):
    """Make an offer to help with a swap request."""
    swap_request = get_object_or_404(DutySwapRequest, pk=request_id)
    member = request.user

    if swap_request.status != "open":
        messages.error(request, "This request is no longer accepting offers.")
        return redirect("duty_roster:open_swap_requests")

    if swap_request.requester == member:
        messages.error(request, "You cannot make an offer on your own request.")
        return redirect("duty_roster:my_swap_requests")

    # Check if user already made an offer
    existing_offer = swap_request.offers.filter(offered_by=member).first()
    if existing_offer:
        messages.info(request, "You have already made an offer for this request.")
        return redirect("duty_roster:swap_request_detail", request_id=request_id)

    # Check if user is eligible for this role
    if member not in get_eligible_members_for_role(
        swap_request.role, exclude_member=swap_request.requester
    ):
        messages.error(request, "You are not qualified for this role.")
        return redirect("duty_roster:open_swap_requests")

    if request.method == "POST":
        form = DutySwapOfferForm(
            request.POST, swap_request=swap_request, offered_by=member
        )
        if form.is_valid():
            offer = form.save()

            # Notify requester
            send_offer_made_notification(offer)

            messages.success(
                request,
                f"Your offer has been sent to {swap_request.requester.first_name}!",
            )
            return redirect("duty_roster:swap_request_detail", request_id=request_id)
    else:
        form = DutySwapOfferForm(swap_request=swap_request, offered_by=member)

    context = {
        "form": form,
        "swap_request": swap_request,
    }
    return render(request, "duty_roster/swap/make_offer.html", context)


@active_member_required
@require_POST
def accept_offer(request, offer_id):
    """Accept an offer - completes the swap/cover."""
    offer = get_object_or_404(DutySwapOffer, pk=offer_id)
    swap_request = offer.swap_request

    if swap_request.requester != request.user:
        return HttpResponseForbidden("You can only accept offers on your own requests.")

    if swap_request.status != "open":
        messages.error(request, "This request is no longer open.")
        return redirect("duty_roster:my_swap_requests")

    if offer.status != "pending":
        messages.error(request, "This offer is no longer available.")
        return redirect("duty_roster:swap_request_detail", request_id=swap_request.pk)

    with transaction.atomic():
        # Accept this offer
        offer.status = "accepted"
        offer.responded_at = timezone.now()
        offer.save()

        # Mark request as fulfilled
        swap_request.status = "fulfilled"
        swap_request.accepted_offer = offer
        swap_request.fulfilled_at = timezone.now()
        swap_request.save()

        # Auto-decline other pending offers
        other_offers = swap_request.offers.filter(status="pending").exclude(pk=offer.pk)
        for other in other_offers:
            other.status = "auto_declined"
            other.responded_at = timezone.now()
            other.save()

        # Update duty assignments
        update_duty_assignments(swap_request, offer)

        # Send notifications
        send_offer_accepted_notifications(offer)

        for other in other_offers:
            send_offer_declined_notification(other, auto=True)

    messages.success(
        request,
        f"Swap completed! {offer.offered_by.first_name} will cover your duty "
        f"on {swap_request.original_date.strftime('%B %d')}.",
    )
    return redirect("duty_roster:my_swap_requests")


@active_member_required
@require_POST
def decline_offer(request, offer_id):
    """Decline an offer."""
    offer = get_object_or_404(DutySwapOffer, pk=offer_id)
    swap_request = offer.swap_request

    if swap_request.requester != request.user:
        return HttpResponseForbidden(
            "You can only decline offers on your own requests."
        )

    if offer.status != "pending":
        messages.error(request, "This offer is no longer pending.")
        return redirect("duty_roster:swap_request_detail", request_id=swap_request.pk)

    offer.status = "declined"
    offer.responded_at = timezone.now()
    offer.save()

    send_offer_declined_notification(offer, auto=False)

    messages.success(
        request, f"You have declined {offer.offered_by.first_name}'s offer."
    )
    return redirect("duty_roster:swap_request_detail", request_id=swap_request.pk)


@active_member_required
@require_POST
def decline_swap_request(request, request_id):
    """Decline a swap request (for direct requests only)."""
    swap_request = get_object_or_404(DutySwapRequest, pk=request_id)
    member = request.user

    # Only the target of a direct request can decline
    if swap_request.direct_request_to != member:
        return HttpResponseForbidden("You can only decline requests sent to you.")

    if swap_request.status != "open":
        messages.error(request, "This request is no longer open.")
        return redirect("duty_roster:open_swap_requests")

    # Automatically convert to general request so others can see it
    swap_request.direct_request_to = None
    swap_request.request_type = "general"
    swap_request.save()

    # Notify the requester that this member declined
    send_request_declined_by_member_notification(swap_request, member)

    # Notify all other eligible members about the now-general request
    send_swap_request_notifications(swap_request)

    messages.success(
        request,
        f"You have declined {swap_request.requester.first_name}'s request. "
        "It has been converted to a general request so other members can help.",
    )
    return redirect("duty_roster:open_swap_requests")


@active_member_required
@require_POST
def withdraw_offer(request, offer_id):
    """Withdraw an offer you made."""
    offer = get_object_or_404(DutySwapOffer, pk=offer_id)

    if offer.offered_by != request.user:
        return HttpResponseForbidden("You can only withdraw your own offers.")

    if offer.status != "pending":
        messages.error(request, "This offer is no longer pending.")
        return redirect(
            "duty_roster:swap_request_detail", request_id=offer.swap_request.pk
        )

    offer.status = "withdrawn"
    offer.responded_at = timezone.now()
    offer.save()

    messages.success(request, "Your offer has been withdrawn.")
    return redirect("duty_roster:open_swap_requests")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def update_duty_assignments(swap_request, offer):
    """Update duty assignments after a swap/cover is accepted."""
    role_field_map = {
        "DO": "duty_officer",
        "ADO": "assistant_duty_officer",
        "INSTRUCTOR": "instructor",
        "TOW": "tow_pilot",
    }
    field_name = role_field_map.get(swap_request.role)

    if not field_name:
        logger.error(f"Unknown role: {swap_request.role}")
        return

    # Update original date: offerer takes over
    original_assignment = DutyAssignment.objects.filter(
        date=swap_request.original_date
    ).first()
    if original_assignment:
        setattr(original_assignment, field_name, offer.offered_by)
        original_assignment.save()
        logger.info(
            f"Updated {swap_request.original_date}: {field_name} = {offer.offered_by}"
        )

    # If it's a swap (not just cover), also update the swap date
    if offer.offer_type == "swap" and offer.proposed_swap_date:
        swap_assignment, created = DutyAssignment.objects.get_or_create(
            date=offer.proposed_swap_date
        )
        setattr(swap_assignment, field_name, swap_request.requester)
        swap_assignment.save()
        logger.info(
            f"Updated {offer.proposed_swap_date}: {field_name} = {swap_request.requester}"
        )


# =============================================================================
# EMAIL NOTIFICATION FUNCTIONS
# =============================================================================


def get_email_context_base():
    """Get base context for email templates."""
    config = SiteConfiguration.objects.first()
    base_url = get_canonical_url()
    if not config:
        return {
            "club_name": "Soaring Club",
            "club_nickname": "Club",
            "club_logo_url": None,
            "base_url": base_url,
        }
    return {
        "club_name": config.club_name,
        "club_nickname": config.club_nickname,
        "club_logo_url": get_absolute_club_logo_url(config),
        "base_url": base_url,
    }


def get_from_email():
    """Get the from email address for notifications."""
    return getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")


def send_swap_request_notifications(swap_request):
    """Send notification emails when a swap request is created."""
    if swap_request.request_type == "direct" and swap_request.direct_request_to:
        # Send only to the specific member
        recipients = [swap_request.direct_request_to]
    else:
        # Send to all eligible members
        recipients = get_eligible_members_for_role(
            swap_request.role, exclude_member=swap_request.requester
        )

    if not recipients:
        logger.warning(f"No eligible recipients for swap request {swap_request.pk}")
        return

    role_title = swap_request.get_role_title()
    context = get_email_context_base()
    base_url = context.get("base_url", "http://localhost:8001")
    context.update(
        {
            "swap_request": swap_request,
            "role_title": role_title,
            "request_url": f"{base_url}/duty_roster/swap/request/{swap_request.pk}/",
        }
    )

    subject = f"🔄 {swap_request.requester.first_name} needs {role_title} coverage on {swap_request.original_date.strftime('%b %d')}"

    for recipient in recipients:
        if recipient.email:
            # Personalize context for each recipient
            recipient_context = context.copy()
            recipient_context["recipient"] = recipient
            recipient_context["is_direct_request"] = (
                swap_request.request_type == "direct"
            )

            html_content = render_to_string(
                "duty_roster/emails/swap_request_created.html", recipient_context
            )

            send_mail(
                subject=subject,
                message="",  # Plain text fallback
                html_message=html_content,
                from_email=get_from_email(),
                recipient_list=[recipient.email],
                fail_silently=True,
            )
            logger.info(f"Sent swap request notification to {recipient.email}")


def send_offer_made_notification(offer):
    """Notify requester that someone made an offer."""
    swap_request = offer.swap_request

    role_title = swap_request.get_role_title()
    context = get_email_context_base()
    base_url = context.get("base_url", "http://localhost:8001")
    context.update(
        {
            "offer": offer,
            "swap_request": swap_request,
            "role_title": role_title,
            "request_url": f"{base_url}/duty_roster/swap/request/{swap_request.pk}/",
        }
    )

    if offer.offer_type == "swap":
        subject = f"📨 {offer.offered_by.first_name} offers to swap {role_title} duty"
    else:
        subject = (
            f"📨 {offer.offered_by.first_name} offers to cover your {role_title} duty"
        )

    html_content = render_to_string("duty_roster/emails/swap_offer_made.html", context)

    if swap_request.requester.email:
        send_mail(
            subject=subject,
            message="",
            html_message=html_content,
            from_email=get_from_email(),
            recipient_list=[swap_request.requester.email],
            fail_silently=True,
        )
        logger.info(f"Sent offer notification to {swap_request.requester.email}")


def send_offer_accepted_notifications(offer):
    """Notify both parties when an offer is accepted."""
    swap_request = offer.swap_request

    role_title = swap_request.get_role_title()
    is_swap = offer.offer_type == "swap"

    # Check dev mode
    dev_mode, redirect_list = get_dev_mode_info()

    for recipient in [swap_request.requester, offer.offered_by]:
        if not recipient.email:
            continue

        # Determine if this is the original requester or the person who offered
        is_original_requester = recipient == swap_request.requester

        context = get_email_context_base()
        base_url = context.get("base_url", "http://localhost:8001")
        context.update(
            {
                "offer": offer,
                "swap_request": swap_request,
                "role_title": role_title,
                "roster_url": f"{base_url}/duty_roster/duty-calendar/",
                "recipient": recipient,
                "is_swap": is_swap,
            }
        )

        subject = f"✅ {role_title} duty swap confirmed for {swap_request.original_date.strftime('%b %d')}"

        html_content = render_to_string(
            "duty_roster/emails/swap_offer_accepted.html", context
        )

        # Generate ICS attachment for the recipient
        ics_content = generate_swap_ics(
            swap_request,
            for_member=recipient,
            is_original_requester=is_original_requester,
        )

        # Determine date for filename
        if is_original_requester and is_swap and offer.proposed_swap_date:
            ics_date = offer.proposed_swap_date.isoformat()
        elif not is_original_requester:
            ics_date = swap_request.original_date.isoformat()
        else:
            ics_date = swap_request.original_date.isoformat()

        ics_filename = f"duty-{ics_date}-{role_title.lower().replace(' ', '-')}.ics"

        # Create email with ICS attachment
        email = EmailMultiAlternatives(
            subject=subject,
            body="",
            from_email=get_from_email(),
            to=[recipient.email],
        )
        email.attach_alternative(html_content, "text/html")

        # Only attach ICS if there's actual content (e.g., requester in cover scenario gets no new duty)
        if ics_content:
            email.attach(ics_filename, ics_content, "text/calendar")

        # Apply dev mode if enabled
        if dev_mode:
            if redirect_list:
                email.subject = f"[DEV MODE] {subject} (TO: {recipient.email})"
                email.to = redirect_list
            else:
                logger.error(
                    "Dev mode is enabled but redirect_list is empty. Refusing to send real email."
                )
                return  # Don't send ANY emails if dev mode misconfigured

        email.send(fail_silently=True)
        logger.info(f"Sent acceptance notification to {recipient.email}")


def send_offer_declined_notification(offer, auto=False):
    """Notify offerer that their offer was declined (or auto-declined)."""
    swap_request = offer.swap_request

    role_title = swap_request.get_role_title()
    context = get_email_context_base()
    context.update(
        {
            "offer": offer,
            "swap_request": swap_request,
            "role_title": role_title,
            "auto_declined": auto,
        }
    )

    if auto:
        subject = f"ℹ️ {swap_request.requester.first_name} accepted another offer"
    else:
        subject = f"ℹ️ Your {role_title} swap offer was declined"

    html_content = render_to_string(
        "duty_roster/emails/swap_offer_declined.html", context
    )

    if offer.offered_by.email:
        send_mail(
            subject=subject,
            message="",
            html_message=html_content,
            from_email=get_from_email(),
            recipient_list=[offer.offered_by.email],
            fail_silently=True,
        )
        logger.info(f"Sent decline notification to {offer.offered_by.email}")


def send_request_cancelled_notifications(swap_request):
    """Notify all originally notified members that the request was cancelled."""
    # Get the same recipients who were originally notified
    if swap_request.request_type == "direct" and swap_request.direct_request_to:
        # For direct requests, only notify the specific member
        recipients = [swap_request.direct_request_to]
    else:
        # For broadcast requests, notify all eligible members
        recipients = get_eligible_members_for_role(
            swap_request.role, exclude_member=swap_request.requester
        )

    if not recipients:
        logger.warning(
            f"No recipients to notify for cancelled swap request {swap_request.pk}"
        )
        return

    # Get list of members who made offers (to customize message)
    offerers_ids = set(swap_request.offers.values_list("offered_by_id", flat=True))

    role_title = swap_request.get_role_title()
    context = get_email_context_base()
    subject = f"ℹ️ {swap_request.requester.first_name} cancelled their {role_title} swap request"

    for recipient in recipients:
        if recipient.email:
            # Personalize context for each recipient
            recipient_context = context.copy()
            recipient_context.update(
                {
                    "recipient": recipient,
                    "swap_request": swap_request,
                    "role_title": role_title,
                    "had_offer": recipient.id in offerers_ids,
                }
            )

            html_content = render_to_string(
                "duty_roster/emails/swap_request_cancelled.html", recipient_context
            )

            send_mail(
                subject=subject,
                message="",
                html_message=html_content,
                from_email=get_from_email(),
                recipient_list=[recipient.email],
                fail_silently=True,
            )
            logger.info(
                f"Sent cancellation notification to {recipient.email} (had_offer={recipient.id in offerers_ids})"
            )


def send_request_declined_by_member_notification(swap_request, declining_member):
    """Notify requester that a specific member declined their direct request."""

    role_title = swap_request.get_role_title()
    context = get_email_context_base()
    base_url = context.get("base_url", "http://localhost:8001")
    context.update(
        {
            "swap_request": swap_request,
            "role_title": role_title,
            "declining_member": declining_member,
            "request_url": f"{base_url}/duty_roster/swap/request/{swap_request.pk}/",
        }
    )

    subject = f"ℹ️ {declining_member.first_name} declined your {role_title} swap request"

    html_content = render_to_string(
        "duty_roster/emails/swap_request_member_declined.html", context
    )

    if swap_request.requester.email:
        send_mail(
            subject=subject,
            message="",
            html_message=html_content,
            from_email=get_from_email(),
            recipient_list=[swap_request.requester.email],
            fail_silently=True,
        )
        logger.info(
            f"Sent member declined notification to {swap_request.requester.email}"
        )
