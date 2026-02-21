"""Tests for ad-hoc operations email notification logic (issue #654).

Covers:
- notify_ops_status() sends proposal to MEMBERS_MAILING_LIST, not role-specific lists
- expire_ad_hoc_days command expires today's unconfirmed days (not tomorrow's)
- Confirmed and future unconfirmed days are left untouched
"""

from datetime import timedelta
from unittest.mock import patch

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


class TestExpireAdHocDaysDeadline(TestCase):
    """expire_ad_hoc_days should expire TODAY's unconfirmed ad-hoc days (runs
    at 3 AM UTC = 10 PM EST), not tomorrow's."""

    def setUp(self):
        _make_site_config()
        self.today = now().date()
        self.tomorrow = self.today + timedelta(days=1)

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_todays_unconfirmed_adhoc_is_cancelled(self, mock_send):
        """An unconfirmed ad-hoc day for today must be deleted."""
        assignment = DutyAssignment.objects.create(
            date=self.today,
            is_scheduled=False,
            is_confirmed=False,
        )
        cmd = ExpireCommand()
        cmd.execute_job(dry_run=False)

        self.assertFalse(
            DutyAssignment.objects.filter(pk=assignment.pk).exists(),
            "Today's unconfirmed ad-hoc assignment should have been deleted.",
        )
        mock_send.assert_called_once()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_tomorrows_unconfirmed_adhoc_is_left_alone(self, mock_send):
        """An unconfirmed ad-hoc day for tomorrow must NOT be cancelled yet."""
        assignment = DutyAssignment.objects.create(
            date=self.tomorrow,
            is_scheduled=False,
            is_confirmed=False,
        )
        cmd = ExpireCommand()
        cmd.execute_job(dry_run=False)

        self.assertTrue(
            DutyAssignment.objects.filter(pk=assignment.pk).exists(),
            "Tomorrow's unconfirmed ad-hoc assignment should NOT be cancelled yet.",
        )
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.expire_ad_hoc_days.send_mail")
    def test_confirmed_adhoc_today_is_not_cancelled(self, mock_send):
        """A confirmed ad-hoc day for today must not be touched."""
        assignment = DutyAssignment.objects.create(
            date=self.today,
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
    def test_scheduled_day_today_is_not_cancelled(self, mock_send):
        """A scheduled (non-ad-hoc) day for today must not be touched."""
        assignment = DutyAssignment.objects.create(
            date=self.today,
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
            date=self.today,
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
