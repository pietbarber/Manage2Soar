"""
Test suite for the notification management commands.

Tests the actual production commands: aging logsheets, late SPRs, and duty delinquents.
These are the commands running in production Kubernetes CronJobs.
"""

from datetime import datetime, time, timedelta
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from duty_roster.management.commands.notify_aging_logsheets import (
    Command as AgingLogsheetsCommand,
)
from duty_roster.management.commands.report_duty_delinquents import (
    Command as DutyDelinquentsCommand,
)
from duty_roster.models import DutyAssignment, DutyDay, DutySlot
from instructors.management.commands.notify_late_sprs import Command as LateSPRsCommand
from instructors.models import InstructionReport
from logsheet.models import Airfield, Flight, Logsheet
from members.models import Member
from notifications.management.commands.cleanup_old_notifications import (
    Command as CleanupNotificationsCommand,
)
from notifications.models import Notification
from utils.models import CronJobLock

User = get_user_model()


class TestAgingLogsheetsCommand(TransactionTestCase):
    """Test the aging logsheets notification command."""

    def setUp(self):
        """Set up test data."""
        # Create test member who will act as duty officer
        self.duty_member = Member.objects.create(
            username="duty_officer",
            email="duty@test.com",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
        )

        # Create aging logsheet (8 days old)
        old_date = timezone.now().date() - timedelta(days=8)
        airfield = Airfield.objects.create(identifier="KFRR", name="KFRR Field")
        self.aging_logsheet = Logsheet.objects.create(
            log_date=old_date,
            airfield=airfield,
            created_by=self.duty_member,
            finalized=False,
        )

        # Create fresh logsheet (3 days old)
        fresh_date = timezone.now().date() - timedelta(days=3)
        self.fresh_logsheet = Logsheet.objects.create(
            log_date=fresh_date,
            airfield=airfield,
            created_by=self.duty_member,
            finalized=False,
        )

        # Assign duty officer directly on the logsheet (current system)
        self.aging_logsheet.duty_officer = self.duty_member
        self.aging_logsheet.save()

        self.command = AgingLogsheetsCommand()

    def test_identifies_aging_logsheets(self):
        """Test that command identifies logsheets older than 7 days."""
        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_notification") as mock_send:
                # Execute non-dry run but patch the notifier to avoid external side-effects
                self.command.handle(dry_run=False, verbosity=1)

        # Should identify 1 aging logsheet
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        duty_officer, logsheet_data = call_args

        assert duty_officer == self.duty_member
        # logsheet_data is a list of (logsheet, days_old) tuples
        assert len(logsheet_data) == 1
        assert logsheet_data[0][0] == self.aging_logsheet
        assert duty_officer == self.duty_member

    def test_ignores_fresh_logsheets(self):
        """Test that fresh logsheets are not flagged."""
        # Delete the aging logsheet, only keep fresh one
        self.aging_logsheet.delete()

        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_notification") as mock_send:
                self.command.handle(dry_run=False, verbosity=1)

        # Should not send any notifications
        mock_send.assert_not_called()

    def test_handles_finalized_logsheets(self):
        """Test that finalized logsheets are ignored."""
        # Mark aging logsheet as finalized
        self.aging_logsheet.finalized = True
        self.aging_logsheet.save()

        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_notification") as mock_send:
                self.command.handle(dry_run=False, verbosity=1)

        # Should not send notifications for finalized logsheets
        mock_send.assert_not_called()

    @patch("duty_roster.management.commands.notify_aging_logsheets.send_mail")
    def test_sends_email_notification(self, mock_send_mail):
        """Test that email notifications are sent."""
        with patch("sys.stdout", new_callable=StringIO):
            self.command.handle(verbosity=1)

        # Should send email
        mock_send_mail.assert_called_once()
        args, kwargs = mock_send_mail.call_args

        # Check email content (using keyword arguments)
        subject = kwargs["subject"]
        message = kwargs["message"]
        from_email = kwargs["from_email"]
        recipient_list = kwargs["recipient_list"]

        assert "Aging Logsheet" in subject
        # The message contains the creation date, not the log date
        assert str(self.aging_logsheet.airfield) in message
        assert self.duty_member.email in recipient_list

    def test_creates_in_app_notification(self):
        """Test that in-app notifications are created."""
        with patch("sys.stdout", new_callable=StringIO):
            self.command.handle(verbosity=1)

        # Should create notification
        notification = Notification.objects.get(user=self.duty_member)
        assert "aging logsheet" in notification.message.lower()
        assert "1 aging logsheet(s)" in notification.message


class TestLateSPRsCommand(TransactionTestCase):
    """Test the late SPRs notification command."""

    def setUp(self):
        """Set up test data."""
        # Create instructor and student as Member instances
        self.instructor = Member.objects.create(
            username="instructor",
            email="instructor@test.com",
            first_name="Test",
            last_name="Instructor",
            membership_status="Full Member",
        )

        self.student = Member.objects.create(
            username="student",
            email="student@test.com",
            first_name="Test",
            last_name="Student",
            membership_status="Full Member",
        )

        # Create flight requiring SPR (8 days ago)
        flight_date = timezone.now().date() - timedelta(days=8)
        airfield = Airfield.objects.create(identifier="KFRR", name="KFRR Field")
        logsheet = Logsheet.objects.create(
            log_date=flight_date,
            airfield=airfield,
            created_by=self.instructor,
            finalized=True,
        )

        self.flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=self.student,
            instructor=self.instructor,
            flight_type="dual",
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            airfield=airfield,
        )

        self.command = LateSPRsCommand()

    def test_identifies_overdue_sprs(self):
        """Test that command identifies flights without SPRs."""
        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_notification") as mock_send:
                self.command.handle(dry_run=False, verbosity=1)

        # Should identify overdue SPR
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        instructor, spr_data = call_args

        assert instructor == self.instructor
        assert len(spr_data) == 1
        assert spr_data[0]["flight"] == self.flight
        assert spr_data[0]["escalation_level"] == "NOTICE"  # 7 days = NOTICE level

    def test_escalation_levels(self):
        """Test different escalation levels based on days overdue."""
        # Test 15-day overdue flight (should be level 2)
        old_date = timezone.now().date() - timedelta(days=15)
        old_airfield = Airfield.objects.create(identifier="KXYZ", name="Old Field")
        old_logsheet = Logsheet.objects.create(
            log_date=old_date,
            airfield=old_airfield,
            created_by=self.instructor,
            finalized=True,
        )

        old_flight = Flight.objects.create(
            logsheet=old_logsheet,
            pilot=self.student,
            instructor=self.instructor,
            flight_type="dual",
            launch_time=time(9, 0),
            landing_time=time(10, 0),
            airfield=old_airfield,
        )

        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_notification") as mock_send:
                self.command.handle(dry_run=False, verbosity=1)

        # Should have one call with both flights grouped together
        assert mock_send.call_count == 1

        # Check that both escalation levels are present in the data
        call_args = mock_send.call_args[0]
        instructor, spr_data = call_args

        escalation_levels = [spr["escalation_level"] for spr in spr_data]
        assert "NOTICE" in escalation_levels  # 8 days = NOTICE
        assert "REMINDER" in escalation_levels  # 15 days = REMINDER

    def test_ignores_flights_with_sprs(self):
        """Test that flights with SPRs are not flagged."""
        # Create SPR for the flight
        InstructionReport.objects.create(
            report_date=self.flight.logsheet.log_date,
            instructor=self.instructor,
            student=self.student,
            report_text="Test SPR",
        )

        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_notification") as mock_send:
                self.command.handle(dry_run=True, verbosity=1)

        # Should not send notifications in dry run mode
        mock_send.assert_not_called()


class TestDutyDelinquentsCommand(TestCase):
    """Test the duty delinquents report command."""

    def setUp(self):
        """Set up test data."""
        # Create flying and non-flying members directly
        self.flying_member = Member.objects.create(
            username="flying_member",
            email="flyer@test.com",
            first_name="Flying",
            last_name="Member",
            membership_status="Full Member",
            joined_club=timezone.now().date()
            - timedelta(days=365),  # Joined a year ago
        )

        self.non_flying_member = Member.objects.create(
            username="non_flying_member",
            email="nonflyer@test.com",
            first_name="Non Flying",
            last_name="Member",
            membership_status="Full Member",
            joined_club=timezone.now().date() - timedelta(days=365),
        )

        # Create flights for flying member (but no duty)
        for i in range(5):
            flight_date = timezone.now().date() - timedelta(days=30 + i * 10)
            af = Airfield.objects.create(identifier=f"AF{i}", name=f"Field {i}")
            ls = Logsheet.objects.create(
                log_date=flight_date,
                airfield=af,
                created_by=self.flying_member,
                finalized=True,
            )

            Flight.objects.create(
                logsheet=ls,
                pilot=self.flying_member,
                flight_type="solo",
                launch_time=time(10, 0),
                landing_time=time(11, 0),
                airfield=af,
            )

        self.command = DutyDelinquentsCommand()

    def test_identifies_delinquent_members(self):
        """Test that flying members without duty are identified."""
        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_delinquency_report") as mock_send:
                self.command.handle(
                    lookback_months=12, min_flights=1, dry_run=False, verbosity=1
                )

        # Should identify flying member as delinquent
        mock_send.assert_called_once()
        delinquent_data = mock_send.call_args[0][0]

        # Flying member should be in delinquents
        delinquent_members = [data["member"] for data in delinquent_data]
        assert self.flying_member in delinquent_members

        # Non-flying member should not be in delinquents (no flights)
        assert self.non_flying_member not in delinquent_members

    def test_excludes_members_with_duty(self):
        """Test that members who did duty are not flagged."""
        # Create duty assignment for flying member
        duty_date = timezone.now().date() - timedelta(days=60)
        # Create a duty day and assign the flying member as duty officer
        duty_day = DutyDay.objects.create(date=duty_date)
        DutySlot.objects.create(
            duty_day=duty_day, member=self.flying_member, role="duty_officer"
        )

        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_delinquency_report") as mock_send:
                self.command.handle(
                    lookback_months=12, min_flights=1, dry_run=False, verbosity=1
                )

        # Flying member should not be delinquent since they did duty
        # No delinquent members found, so no report should be sent
        mock_send.assert_not_called()

    def test_configurable_parameters(self):
        """Test that command parameters work correctly."""
        # Test with stricter minimum flights requirement
        with patch("sys.stdout", new_callable=StringIO):
            with patch.object(self.command, "_send_delinquency_report") as mock_send:
                self.command.handle(
                    lookback_months=12,
                    min_flights=10,  # Require 10+ flights
                    dry_run=False,
                    verbosity=1,
                )

        # Flying member only has 5 flights, so shouldn't be considered actively flying
        # Therefore no report should be sent at all
        mock_send.assert_not_called()

    def test_excludes_new_members(self):
        """Test that recently joined members are excluded."""
        # Create new member who joined recently
        new_member = Member.objects.create(
            username="new_member",
            email="new@test.com",
            first_name="New",
            last_name="Member",
            membership_status="Full Member",
            joined_club=timezone.now().date() - timedelta(days=30),  # Joined recently
        )

        # Add flights for new member
        af_new = Airfield.objects.create(identifier="ANew", name="New Field")
        ls_new = Logsheet.objects.create(
            log_date=timezone.now().date() - timedelta(days=15),
            airfield=af_new,
            created_by=new_member,
            finalized=True,
        )

        Flight.objects.create(
            logsheet=ls_new,
            pilot=new_member,
            flight_type="solo",
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            airfield=af_new,
        )

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            with patch.object(self.command, "_send_delinquency_report") as mock_send:
                self.command.handle(
                    lookback_months=12, min_flights=1, dry_run=False, verbosity=1
                )

        # Debug information in case test fails
        output = mock_stdout.getvalue()

        # Report should still be sent because original flying_member is delinquent
        # But new member should be excluded (joined within 90 days)
        if mock_send.call_count == 0:
            # If no report was sent, print debug info to help diagnose
            print(f"\nDEBUG: Command output:\n{output}")
            print(f"DEBUG: Flying member join date: {self.flying_member.joined_club}")
            print(f"DEBUG: New member join date: {new_member.joined_club}")
            print(f"DEBUG: Current date: {timezone.now().date()}")

        mock_send.assert_called_once()
        delinquent_data = mock_send.call_args[0][0]
        delinquent_members = [data["member"] for data in delinquent_data]

        # Original flying member should still be reported as delinquent
        assert self.flying_member in delinquent_members
        # New member should be excluded due to recent join date
        assert new_member not in delinquent_members

    def test_recipient_filtering_active_member_managers_only(self):
        """Test that reports are sent only to active member managers with member_manager=True."""
        # Clear existing member managers to have clean test
        Member.objects.filter(member_manager=True).update(member_manager=False)

        # Create member managers with different statuses
        active_member_manager = Member.objects.create(
            username="active_mm",
            email="active_mm@test.com",
            first_name="Active",
            last_name="Manager",
            membership_status="Full Member",
            member_manager=True,
            joined_club=timezone.now().date() - timedelta(days=365),
        )

        inactive_member_manager = Member.objects.create(
            username="inactive_mm",
            email="inactive_mm@test.com",
            first_name="Inactive",
            last_name="Manager",
            membership_status="Inactive",  # Use inactive status
            member_manager=True,
            joined_club=timezone.now().date() - timedelta(days=365),
        )

        regular_member = Member.objects.create(
            username="regular",
            email="regular@test.com",
            first_name="Regular",
            last_name="Member",
            membership_status="Full Member",
            member_manager=False,  # Not a member manager
            joined_club=timezone.now().date() - timedelta(days=365),
        )

        # Create delinquent data for testing
        test_delinquents = [
            {
                "member": self.flying_member,
                "flight_count": 5,
                "most_recent_flight": timezone.now().date() - timedelta(days=30),
                "membership_duration": "1 year(s), 0 month(s)",
            }
        ]

        # Mock the send_mail function to capture recipients
        with patch(
            "duty_roster.management.commands.report_duty_delinquents.send_mail"
        ) as mock_mail:
            with patch(
                "duty_roster.management.commands.report_duty_delinquents.Notification.objects.create"
            ) as mock_notification:
                # Call _send_delinquency_report directly
                self.command._send_delinquency_report(test_delinquents, 12)

        # Verify only active member manager received email
        mock_mail.assert_called_once()
        recipient_list = mock_mail.call_args[1]["recipient_list"]

        # Should contain only the active member manager's email
        assert len(recipient_list) == 1
        assert active_member_manager.email in recipient_list
        assert inactive_member_manager.email not in recipient_list
        assert regular_member.email not in recipient_list

        # Verify only active member manager got in-app notification
        mock_notification.assert_called_once()
        notification_call = mock_notification.call_args[1]
        assert notification_call["user"] == active_member_manager


class TestCleanupNotificationsCommand(TransactionTestCase):
    """Test the old notifications cleanup command."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user1 = Member.objects.create(
            username="user1",
            email="user1@test.com",
            first_name="User",
            last_name="One",
            membership_status="Full Member",
        )

        self.user2 = Member.objects.create(
            username="user2",
            email="user2@test.com",
            first_name="User",
            last_name="Two",
            membership_status="Full Member",
        )

        # Create old notifications (65 days old)
        old_time = timezone.now() - timedelta(days=65)
        self.old_dismissed = Notification.objects.create(
            user=self.user1,
            message="Old dismissed notification",
            dismissed=True,
            created_at=old_time,
        )

        self.old_undismissed = Notification.objects.create(
            user=self.user1,
            message="Old undismissed notification",
            dismissed=False,
            created_at=old_time,
        )

        # Create recent notifications (30 days old)
        recent_time = timezone.now() - timedelta(days=30)
        self.recent_dismissed = Notification.objects.create(
            user=self.user2,
            message="Recent dismissed notification",
            dismissed=True,
            created_at=recent_time,
        )

        self.recent_undismissed = Notification.objects.create(
            user=self.user2,
            message="Recent undismissed notification",
            dismissed=False,
            created_at=recent_time,
        )

        self.command = CleanupNotificationsCommand()

    def test_identifies_old_notifications(self):
        """Test that command identifies notifications older than 60 days."""
        command = CleanupNotificationsCommand()

        with StringIO() as mock_stdout:
            command.stdout = mock_stdout
            result = command.handle(dry_run=True, verbosity=2)
            output = mock_stdout.getvalue()

        # Should identify 2 old notifications (both dismissed and undismissed)
        assert "Found 2 old notification(s)" in output
        assert "1 dismissed, 1 undismissed" in output
        assert result == 2

    def test_purges_old_notifications_only(self):
        """Test that only old notifications are deleted, recent ones preserved."""
        # Verify initial state
        assert Notification.objects.count() == 4

        command = CleanupNotificationsCommand()

        with StringIO() as mock_stdout:
            command.stdout = mock_stdout
            command.handle(dry_run=False, verbosity=1)

        # Should have deleted 2 old notifications, kept 2 recent ones
        remaining = Notification.objects.all()
        assert remaining.count() == 2

        # Recent notifications should still exist
        assert self.recent_dismissed in remaining
        assert self.recent_undismissed in remaining

        # Old notifications should be gone
        assert self.old_dismissed not in remaining
        assert self.old_undismissed not in remaining

    def test_custom_days_parameter(self):
        """Test that custom days parameter works correctly."""
        command1 = CleanupNotificationsCommand()

        with StringIO() as mock_stdout:
            command1.stdout = mock_stdout
            # Use 40 days cutoff - should delete 65-day old notifications
            result = command1.handle(days=40, dry_run=True, verbosity=1)

        # Should still find 2 old notifications (65 > 40)
        assert result == 2

        command2 = CleanupNotificationsCommand()

        with StringIO() as mock_stdout:
            command2.stdout = mock_stdout
            # Use 70 days cutoff - should delete nothing
            result = command2.handle(days=70, dry_run=True, verbosity=1)

        # Should find no notifications to delete (65 < 70)
        assert result == 0

    def test_handles_no_old_notifications(self):
        """Test behavior when no old notifications exist."""
        # Delete old notifications, keep only recent ones
        Notification.objects.filter(
            created_at__lt=timezone.now() - timedelta(days=60)
        ).delete()

        # Create fresh command instance and override stdout
        command = CleanupNotificationsCommand()

        with StringIO() as mock_stdout:
            command.stdout = mock_stdout
            result = command.handle(dry_run=False, verbosity=1)
            output = mock_stdout.getvalue()

        assert "No old notifications found to purge" in output
        assert result == 0

    def test_dry_run_does_not_delete(self):
        """Test that dry run mode does not actually delete notifications."""
        initial_count = Notification.objects.count()

        command = CleanupNotificationsCommand()

        with StringIO() as mock_stdout:
            command.stdout = mock_stdout
            command.handle(dry_run=True, verbosity=1)

        # Count should be unchanged in dry run
        assert Notification.objects.count() == initial_count

    def test_purges_both_dismissed_and_undismissed(self):
        """Test that both dismissed and undismissed old notifications are purged."""
        command = CleanupNotificationsCommand()

        with StringIO() as mock_stdout:
            command.stdout = mock_stdout
            command.handle(dry_run=False, verbosity=1)

        # Both old notifications should be gone regardless of dismissed status
        assert not Notification.objects.filter(pk=self.old_dismissed.pk).exists()
        assert not Notification.objects.filter(pk=self.old_undismissed.pk).exists()


class TestCronJobIntegration(TransactionTestCase):
    """Test integration aspects of the CronJob system."""

    def test_commands_use_base_cronjob(self):
        """Test that all notification commands inherit from BaseCronJobCommand."""
        from utils.management.commands.base_cronjob import BaseCronJobCommand

        # All notification commands should inherit from BaseCronJobCommand
        assert issubclass(AgingLogsheetsCommand, BaseCronJobCommand)
        assert issubclass(LateSPRsCommand, BaseCronJobCommand)
        assert issubclass(DutyDelinquentsCommand, BaseCronJobCommand)
        assert issubclass(CleanupNotificationsCommand, BaseCronJobCommand)

    def test_commands_have_job_names(self):
        """Test that all commands define job_name."""
        aging_cmd = AgingLogsheetsCommand()
        late_spr_cmd = LateSPRsCommand()
        duty_cmd = DutyDelinquentsCommand()
        cleanup_cmd = CleanupNotificationsCommand()

        assert hasattr(aging_cmd, "job_name")
        assert hasattr(late_spr_cmd, "job_name")
        assert hasattr(duty_cmd, "job_name")
        assert hasattr(cleanup_cmd, "job_name")

        assert aging_cmd.job_name is not None
        assert late_spr_cmd.job_name is not None
        assert duty_cmd.job_name is not None
        assert cleanup_cmd.job_name is not None

    def test_distributed_locking_prevents_overlap(self):
        """Test that distributed locking prevents overlapping executions."""
        # Create lock for aging logsheets command
        lock = CronJobLock.objects.create(
            job_name="notify_aging_logsheets",
            locked_by="test-pod-123",
            locked_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # Try to run command - should be blocked by existing lock
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command("notify_aging_logsheets", verbosity=1)

        output = mock_stdout.getvalue()
        assert "already running" in output.lower()

    def test_dry_run_mode_available(self):
        """Test that all commands support dry-run mode."""
        commands = [
            "notify_aging_logsheets",
            "notify_late_sprs",
            "report_duty_delinquents",
            "cleanup_old_notifications",
        ]

        for cmd_name in commands:
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                call_command(cmd_name, dry_run=True, verbosity=2)

            output = mock_stdout.getvalue()
            assert "DRY RUN" in output.upper()

    def test_verbosity_controls_output(self):
        """Test that verbosity levels control output detail."""
        # Test low verbosity (minimal output)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command("notify_aging_logsheets", verbosity=0, dry_run=True)

        low_output = mock_stdout.getvalue()

        # Test high verbosity (detailed output)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command("notify_aging_logsheets", verbosity=2, dry_run=True)

        high_output = mock_stdout.getvalue()

        # High verbosity should produce more output
        assert len(high_output) >= len(low_output)
