"""
Simplified test suite for the notification management commands.

Tests the actual production commands with minimal mocking to verify core functionality.
"""

from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from utils.models import CronJobLock


class TestCronJobCommandIntegration(TransactionTestCase):
    """Test integration aspects of the CronJob system."""

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

    def test_commands_inherit_from_base_cronjob(self):
        """Test that all notification commands inherit from BaseCronJobCommand."""
        from duty_roster.management.commands.notify_aging_logsheets import (
            Command as AgingLogsheetsCommand,
        )
        from duty_roster.management.commands.report_duty_delinquents import (
            Command as DutyDelinquentsCommand,
        )
        from instructors.management.commands.notify_late_sprs import (
            Command as LateSPRsCommand,
        )
        from utils.management.commands.base_cronjob import BaseCronJobCommand

        # All notification commands should inherit from BaseCronJobCommand
        assert issubclass(AgingLogsheetsCommand, BaseCronJobCommand)
        assert issubclass(LateSPRsCommand, BaseCronJobCommand)
        assert issubclass(DutyDelinquentsCommand, BaseCronJobCommand)

    def test_commands_have_job_names(self):
        """Test that all commands define job_name."""
        from duty_roster.management.commands.notify_aging_logsheets import (
            Command as AgingLogsheetsCommand,
        )
        from duty_roster.management.commands.report_duty_delinquents import (
            Command as DutyDelinquentsCommand,
        )
        from instructors.management.commands.notify_late_sprs import (
            Command as LateSPRsCommand,
        )

        aging_cmd = AgingLogsheetsCommand()
        late_spr_cmd = LateSPRsCommand()
        duty_cmd = DutyDelinquentsCommand()

        assert hasattr(aging_cmd, "job_name")
        assert hasattr(late_spr_cmd, "job_name")
        assert hasattr(duty_cmd, "job_name")

        assert aging_cmd.job_name is not None
        assert late_spr_cmd.job_name is not None
        assert duty_cmd.job_name is not None

    def test_force_flag_bypasses_locks(self):
        """Test that --force flag bypasses distributed locking."""
        # Create lock for command
        lock = CronJobLock.objects.create(
            job_name="notify_aging_logsheets",
            locked_by="other-pod-456",
            locked_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # Run with force flag - should execute despite lock
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command(
                "notify_aging_logsheets", force=True, dry_run=True, verbosity=1
            )

        output = mock_stdout.getvalue()
        # Should show execution, not lock conflict
        assert "DRY RUN" in output.upper()
        assert "already running" not in output.lower()

    def test_expired_locks_are_cleaned_up(self):
        """Test that expired locks are automatically cleaned up."""
        # Create expired lock
        expired_lock = CronJobLock.objects.create(
            job_name="notify_aging_logsheets",
            locked_by="dead-pod-789",
            locked_at=timezone.now() - timedelta(hours=2),
            expires_at=timezone.now() - timedelta(hours=1),  # Expired 1 hour ago
        )

        # Run command - should clean up expired lock and execute
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command("notify_aging_logsheets", dry_run=True, verbosity=2)

        output = mock_stdout.getvalue()
        assert "DRY RUN" in output.upper()
        assert "Cleaned up" in output or "cleaned up" in output

        # Expired lock should be removed
        assert not CronJobLock.objects.filter(
            job_name="notify_aging_logsheets"
        ).exists()


class TestCronJobLockModel(TestCase):
    """Test the CronJobLock model functionality."""

    def test_lock_creation_and_basic_fields(self):
        """Test creating locks and basic field access."""
        now = timezone.now()
        lock = CronJobLock.objects.create(
            job_name="test_job",
            locked_by="test-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1),
        )

        assert lock.job_name == "test_job"
        assert lock.locked_by == "test-pod"
        assert lock.locked_at == now
        assert not lock.is_expired()

    def test_lock_expiration_detection(self):
        """Test that expired locks are correctly identified."""
        now = timezone.now()

        # Create expired lock
        expired_lock = CronJobLock.objects.create(
            job_name="expired_job",
            locked_by="old-pod",
            locked_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )

        assert expired_lock.is_expired()

        # Create fresh lock
        fresh_lock = CronJobLock.objects.create(
            job_name="fresh_job",
            locked_by="new-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1),
        )

        assert not fresh_lock.is_expired()

    def test_unique_job_name_constraint(self):
        """Test that job names must be unique."""
        now = timezone.now()

        # Create first lock
        CronJobLock.objects.create(
            job_name="unique_test",
            locked_by="pod1",
            locked_at=now,
            expires_at=now + timedelta(hours=1),
        )

        # Try to create second lock with same job_name - should fail
        with pytest.raises(Exception):  # IntegrityError or similar
            CronJobLock.objects.create(
                job_name="unique_test",
                locked_by="pod2",
                locked_at=now,
                expires_at=now + timedelta(hours=1),
            )

    def test_cleanup_expired_locks_class_method(self):
        """Test the cleanup_expired_locks class method."""
        now = timezone.now()

        # Create mix of expired and fresh locks
        expired_lock1 = CronJobLock.objects.create(
            job_name="expired1",
            locked_by="dead-pod1",
            locked_at=now - timedelta(hours=3),
            expires_at=now - timedelta(hours=2),
        )

        fresh_lock = CronJobLock.objects.create(
            job_name="fresh1",
            locked_by="live-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1),
        )

        # Run cleanup
        cleaned_count = CronJobLock.cleanup_expired_locks()

        # Should clean up 1 expired lock
        assert cleaned_count == 1

        # Only fresh lock should remain
        remaining_locks = list(CronJobLock.objects.all())
        assert len(remaining_locks) == 1
        assert remaining_locks[0].job_name == "fresh1"


class TestCommandExecutionFlow(TransactionTestCase):
    """Test the complete command execution flow end-to-end."""

    def test_successful_command_execution_flow(self):
        """Test complete successful execution with lock acquire/release cycle."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command("notify_aging_logsheets", dry_run=True, verbosity=2)

        output = mock_stdout.getvalue()

        # Should show complete flow
        assert "Starting notify_aging_logsheets" in output
        assert "DRY RUN" in output.upper()
        assert "Completed notify_aging_logsheets" in output

        # No locks should remain after successful execution
        assert not CronJobLock.objects.filter(
            job_name="notify_aging_logsheets"
        ).exists()

    def test_parameter_passing_works(self):
        """Test that command-specific parameters are passed correctly."""
        # Test aging logsheets with custom days parameter
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command("notify_aging_logsheets", days=14, dry_run=True, verbosity=2)

        output = mock_stdout.getvalue()
        assert "14 days" in output

        # Test duty delinquents with custom parameters
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            call_command(
                "report_duty_delinquents",
                lookback_months=6,
                min_flights=5,
                dry_run=True,
                verbosity=2,
            )

        output = mock_stdout.getvalue()
        # Should show 6 months back from Oct 2025 (around May)
        assert "2025-05" in output
        assert "5" in output  # Should mention minimum flights
