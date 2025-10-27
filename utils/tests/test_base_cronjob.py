"""
Test suite for BaseCronJobCommand - the foundation of our CronJob system.

Tests distributed locking, error handling, logging, and dry-run functionality.
These tests ensure the core framework works reliably across multiple pods.
"""
import pytest
import socket
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock 
from io import StringIO

from django.test import TestCase, TransactionTestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction, connection
from django.utils import timezone

from utils.models import CronJobLock
from utils.management.commands.base_cronjob import BaseCronJobCommand


class TestCronJobLock(TestCase):
    """Test the CronJobLock model that provides distributed locking."""
    
    def test_lock_creation(self):
        """Test basic lock creation and fields."""
        lock = CronJobLock.objects.create(
            job_name="test_job",
            locked_by="test-pod-123",
            locked_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        assert lock.job_name == "test_job"
        assert lock.locked_by == "test-pod-123"
        assert lock.locked_at is not None
        assert lock.expires_at is not None
        assert not lock.is_expired()
        
    def test_lock_expiration(self):
        """Test lock expiration logic."""
        # Create an expired lock
        now = timezone.now()
        expired_lock = CronJobLock.objects.create(
            job_name="expired_job",
            locked_by="old-pod",
            locked_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1)  # Expired 1 hour ago
        )
        
        assert expired_lock.is_expired()
        
        # Create a fresh lock
        fresh_lock = CronJobLock.objects.create(
            job_name="fresh_job", 
            locked_by="new-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        assert not fresh_lock.is_expired()
        
    def test_unique_constraint(self):
        """Test that only one lock per job can exist."""
        now = timezone.now()
        CronJobLock.objects.create(
            job_name="unique_test",
            locked_by="pod1",
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        # Second lock with same job_name should fail
        with pytest.raises(Exception):  # IntegrityError
            CronJobLock.objects.create(
                job_name="unique_test",
                locked_by="pod2", 
                locked_at=now,
                expires_at=now + timedelta(hours=1)
            )
            
    def test_string_representation(self):
        """Test the string representation of locks."""
        now = timezone.now()
        lock = CronJobLock.objects.create(
            job_name="test_repr",
            locked_by="test-pod", 
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        expected = "test_repr (test-pod)"
        assert str(lock) == expected
        
    def test_cleanup_expired_locks(self):
        """Test the cleanup_expired_locks class method."""
        now = timezone.now()
        
        # Create expired lock
        CronJobLock.objects.create(
            job_name="expired1",
            locked_by="dead-pod",
            locked_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1)
        )
        
        # Create fresh lock
        CronJobLock.objects.create(
            job_name="fresh1",
            locked_by="live-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        # Cleanup should remove expired locks
        cleaned_count = CronJobLock.cleanup_expired_locks()
        assert cleaned_count == 1
        
        # Only fresh lock should remain
        remaining_locks = list(CronJobLock.objects.all())
        assert len(remaining_locks) == 1
        assert remaining_locks[0].job_name == "fresh1"


class TestBaseCronJobCommand(TransactionTestCase):
    """Test the BaseCronJobCommand abstract base class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a concrete implementation for testing
        class TestCommand(BaseCronJobCommand):
            job_name = "test_command"
            
            def execute_job(self, *args, **options):
                return "Test execution completed"
                
        self.command_class = TestCommand
        self.command = self.command_class()
        
    def test_job_name_required(self):
        """Test that job_name is required."""
        class NoNameCommand(BaseCronJobCommand):
            pass  # No job_name defined
            
        with pytest.raises(ValueError, match="must define job_name"):
            NoNameCommand()
            
    def test_pod_id_generation(self):
        """Test that pod_id is generated correctly."""
        pod_id = self.command.pod_id
        
        # Should be in format: hostname-pid
        assert isinstance(pod_id, str)
        assert len(pod_id) > 0
        
        # Should contain hostname and pid
        hostname = socket.gethostname()
        pid = str(os.getpid())
        assert hostname in pod_id
        assert pid in pod_id
        
    def test_lock_acquisition_success(self):
        """Test successful lock acquisition."""
        success = self.command.acquire_lock()
        
        assert success is True
        assert self.command.lock_acquired is True
        
        # Verify lock exists in database
        lock = CronJobLock.objects.get(job_name="test_command")
        assert lock.locked_by == self.command.pod_id
        
    def test_lock_acquisition_failure(self):
        """Test lock acquisition failure when lock already exists."""
        # Create existing non-expired lock
        now = timezone.now()
        CronJobLock.objects.create(
            job_name="test_command",
            locked_by="other-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        success = self.command.acquire_lock()
        assert success is False
        assert self.command.lock_acquired is False
        
    def test_lock_acquisition_expired_lock_replacement(self):
        """Test that expired locks are replaced."""
        # Create expired lock
        now = timezone.now()
        CronJobLock.objects.create(
            job_name="test_command",
            locked_by="dead-pod",
            locked_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1)
        )
        
        # Should acquire lock successfully after replacing expired one
        success = self.command.acquire_lock()
        assert success is True
        assert self.command.lock_acquired is True
        
        # Verify lock now belongs to current pod
        lock = CronJobLock.objects.get(job_name="test_command")
        assert lock.locked_by == self.command.pod_id
        
    def test_lock_release(self):
        """Test lock release functionality."""
        # Acquire lock first
        self.command.acquire_lock()
        assert CronJobLock.objects.filter(job_name="test_command").exists()
        
        # Release lock
        self.command.release_lock()
        assert not CronJobLock.objects.filter(job_name="test_command").exists()
        assert self.command.lock_acquired is False
        
    def test_lock_release_other_pod(self):
        """Test that we can't release locks from other pods."""
        # Create lock from different pod
        now = timezone.now()
        CronJobLock.objects.create(
            job_name="test_command",
            locked_by="different-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        # Should not be able to release (no error, but lock remains)
        self.command.release_lock()
        
        # Lock should still exist
        assert CronJobLock.objects.filter(job_name="test_command").exists()
        lock = CronJobLock.objects.get(job_name="test_command")
        assert lock.locked_by == "different-pod"
        
    @patch('utils.management.commands.base_cronjob.BaseCronJobCommand.execute_job')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_successful_execution(self, mock_stdout, mock_execute):
        """Test successful command execution flow."""
        mock_execute.return_value = None
        
        # Test normal execution
        self.command.handle(verbosity=1)
        
        output = mock_stdout.getvalue()
        assert "�" in output  # Starting emoji
        assert "✅" in output  # Success emoji
        
        mock_execute.assert_called_once()
        
        # Verify lock was released
        assert not CronJobLock.objects.filter(job_name="test_command").exists()
        
    @patch('utils.management.commands.base_cronjob.BaseCronJobCommand.execute_job')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_dry_run(self, mock_stdout, mock_execute):
        """Test dry-run mode execution."""
        mock_execute.return_value = None
        
        self.command.handle(dry_run=True, verbosity=2)
        
        output = mock_stdout.getvalue()
        assert "🔍" in output  # Dry run emoji
        assert "DRY RUN" in output.upper()
        assert "Skipping lock acquisition" in output
        
        mock_execute.assert_called_once_with(dry_run=True, verbosity=2)
        
        # No locks should be created in dry run
        assert not CronJobLock.objects.filter(job_name="test_command").exists()
        
    @patch('utils.management.commands.base_cronjob.BaseCronJobCommand.execute_job')
    @patch('sys.stdout', new_callable=StringIO)
    def test_handle_execution_error(self, mock_stdout, mock_execute):
        """Test handling of execution errors."""
        mock_execute.side_effect = Exception("Test error occurred")
        
        with pytest.raises(Exception):
            self.command.handle(verbosity=1)
            
        output = mock_stdout.getvalue()
        assert "❌" in output  # Error emoji
        
        # Lock should still be released despite error
        assert not CronJobLock.objects.filter(job_name="test_command").exists()
        
    def test_handle_lock_acquisition_failure(self):
        """Test behavior when lock acquisition fails."""
        # Create existing lock
        now = timezone.now()
        CronJobLock.objects.create(
            job_name="test_command",
            locked_by="other-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            self.command.handle(verbosity=1)
            
        output = mock_stdout.getvalue()
        assert "⏸️" in output  # Skip emoji
        assert "already running" in output.lower()
        
    def test_force_execution(self):
        """Test force execution bypasses lock check."""
        # Create existing lock
        now = timezone.now()
        CronJobLock.objects.create(
            job_name="test_command",
            locked_by="other-pod",
            locked_at=now,
            expires_at=now + timedelta(hours=1)
        )
        
        with patch('utils.management.commands.base_cronjob.BaseCronJobCommand.execute_job') as mock_execute:
            with patch('sys.stdout', new_callable=StringIO):
                self.command.handle(force=True, verbosity=1)
                
        # Should execute despite existing lock
        mock_execute.assert_called_once()
        
    def test_add_arguments(self):
        """Test that standard arguments are added correctly."""
        parser = Mock()
        self.command.add_arguments(parser)
        
        # Verify force argument was added
        parser.add_argument.assert_any_call(
            '--force',
            action='store_true',
            help='Force execution even if lock exists (dangerous - use only for debugging)'
        )
        
        # Verify dry-run argument was added
        parser.add_argument.assert_any_call(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually executing'
        )
        
    def test_utility_logging_methods(self):
        """Test the utility logging methods."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            self.command.verbosity = 1
            
            self.command.log_info("Test info message")
            self.command.log_success("Test success message") 
            self.command.log_warning("Test warning message")
            self.command.log_error("Test error message")
            
        output = mock_stdout.getvalue()
        assert "ℹ️ Test info message" in output
        assert "✅ Test success message" in output
        assert "⚠️ Test warning message" in output
        assert "❌ Test error message" in output
        
    def test_must_implement_execute_job(self):
        """Test that execute_job must be implemented."""
        class IncompleteCommand(BaseCronJobCommand):
            job_name = "incomplete"
            # No execute_job implementation
            
        command = IncompleteCommand()
        
        with pytest.raises(NotImplementedError):
            command.execute_job()


class TestCronJobCommandIntegration(TransactionTestCase):
    """Integration tests for the complete CronJob system."""
    
    def setUp(self):
        """Set up integration test fixtures."""
        class IntegrationTestCommand(BaseCronJobCommand):
            job_name = "integration_test"
            
            def execute_job(self, *args, **options):
                if options.get('should_fail'):
                    raise Exception("Intentional test failure")
                return "Integration test completed"
                
        self.command_class = IntegrationTestCommand
        
    @patch('socket.gethostname')
    @patch('os.getpid')
    def test_concurrent_execution_prevention(self, mock_getpid, mock_hostname):
        """Test that concurrent executions are properly prevented."""
        # Set up different pod identities
        mock_hostname.side_effect = ["host1", "host2"]
        mock_getpid.side_effect = [1001, 1002]
        
        command1 = self.command_class()
        command2 = self.command_class()
        
        # First command should acquire lock
        success1 = command1.acquire_lock()
        assert success1 is True
        
        # Second command should fail to acquire
        success2 = command2.acquire_lock()
        assert success2 is False
        
        # Release lock from first command
        command1.release_lock()
        
        # Now second command should succeed
        success2_retry = command2.acquire_lock()
        assert success2_retry is True
        
    def test_expired_lock_takeover(self):
        """Test that expired locks can be taken over by new processes."""
        # Create expired lock
        now = timezone.now()
        CronJobLock.objects.create(
            job_name="integration_test",
            locked_by="dead-pod-123",
            locked_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1)
        )
        
        command = self.command_class()
        
        # Should be able to acquire expired lock
        success = command.acquire_lock()
        assert success is True
        
        # Verify lock now belongs to current pod
        lock = CronJobLock.objects.get(job_name="integration_test")
        assert lock.locked_by == command.pod_id
        assert not lock.is_expired()
        
    @patch('sys.stdout', new_callable=StringIO)
    def test_end_to_end_execution(self, mock_stdout):
        """Test complete end-to-end command execution."""
        command = self.command_class()
        
        # Execute command normally
        command.handle(verbosity=2)
        
        output = mock_stdout.getvalue()
        
        # Verify complete execution flow
        assert "🚀" in output  # Starting
        assert "🔒" in output or "Acquired lock" in output  # Lock acquired
        assert "✅" in output  # Completed 
        assert "Integration test completed" not in output  # Return value not printed
        
        # Verify no lock remains
        assert not CronJobLock.objects.filter(
            job_name="integration_test"
        ).exists()
        
    @patch('sys.stdout', new_callable=StringIO)
    def test_error_handling_with_cleanup(self, mock_stdout):
        """Test that errors are handled gracefully with proper cleanup."""
        command = self.command_class()
        
        # Execute with intentional failure
        with pytest.raises(Exception):
            command.handle(should_fail=True, verbosity=2)
            
        output = mock_stdout.getvalue()
        
        # Verify error handling
        assert "❌" in output  # Error emoji
        
        # Verify lock was cleaned up despite error
        assert not CronJobLock.objects.filter(
            job_name="integration_test"
        ).exists()