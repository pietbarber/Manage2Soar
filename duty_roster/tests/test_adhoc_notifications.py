"""Tests for ad-hoc operations email notification logic (issue #654).

Covers:
- notify_ops_status() sends proposal to MEMBERS_MAILING_LIST, not role-specific lists
- expire_ad_hoc_days command expires the next club-local day's (tomorrow's)
  unconfirmed ad-hoc days at the night-before deadline (issue #1056)
- Confirmed and scheduled days are left untouched
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils.timezone import now

from duty_roster.management.commands.expire_ad_hoc_days import Command as ExpireCommand
from duty_roster.models import DutyAssignment
from duty_roster.utils.email import notify_ops_status
from siteconfig.models import SiteConfiguration


def _make_site_config():
    return SiteConfiguration.objects.first() or SiteConfiguration.objects.create(
        club_name="Test Club",
        club_abbreviation="TST",
        domain_name="example.com",
    )


class TestNotifyOpsStatusRecipients(TestCase):
    """notify_ops_status() should send the initial proposal to all members, not
    to separate instructor/tow-pilot mailing lists."""

    def setUp(self):
        _make_site_config()
        self.tomorrow = now().date() + timedelta(days=1)
        self.assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )

    @override_settings(
        MEMBERS_MAILING_LIST="members@example.com",
        INSTRUCTORS_MAILING_LIST="instructors@example.com",
        TOWPILOTS_MAILING_LIST="towpilots@example.com",
    )
    @patch("duty_roster.utils.email.send_mail")
    def test_proposal_sent_to_members_list_not_role_lists(self, mock_send):
        """Initial ad-hoc proposal must go to members@, not instructors@ or towpilots@."""
        notify_ops_status(self.assignment)

        mock_send.assert_called_once()
        recipient_list = mock_send.call_args[1]["recipient_list"]
        self.assertIn("members@example.com", recipient_list)
        self.assertNotIn("instructors@example.com", recipient_list)
        self.assertNotIn("towpilots@example.com", recipient_list)

    @override_settings(MEMBERS_MAILING_LIST="members@example.com")
    @patch("duty_roster.utils.email.send_mail")
    def test_proposal_not_sent_for_scheduled_day(self, mock_send):
        """Scheduled (not ad-hoc) days must not trigger a proposal email."""
        self.assignment.is_scheduled = True
        self.assignment.save()
        notify_ops_status(self.assignment)
        mock_send.assert_not_called()

    @override_settings(MEMBERS_MAILING_LIST="members@example.com")
    @patch("duty_roster.utils.email.send_mail")
    def test_proposal_not_sent_when_already_has_tow_pilot(self, mock_send):
        """Once a tow pilot has signed up, the initial proposal path should not fire."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        tow = User.objects.create_user(
            username="towonly",
            email="tow@example.com",
            password="x",
            membership_status="Full Member",
            towpilot=True,
        )
        self.assignment.tow_pilot = tow
        self.assignment.save()
        notify_ops_status(self.assignment)
        # Initial proposal only fires when BOTH tow_pilot and duty_officer are None,
        # so no email at all should be sent once a tow pilot is assigned.
        mock_send.assert_not_called()

    @override_settings(MEMBERS_MAILING_LIST="members@example.com")
    @patch("duty_roster.utils.email.send_mail")
    def test_rescind_to_empty_crew_does_not_resend_proposal(self, mock_send):
        """After the last crew member rescinds, notify_ops_status with is_rescind=True
        must NOT re-send the original proposal email (issue #654 duplicate fix)."""
        notify_ops_status(self.assignment, is_rescind=True)
        mock_send.assert_not_called()


class TestProposeAdHocDayDeduplication(TestCase):
    """Proposing an ad-hoc day that already exists must not send a second proposal email."""

    def setUp(self):
        _make_site_config()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.member = User.objects.create_user(
            username="proposer",
            email="proposer@example.com",
            password="testpass",
            membership_status="Full Member",
        )
        # A future date to satisfy the "must be in the future" guard in the view
        self.future = now().date() + timedelta(days=3)

    @override_settings(MEMBERS_MAILING_LIST="members@example.com")
    @patch("duty_roster.utils.email.send_mail")
    def test_second_propose_click_does_not_send_duplicate_email(self, mock_send):
        """POSTing calendar_ad_hoc_confirm twice for the same date must send
        exactly one proposal email, not two (issue #654)."""
        self.client.force_login(self.member)
        url = f"/duty_roster/calendar/ad-hoc/confirm/{self.future.year}/{self.future.month}/{self.future.day}/"

        self.client.post(url)
        self.client.post(url)  # Second click — day already exists

        self.assertEqual(
            mock_send.call_count,
            1,
            "Proposal email must be sent exactly once even if the same date is proposed twice.",
        )


class TestExpireAdHocDaysDeadline(TestCase):
    """expire_ad_hoc_days should expire tomorrow's day at 23:00 club-local."""

    def setUp(self):
        _make_site_config()
        self.today = now().date()
        self.tomorrow = self.today + timedelta(days=1)
        self.club_now_patcher = patch(
            "duty_roster.management.commands.expire_ad_hoc_days.get_club_now"
        )
        self.mock_club_now = self.club_now_patcher.start()
        self.mock_club_now.return_value = datetime.combine(
            self.today, datetime.min.time().replace(hour=23), tzinfo=dt_timezone.utc
        )

    def tearDown(self):
        self.club_now_patcher.stop()
        super().tearDown()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_tomorrows_unconfirmed_adhoc_is_cancelled(self, mock_send):
        """An unconfirmed ad-hoc day for tomorrow (the night-before ops day)
        must be deleted and a cancellation email sent."""
        assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )
        cmd = ExpireCommand()
        cmd.execute_job(dry_run=False)

        self.assertFalse(
            DutyAssignment.objects.filter(pk=assignment.pk).exists(),
            "Tomorrow's unconfirmed ad-hoc assignment should have been deleted.",
        )
        mock_send.assert_called_once()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_todays_unconfirmed_adhoc_is_left_alone(self, mock_send):
        """An unconfirmed ad-hoc day for today (the current club-local day)
        must NOT be cancelled — that is the off-by-one fixed in issue #1056."""
        assignment = DutyAssignment.objects.create(
            date=self.today,
            is_scheduled=False,
            is_confirmed=False,
        )
        cmd = ExpireCommand()
        cmd.execute_job(dry_run=False)

        self.assertTrue(
            DutyAssignment.objects.filter(pk=assignment.pk).exists(),
            "Today's unconfirmed ad-hoc assignment should NOT be cancelled.",
        )
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_confirmed_adhoc_tomorrow_is_not_cancelled(self, mock_send):
        """A confirmed ad-hoc day for tomorrow must not be touched."""
        assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=True,
        )
        cmd = ExpireCommand()
        cmd.execute_job(dry_run=False)

        self.assertTrue(
            DutyAssignment.objects.filter(pk=assignment.pk).exists(),
            "Confirmed ad-hoc day should not be cancelled.",
        )
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_scheduled_day_tomorrow_is_not_cancelled(self, mock_send):
        """A scheduled (non-ad-hoc) day for tomorrow must not be touched."""
        assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=True,
            is_confirmed=False,
        )
        cmd = ExpireCommand()
        cmd.execute_job(dry_run=False)

        self.assertTrue(
            DutyAssignment.objects.filter(pk=assignment.pk).exists(),
            "Scheduled day should not be cancelled.",
        )
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_dry_run_does_not_delete_or_email(self, mock_send):
        """Dry run must not delete assignments or send any emails."""
        assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )
        cmd = ExpireCommand()
        cmd.execute_job(dry_run=True)

        self.assertTrue(
            DutyAssignment.objects.filter(pk=assignment.pk).exists(),
            "Dry run should not delete the assignment.",
        )
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_before_local_deadline_does_not_cancel(self, mock_send):
        """An hourly run before 23:00 local must leave tomorrow untouched."""
        self.mock_club_now.return_value = datetime.combine(
            self.today, datetime.min.time().replace(hour=22), tzinfo=dt_timezone.utc
        )
        assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )

        ExpireCommand().execute_job(dry_run=False)

        self.assertTrue(DutyAssignment.objects.filter(pk=assignment.pk).exists())
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_fractional_timezone_runs_at_local_deadline(self, mock_send):
        """A 15-minute UTC schedule reaches 23:00 in Asia/Kathmandu."""
        config = SiteConfiguration.objects.first()
        config.club_timezone = "Asia/Kathmandu"
        config.save(update_fields=["club_timezone"])
        self.mock_club_now.return_value = datetime(
            2026, 1, 1, 23, 0, 0, tzinfo=ZoneInfo("Asia/Kathmandu")
        )
        assignment = DutyAssignment.objects.create(
            date=datetime(2026, 1, 2).date(),
            is_scheduled=False,
            is_confirmed=False,
        )

        ExpireCommand().execute_job(dry_run=False)

        self.assertFalse(DutyAssignment.objects.filter(pk=assignment.pk).exists())
        mock_send.assert_called_once()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_after_local_deadline_does_not_cancel(self, mock_send):
        """The second quarter-hour run must not repeat the deadline action."""
        self.mock_club_now.return_value = datetime.combine(
            self.today,
            datetime.min.time().replace(hour=23, minute=15),
            tzinfo=dt_timezone.utc,
        )
        assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )

        ExpireCommand().execute_job(dry_run=False)

        self.assertTrue(DutyAssignment.objects.filter(pk=assignment.pk).exists())
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_uses_club_local_tomorrow_for_expiration(self, mock_send):
        """Command should use the next day in a non-US club timezone."""
        config = SiteConfiguration.objects.first()
        config.club_timezone = "Asia/Tokyo"
        config.save(update_fields=["club_timezone"])

        # 14:00 UTC on Jan 1 is 23:00 in Tokyo, the night-before deadline for
        # the Jan 2 operations day.
        self.mock_club_now.return_value = datetime(
            2026, 1, 1, 23, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")
        )

        local_tomorrow_assignment = DutyAssignment.objects.create(
            date=datetime(2026, 1, 2).date(),
            is_scheduled=False,
            is_confirmed=False,
        )
        local_today_assignment = DutyAssignment.objects.create(
            date=datetime(2026, 1, 1).date(),
            is_scheduled=False,
            is_confirmed=False,
        )

        cmd = ExpireCommand()
        cmd.execute_job(dry_run=False)

        self.assertFalse(
            DutyAssignment.objects.filter(pk=local_tomorrow_assignment.pk).exists(),
            "Club-local tomorrow's unconfirmed ad-hoc day should be cancelled.",
        )
        self.assertTrue(
            DutyAssignment.objects.filter(pk=local_today_assignment.pk).exists(),
            "Club-local today's assignment should remain (it is not the night-before day).",
        )
        mock_send.assert_called_once()
