from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError

from billing.models import BillingPeriod, BillingPeriodEvent
from billing.periods import (
    automatic_close_at,
    close_period,
    is_period_closed,
    reopen_period,
)
from members.models import Member
from siteconfig.models import BillingPeriodClosePolicy


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(username="period-treasurer", treasurer=True)


def test_manual_policy_does_not_automatically_close_period(enable_billing_app):
    enable_billing_app.billing_period_close_policy = BillingPeriodClosePolicy.MANUAL
    enable_billing_app.save(update_fields=["billing_period_close_policy"])

    assert not is_period_closed(
        date(2026, 7, 1), now=datetime(2026, 8, 4, tzinfo=ZoneInfo("UTC"))
    )


def test_nth_weekday_policy_closes_at_1159_pm_club_time(enable_billing_app):
    enable_billing_app.club_timezone = "UTC"
    enable_billing_app.billing_period_close_policy = (
        BillingPeriodClosePolicy.NTH_WEEKDAY
    )
    enable_billing_app.save(
        update_fields=["club_timezone", "billing_period_close_policy"]
    )
    close_at = automatic_close_at(2026, 7)

    assert close_at == datetime(2026, 8, 3, 23, 59, tzinfo=ZoneInfo("UTC"))
    assert not is_period_closed(date(2026, 7, 1), now=close_at.replace(minute=58))
    assert is_period_closed(date(2026, 7, 1), now=close_at)


def test_days_before_month_end_policy_closes_at_1159_pm_club_time(enable_billing_app):
    enable_billing_app.club_timezone = "UTC"
    enable_billing_app.billing_period_close_policy = (
        BillingPeriodClosePolicy.DAYS_BEFORE_MONTH_END
    )
    enable_billing_app.billing_period_close_month_offset = 0
    enable_billing_app.save(
        update_fields=[
            "club_timezone",
            "billing_period_close_policy",
            "billing_period_close_month_offset",
        ]
    )
    close_at = automatic_close_at(2026, 7)

    assert close_at == datetime(2026, 7, 31, 23, 59, tzinfo=ZoneInfo("UTC"))
    assert not is_period_closed(date(2026, 7, 1), now=close_at.replace(minute=58))
    assert is_period_closed(date(2026, 7, 1), now=close_at)


def test_nth_weekday_policy_supports_any_weekday_and_month(enable_billing_app):
    enable_billing_app.club_timezone = "UTC"
    enable_billing_app.billing_period_close_policy = (
        BillingPeriodClosePolicy.NTH_WEEKDAY
    )
    enable_billing_app.billing_period_close_week_number = 2
    enable_billing_app.billing_period_close_weekday = 2
    enable_billing_app.save(
        update_fields=[
            "club_timezone",
            "billing_period_close_policy",
            "billing_period_close_week_number",
            "billing_period_close_weekday",
        ]
    )
    close_at = automatic_close_at(2026, 7)

    assert close_at == datetime(2026, 8, 12, 23, 59, tzinfo=ZoneInfo("UTC"))
    assert not is_period_closed(date(2026, 7, 1), now=close_at.replace(minute=58))
    assert is_period_closed(date(2026, 7, 1), now=close_at)


def test_treasurer_can_close_and_reopen_a_period(treasurer):
    period = close_period(
        year=2026, month=7, actor=treasurer, reason="Month reconciled"
    )

    assert period.is_closed
    assert (
        BillingPeriodEvent.objects.get(period=period).action
        == BillingPeriodEvent.Action.CLOSED
    )

    period = reopen_period(period=period, actor=treasurer, reason="Late correction")

    assert not period.is_closed
    assert list(
        BillingPeriodEvent.objects.filter(period=period).values_list(
            "action", flat=True
        )
    ) == [
        BillingPeriodEvent.Action.REOPENED,
        BillingPeriodEvent.Action.CLOSED,
    ]


def test_period_actions_require_a_treasurer(treasurer):
    member = Member.objects.create_user(username="period-member")
    with pytest.raises(ValidationError, match="Only treasurers"):
        close_period(year=2026, month=7, actor=member, reason="Not authorized")

    period = close_period(
        year=2026, month=7, actor=treasurer, reason="Month reconciled"
    )
    with pytest.raises(ValidationError, match="Only treasurers"):
        reopen_period(period=period, actor=member, reason="Not authorized")


def test_treasurer_period_views_require_reason(client, treasurer):
    client.force_login(treasurer)
    response = client.post(
        "/billing/periods/close/", {"year": 2026, "month": 7, "reason": ""}
    )

    assert response.status_code == 302
    assert not BillingPeriod.objects.exists()
