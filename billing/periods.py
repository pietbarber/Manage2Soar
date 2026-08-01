from calendar import monthrange
from datetime import date, datetime, time, timedelta

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction

from billing.models import BillingPeriod, BillingPeriodEvent
from billing.permissions import require_manual_transaction_access
from siteconfig.models import BillingPeriodClosePolicy, SiteConfiguration
from siteconfig.timezone_utils import get_club_now, get_club_tzinfo


def close_month(year, month, offset):
    absolute_month = month + offset
    return year + (absolute_month - 1) // 12, (absolute_month - 1) % 12 + 1


def nth_weekday(year, month, weekday, occurrence):
    first_day = date(year, month, 1)
    day = 1 + (weekday - first_day.weekday()) % 7 + 7 * (occurrence - 1)
    last_day = monthrange(year, month)[1]
    # A requested fifth weekday falls back to that month's final occurrence.
    return date(year, month, day if day <= last_day else day - 7)


def automatic_close_at(year, month):
    config = SiteConfiguration.objects.only(
        "billing_period_close_policy",
        "billing_period_close_month_offset",
        "billing_period_close_week_number",
        "billing_period_close_weekday",
        "billing_period_close_days_before_month_end",
    ).first()
    if not config:
        return None
    close_year, close_month_number = close_month(
        year, month, config.billing_period_close_month_offset
    )
    if config.billing_period_close_policy == BillingPeriodClosePolicy.NTH_WEEKDAY:
        close_date = nth_weekday(
            close_year,
            close_month_number,
            config.billing_period_close_weekday,
            config.billing_period_close_week_number,
        )
    else:
        close_date = date(
            close_year,
            close_month_number,
            monthrange(close_year, close_month_number)[1],
        ) - timedelta(days=config.billing_period_close_days_before_month_end)
    return datetime.combine(close_date, time(23, 59), tzinfo=get_club_tzinfo())


def is_period_closed(period_date, now=None):
    period = (
        BillingPeriod.objects.filter(year=period_date.year, month=period_date.month)
        .only("is_closed")
        .first()
    )
    if period is not None and period.is_closed:
        return True

    config = SiteConfiguration.objects.only("billing_period_close_policy").first()
    if (
        not config
        or config.billing_period_close_policy == BillingPeriodClosePolicy.MANUAL
    ):
        return False
    if (
        period is not None
        and period.events.filter(action=BillingPeriodEvent.Action.REOPENED).exists()
    ):
        return False
    close_at = automatic_close_at(period_date.year, period_date.month)
    return close_at is not None and (now or get_club_now()) >= close_at


def lock_period_for_date(period_date):
    """Lock period state so a concurrent close cannot pass a split approval."""
    BillingPeriod.objects.get_or_create(year=period_date.year, month=period_date.month)
    BillingPeriod.objects.select_for_update().get(
        year=period_date.year, month=period_date.month
    )
    return is_period_closed(period_date)


@transaction.atomic
def close_period(*, year, month, actor=None, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A period-close reason is required.")
    if actor is not None:
        require_manual_transaction_access(actor)

    period, _ = BillingPeriod.objects.select_for_update().get_or_create(
        year=year, month=month
    )
    if period.is_closed:
        return period
    period.is_closed = True
    period.save(update_fields=["is_closed"])
    BillingPeriodEvent.objects.create(
        period=period,
        action=BillingPeriodEvent.Action.CLOSED,
        actor=actor,
        reason=reason.strip(),
    )

    try:
        FlightSplitRequest = apps.get_model("logsheet", "FlightSplitRequest")
    except LookupError:
        pass
    else:
        FlightSplitRequest.objects.filter(
            flight__logsheet__log_date__year=year,
            flight__logsheet__log_date__month=month,
            status=FlightSplitRequest.Status.PENDING,
        ).update(status=FlightSplitRequest.Status.LOCKED)
    return period


@transaction.atomic
def reopen_period(*, period, actor, reason):
    require_manual_transaction_access(actor)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A period-reopen reason is required.")
    period = BillingPeriod.objects.select_for_update().get(pk=period.pk)
    if not period.is_closed:
        raise ValidationError("This billing period is already open.")
    period.is_closed = False
    period.save(update_fields=["is_closed"])
    BillingPeriodEvent.objects.create(
        period=period,
        action=BillingPeriodEvent.Action.REOPENED,
        actor=actor,
        reason=reason.strip(),
    )
    return period


def close_due_periods(now=None, dry_run=False):
    now = now or get_club_now()
    config = SiteConfiguration.objects.only("billing_period_close_policy").first()
    if (
        not config
        or config.billing_period_close_policy == BillingPeriodClosePolicy.MANUAL
    ):
        return []

    from logsheet.models import Logsheet

    closed = []
    for log_date in Logsheet.objects.values_list("log_date", flat=True).distinct():
        close_at = automatic_close_at(log_date.year, log_date.month)
        if close_at is not None and now >= close_at:
            period = BillingPeriod.objects.filter(
                year=log_date.year, month=log_date.month
            ).first()
            reopened = (
                period
                and period.events.filter(
                    action=BillingPeriodEvent.Action.REOPENED
                ).exists()
            )
            if period is None or (not period.is_closed and not reopened):
                if dry_run:
                    closed.append((log_date.year, log_date.month))
                else:
                    closed.append(
                        close_period(
                            year=log_date.year,
                            month=log_date.month,
                            reason="Automatically closed by the configured billing-period policy.",
                        )
                    )
    return closed
