from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TransactionTestCase
from django.utils import timezone

from utils.models import CronJobLock


class BaseCronJobCommandTest(TransactionTestCase):
    """Test the base CronJob command functionality"""

    def setUp(self):
        # Clean up any existing locks
        CronJobLock.objects.all().delete()

    def tearDown(self):
        # Clean up locks after each test
        CronJobLock.objects.all().delete()

    def test_dry_run_skips_locking(self):
        """Test that dry run mode skips database locking operations"""
        out = StringIO()

        call_command("test_cronjob", "--dry-run", "--verbosity=2", stdout=out)

        output = out.getvalue()
        self.assertIn("🔍 DRY RUN", output)
        self.assertIn("📝 Skipping lock acquisition", output)
        self.assertIn("✅ Framework is working correctly!", output)

        # No locks should be created in dry run
        self.assertEqual(CronJobLock.objects.count(), 0)

    def test_successful_lock_acquisition_and_release(self):
        """Test normal lock acquisition and release cycle"""
        out = StringIO()

        # Mock database operations to avoid connection issues in tests
        with patch("utils.models.CronJobLock.cleanup_expired_locks", return_value=0):
            with patch("utils.models.CronJobLock.objects.create") as mock_create:
                with patch("utils.models.CronJobLock.objects.filter") as mock_filter:
                    # Setup mock for successful lock creation
                    mock_create.return_value = MagicMock()

                    # Setup mock for lock deletion (release)
                    mock_delete = MagicMock()
                    mock_delete.delete.return_value = (
                        1,
                        {"utils.CronJobLock": 1},
                    )  # (count, details)
                    mock_filter.return_value = mock_delete

                    call_command("test_cronjob", "--verbosity=2", stdout=out)

        output = out.getvalue()
        self.assertIn("🚀 Starting test_cronjob", output)
        self.assertIn("✅ Completed test_cronjob", output)

        # Verify lock was attempted to be created
        mock_create.assert_called_once()

        # Verify lock release was attempted
        mock_filter.assert_called_with(
            job_name="test_cronjob", locked_by=mock_create.call_args[1]["locked_by"]
        )

    def test_concurrent_execution_prevention(self):
        """Test that existing lock prevents second execution"""
        # Create an active lock
        existing_lock = CronJobLock.objects.create(
            job_name="test_cronjob",
            locked_by="other-pod-123",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        out = StringIO()

        with patch("utils.models.CronJobLock.cleanup_expired_locks", return_value=0):
            call_command("test_cronjob", "--verbosity=2", stdout=out)

        output = out.getvalue()
        self.assertIn("⏸️ Job test_cronjob is already running on other-pod-123", output)

        # Original lock should still exist unchanged
        existing_lock.refresh_from_db()
        self.assertEqual(existing_lock.locked_by, "other-pod-123")

    def test_expired_lock_replacement(self):
        """Test that expired locks are replaced with new ones"""
        # Create an expired lock
        expired_lock = CronJobLock.objects.create(
            job_name="test_cronjob",
            locked_by="old-pod-456",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        out = StringIO()

        with patch("utils.models.CronJobLock.cleanup_expired_locks", return_value=0):
            # Mock the execute_job to avoid database issues in test
            with patch(
                "utils.management.commands.test_cronjob.Command.execute_job"
            ) as mock_execute:
                mock_execute.return_value = "Test completed"

                call_command("test_cronjob", "--verbosity=2", stdout=out)

        output = out.getvalue()
        self.assertIn("🔄 Replaced expired lock", output)
        self.assertIn("🚀 Starting test_cronjob", output)

        # Lock should be deleted after successful command completion
        # (commands always release their locks when done)
        with self.assertRaises(CronJobLock.DoesNotExist):
            expired_lock.refresh_from_db()

    def test_lock_cleanup_on_startup(self):
        """Test that expired locks are cleaned up when command starts"""
        # Create multiple expired locks
        CronJobLock.objects.create(
            job_name="old_job_1",
            locked_by="dead-pod-1",
            expires_at=timezone.now() - timedelta(hours=2),
        )
        CronJobLock.objects.create(
            job_name="old_job_2",
            locked_by="dead-pod-2",
            expires_at=timezone.now() - timedelta(minutes=30),
        )

        out = StringIO()

        # Mock the specific command execution to focus on cleanup
        with patch(
            "utils.management.commands.test_cronjob.Command.execute_job"
        ) as mock_execute:
            mock_execute.return_value = "Test completed"

            call_command("test_cronjob", "--verbosity=2", stdout=out)

        output = out.getvalue()
        self.assertIn("🧹 Cleaned up 2 expired locks", output)

        # All locks should be gone after command completion
        # (expired locks cleaned up + command lock released)
        remaining_locks = list(CronJobLock.objects.all())
        self.assertEqual(len(remaining_locks), 0)

    def test_force_option_bypasses_locking(self):
        """Test that --force option bypasses lock acquisition"""
        # Create an active lock that would normally block execution
        CronJobLock.objects.create(
            job_name="test_cronjob",
            locked_by="blocking-pod",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        out = StringIO()

        with patch("utils.models.CronJobLock.cleanup_expired_locks", return_value=0):
            call_command("test_cronjob", "--force", "--verbosity=2", stdout=out)

        output = out.getvalue()
        self.assertIn("🚀 Starting test_cronjob", output)
        self.assertIn("✅ Completed test_cronjob", output)
        # Should not show the "already running" message
        self.assertNotIn("already running", output)

    def test_command_failure_still_releases_lock(self):
        """Test that lock is released even if command execution fails"""
        out = StringIO()

        with patch("utils.models.CronJobLock.cleanup_expired_locks", return_value=0):
            with patch("utils.models.CronJobLock.objects.create") as mock_create:
                with patch("utils.models.CronJobLock.objects.filter") as mock_filter:
                    # Setup mocks
                    mock_create.return_value = MagicMock()
                    mock_delete = MagicMock()
                    mock_delete.delete.return_value = (1, {"utils.CronJobLock": 1})
                    mock_filter.return_value = mock_delete

                    # Mock execute_job to raise an exception
                    with patch(
                        "utils.management.commands.test_cronjob.Command.execute_job"
                    ) as mock_execute:
                        mock_execute.side_effect = Exception("Simulated failure")

                        # Command should raise exception but still attempt lock release
                        with self.assertRaises(Exception):
                            call_command("test_cronjob", "--verbosity=2", stdout=out)

        # Verify lock release was still attempted despite failure
        mock_filter.assert_called_once()

    def test_verbosity_levels(self):
        """Test different verbosity levels control output"""
        # Test verbosity 0 (minimal output)
        out_quiet = StringIO()
        with patch("utils.models.CronJobLock.cleanup_expired_locks", return_value=0):
            with patch(
                "utils.management.commands.test_cronjob.Command.execute_job",
                return_value="Done",
            ):
                call_command("test_cronjob", "--verbosity=0", stdout=out_quiet)

        quiet_output = out_quiet.getvalue()

        # Test verbosity 2 (verbose output)
        out_verbose = StringIO()
        with patch("utils.models.CronJobLock.cleanup_expired_locks", return_value=0):
            with patch(
                "utils.management.commands.test_cronjob.Command.execute_job",
                return_value="Done",
            ):
                call_command("test_cronjob", "--verbosity=2", stdout=out_verbose)

        verbose_output = out_verbose.getvalue()

        # Verbose should contain more detail
        self.assertGreater(len(verbose_output), len(quiet_output))
        self.assertIn("🔒 Acquired lock", verbose_output)


def expected_hostname_prefix():
    """Helper to get expected hostname prefix for lock identification"""
    import socket

    return socket.gethostname().split("-")[0]  # Get hostname without random suffix
