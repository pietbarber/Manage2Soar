"""
Glider Reservation Views

Handles all glider reservation functionality including:
- Viewing reservations (list and detail)
- Creating new reservations
- Cancelling reservations
- Member reservation history

See Issue #410 and docs/workflows/issue-190-glider-reservation-design.md
"""

import logging
from datetime import date, timedelta

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from members.decorators import active_member_required
from siteconfig.models import ReservationLimitPeriod, SiteConfiguration

from .forms import GliderReservationCancelForm, GliderReservationForm
from .models import GliderReservation

logger = logging.getLogger("duty_roster.reservations")


@active_member_required
def reservation_list(request):
    """
    View all reservations for the current user.
    Shows upcoming and past reservations.
    """
    member = request.user
    today = timezone.now().date()

    # Get upcoming reservations
    upcoming = (
        GliderReservation.objects.filter(
            member=member,
            date__gte=today,
            status="confirmed",
        )
        .select_related("glider")
        .order_by("date")
    )

    # Get past reservations (last 12 months)
    past_cutoff = today - timedelta(days=365)
    past = (
        GliderReservation.objects.filter(
            member=member,
            date__lt=today,
            date__gte=past_cutoff,
        )
        .select_related("glider")
        .order_by("-date")[:20]
    )

    # Get reservation counts for status card
    yearly_counts = GliderReservation.get_reservations_by_year(member)
    current_year_count = yearly_counts.get(today.year, 0)
    current_month_count = GliderReservation.get_member_monthly_count(member)

    config = SiteConfiguration.objects.first()
    reservation_limit_period = (
        config.reservation_limit_period if config else ReservationLimitPeriod.YEARLY
    )
    max_per_year = config.max_reservations_per_year if config else 3
    max_per_month = config.max_reservations_per_month if config else 0

    if reservation_limit_period == ReservationLimitPeriod.QUARTERLY:
        current_quarter = ((today.month - 1) // 3) + 1
        current_period_label = f"Q{current_quarter} {today.year}"
        current_period_count = GliderReservation.get_member_quarterly_count(
            member,
            year=today.year,
            quarter=current_quarter,
        )
        primary_period_unit = "quarter"
    else:
        current_period_label = str(today.year)
        current_period_count = current_year_count
        primary_period_unit = "year"

    # Only show current-period capacity status here; do not treat this as
    # global create eligibility because users may reserve in a future period.
    at_primary_period_limit = False
    if max_per_year > 0 and current_period_count >= max_per_year:
        at_primary_period_limit = True

    at_monthly_limit = False
    if max_per_month > 0 and current_month_count >= max_per_month:
        at_monthly_limit = True

    context = {
        "upcoming": upcoming,
        "past": past,
        "yearly_counts": yearly_counts,
        "current_year_count": current_year_count,
        "current_month_count": current_month_count,
        "current_year": today.year,
        "current_month": today.month,
        "max_per_year": max_per_year,
        "max_per_period": max_per_year,
        "reservation_limit_period": reservation_limit_period,
        "current_period_label": current_period_label,
        "current_period_count": current_period_count,
        "primary_period_unit": primary_period_unit,
        "max_per_month": max_per_month,
        "can_create_reservation": config.allow_glider_reservations if config else False,
        "at_primary_period_limit": at_primary_period_limit,
        "at_monthly_limit": at_monthly_limit,
        "reservations_enabled": config.allow_glider_reservations if config else False,
    }

    return render(request, "duty_roster/reservations/list.html", context)


@active_member_required
def reservation_create(request, year=None, month=None, day=None):
    """
    Create a new glider reservation.
    Optionally pre-fill date from URL parameters.
    """
    member = request.user
    config = SiteConfiguration.objects.first()

    target_year = None
    target_month = None
    if request.method == "POST":
        posted_date = request.POST.get("date")
        if posted_date:
            try:
                target_date = date.fromisoformat(posted_date)
                target_year = target_date.year
                target_month = target_date.month
            except ValueError:
                pass
    elif year is not None and month is not None:
        try:
            parsed_year = int(year)
            parsed_month = int(month)
            if 1 <= parsed_month <= 12:
                target_year = parsed_year
                target_month = parsed_month
            else:
                messages.error(request, "Invalid reservation date.")
                return redirect("duty_roster:reservation_list")
        except (TypeError, ValueError):
            pass

    # Check if reservations are enabled
    if not config or not config.allow_glider_reservations:
        messages.error(request, "Glider reservations are currently disabled.")
        return redirect("duty_roster:reservation_list")

    # Pre-check limits only when a target date is known; otherwise let the user
    # open the form and rely on date-aware validation at submit time.
    if target_year is not None and target_month is not None:
        can_reserve, message = GliderReservation.can_member_reserve(
            member,
            year=target_year,
            month=target_month,
        )
        if not can_reserve:
            messages.warning(request, message)
            return redirect("duty_roster:reservation_list")

    if request.method == "POST":
        # Hold member-limit locks across validation and insert to avoid races.
        with transaction.atomic():
            form = GliderReservationForm(request.POST, member=member)
            if form.is_valid():
                reservation = form.save()
                # Check if save was actually successful (form.save() may add errors without raising)
                if reservation.pk:
                    expired_deadlines = []
                    if reservation.glider:
                        expired_deadlines = list(
                            reservation.glider.get_expired_maintenance_deadlines()
                        )

                    if expired_deadlines:
                        overdue_items = ", ".join(
                            f"{d.description_label} (due {d.due_date:%b %d, %Y})"
                            for d in expired_deadlines
                        )
                        messages.warning(
                            request,
                            "Warning: this aircraft has expired maintenance deadlines: "
                            f"{overdue_items}. Please confirm with operations staff before flying.",
                        )

                    # Defensive programming: ensure glider exists before displaying
                    glider_display = (
                        str(reservation.glider)
                        if reservation.glider
                        else "Unknown glider"
                    )
                    messages.success(
                        request,
                        f"Reservation confirmed for {glider_display} on {reservation.date}.",
                    )
                    logger.info(
                        f"Reservation created: {member.full_display_name} reserved "
                        f"{glider_display} for {reservation.date}"
                    )
                    return redirect("duty_roster:reservation_list")
                # If save failed (pk is None), form has errors - fall through to re-render
    else:
        # Pre-fill date if provided in URL
        initial = {}
        if year and month and day:
            try:
                initial["date"] = date(int(year), int(month), int(day))
            except (ValueError, TypeError):
                # Ignore invalid date parameters; form will not be pre-filled if parsing fails.
                pass

        form = GliderReservationForm(member=member, initial=initial)

    # Get available gliders for display (use the same queryset as the form to ensure consistency)
    available_gliders = form.fields["glider"].queryset

    # Prefetch grounded/expired status to avoid N+1 queries in template
    from logsheet.models import MaintenanceDeadline, MaintenanceIssue

    grounded_glider_ids = set(
        MaintenanceIssue.objects.filter(
            glider__in=available_gliders,
            grounded=True,
            resolved=False,
        ).values_list("glider_id", flat=True)
    )

    expired_deadline_glider_ids = set(
        MaintenanceDeadline.objects.filter(
            glider__in=available_gliders,
            due_date__lt=timezone.now().date(),
        )
        .values_list("glider_id", flat=True)
        .distinct()
    )

    selected_glider = None
    selected_glider_expired_deadlines = []
    selected_glider_id = (
        request.POST.get("glider") if request.method == "POST" else None
    )
    if selected_glider_id:
        try:
            selected_glider = available_gliders.filter(
                pk=int(selected_glider_id)
            ).first()
        except (TypeError, ValueError):
            selected_glider = None

    if selected_glider:
        selected_glider_expired_deadlines = list(
            selected_glider.get_expired_maintenance_deadlines()
        )

    context = {
        "form": form,
        "available_gliders": available_gliders,
        "grounded_glider_ids": grounded_glider_ids,
        "expired_deadline_glider_ids": expired_deadline_glider_ids,
        "selected_glider": selected_glider,
        "selected_glider_expired_deadlines": selected_glider_expired_deadlines,
        "max_per_year": config.max_reservations_per_year,
        "max_per_period": config.max_reservations_per_year,
        "reservation_limit_period": config.reservation_limit_period,
    }

    return render(request, "duty_roster/reservations/create.html", context)


@active_member_required
def reservation_detail(request, reservation_id):
    """View details of a specific reservation."""
    member = request.user
    reservation = get_object_or_404(
        GliderReservation.objects.select_related("glider"),
        pk=reservation_id,
        member=member,
    )

    context = {
        "reservation": reservation,
        "can_cancel": reservation.is_active,
    }

    return render(request, "duty_roster/reservations/detail.html", context)


@active_member_required
def reservation_cancel(request, reservation_id):
    """
    Handle reservation cancellation.
    - GET: Show cancellation confirmation form.
    - POST: Process cancellation.
    """
    member = request.user
    reservation = get_object_or_404(
        GliderReservation.objects.select_related("glider"),
        pk=reservation_id,
        member=member,
        status="confirmed",
    )

    if request.method == "POST":
        form = GliderReservationCancelForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data.get("cancellation_reason", "")
            reservation.cancel(reason=reason)
            messages.success(
                request,
                f"Reservation for {reservation.glider} on {reservation.date} has been cancelled.",
            )
            logger.info(
                f"Reservation cancelled: {member.full_display_name} cancelled "
                f"{reservation.glider} reservation for {reservation.date}"
            )
            return redirect("duty_roster:reservation_list")
        else:
            # Show field-specific errors only (non-field errors already shown via form.non_field_errors)
            for field, errors in form.errors.items():
                # Skip non-field errors as they're handled separately
                if field == "__all__":
                    for error in errors:
                        messages.error(request, str(error))
                else:
                    for error in errors:
                        messages.error(request, f"{field}: {str(error)}")
    else:
        form = GliderReservationCancelForm()

    context = {
        "reservation": reservation,
        "form": form,
    }

    return render(request, "duty_roster/reservations/cancel_confirm.html", context)


@active_member_required
def day_reservations(request, year, month, day):
    """
    Get reservations for a specific day.
    Used by HTMX to show reservations in day detail modal.
    """
    try:
        target_date = date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Invalid date")

    reservations = GliderReservation.get_reservations_for_date(target_date)
    config = SiteConfiguration.objects.first()

    context = {
        "reservations": reservations,
        "date": target_date,
        "can_reserve": GliderReservation.can_member_reserve(
            request.user,
            year=target_date.year,
            month=target_date.month,
            config=config,
        )[0],
    }

    return render(request, "duty_roster/reservations/_day_reservations.html", context)


@active_member_required
def reservation_create_for_day(request, year, month, day):
    """
    Create reservation for a specific day (from calendar).
    This is a shortcut that pre-fills the date.
    """
    return reservation_create(request, year, month, day)
