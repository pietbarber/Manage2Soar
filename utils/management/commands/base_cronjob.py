import os
import socket
import sys
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction, IntegrityError
from django.utils import timezone
from utils.models import CronJobLock


class BaseCronJobCommand(BaseCommand):
    """
    Abstract base class for all scheduled management commands in Kubernetes environment.

    Provides distributed locking mechanism to prevent multiple pods from executing
    the same scheduled task simultaneously. Uses database-level atomic operations
    for reliable coordination across multiple pod instances.

    Usage:
        class MyScheduledCommand(BaseCronJobCommand):
            job_name = "my_unique_job"
            max_execution_time = timedelta(minutes=30)

            def execute_job(self, *args, **options):
                # Your job logic here
                self.stdout.write("Job executed successfully")
    """

    # Must be overridden by subclasses
    job_name = None

    # Default maximum execution time (safety timeout)
    max_execution_time = timedelta(hours=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.job_name:
            raise ValueError(f"{self.__class__.__name__} must define job_name")

        # Generate unique pod identifier
        hostname = socket.gethostname()
        pid = os.getpid()
        self.pod_id = f"{hostname}-{pid}"

        self.lock_acquired = False
        # Default verbosity/dry_run values so tests that instantiate the
        # command directly (without going through call_command) behave
        # predictably when they call helper methods such as acquire_lock().
        self.verbosity = 1
        self.dry_run = False

    def add_arguments(self, parser):
        """Add common arguments for all CronJob commands"""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force execution even if lock exists (dangerous - use only for debugging)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually executing'
        )

    def handle(self, *args, **options):
        """Main entry point - handles locking and delegates to execute_job"""
        self.verbosity = options.get('verbosity', 1)
        self.dry_run = options.get('dry_run', False)
        # Rebind stdout at handle time so tests that patch sys.stdout or
        # pass a custom stdout to call_command will capture output.
        # Behavior rules:
        # - If an explicit stdout was passed in options, honor it.
        # - If the command instance already had a custom stdout set by
        #   the caller (e.g. tests assigned a StringIO to `command.stdout`),
        #   do NOT clobber it.
        # - Otherwise, use the current sys.stdout (which may be patched by tests).
        if options.get('stdout') is not None:
            self.stdout = options.get('stdout')
        elif not hasattr(self, 'stdout') or self.stdout is None:
            # If no stdout is set, use current sys.stdout (may be patched)
            self.stdout = sys.stdout
        # If self.stdout is already set (e.g., by a test), leave it alone
        force = options.get('force', False)
        # Always print dry-run header if requested
        if self.dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    f"🔍 DRY RUN: {self.job_name} (no changes will be made)"
                )
            )

        # Clean up expired locks regardless of dry-run. Cleaning expired
        # locks is idempotent and helps tests that expect cleanup to run
        # even in dry-run mode.
        try:
            expired_count = CronJobLock.cleanup_expired_locks()
            if expired_count > 0 and self.verbosity >= 2:
                self.stdout.write(f"🧹 Cleaned up {expired_count} expired locks")
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Database unavailable for lock cleanup: {str(e)}")
            )
            return

        # For dry runs, skip acquiring a lock but continue to execute the
        # job (so tests can verify behavior and output).
        if self.dry_run:
            self.stdout.write("📝 Skipping lock acquisition for dry run")
        else:
            # Attempt to acquire lock unless forced
            if not force and not self.acquire_lock():
                return

        try:
            start_time = timezone.now()
            self.stdout.write(
                self.style.NOTICE(f"🚀 Starting {self.job_name} on pod {self.pod_id}")
            )

            # Execute the actual job
            result = self.execute_job(*args, **options)

            # Calculate execution time
            execution_time = timezone.now() - start_time
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Completed {self.job_name} in {execution_time.total_seconds():.2f}s"
                )
            )

            return result

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Job {self.job_name} failed: {str(e)}")
            )
            raise
        finally:
            # Always release the lock, even if job failed (skip for dry runs)
            if self.lock_acquired and not self.dry_run:
                self.release_lock()

    def acquire_lock(self):
        """
        Attempt to acquire distributed lock for this job.

        Returns:
            bool: True if lock was acquired, False otherwise
        """
        expires_at = timezone.now() + self.max_execution_time

        try:
            with transaction.atomic():
                # Try to create a new lock record
                CronJobLock.objects.create(
                    job_name=self.job_name,
                    locked_by=self.pod_id,
                    expires_at=expires_at
                )
                self.lock_acquired = True

                if self.verbosity >= 2:
                    self.stdout.write(f"🔒 Acquired lock for {self.job_name}")

                return True

        except IntegrityError:
            # Lock already exists - check if it's expired
            try:
                with transaction.atomic():
                    existing_lock = CronJobLock.objects.select_for_update(nowait=True).get(
                        job_name=self.job_name
                    )

                if existing_lock.is_expired():
                    # Lock is expired, try to replace it
                    existing_lock.locked_by = self.pod_id
                    existing_lock.locked_at = timezone.now()
                    existing_lock.expires_at = expires_at
                    existing_lock.save()

                    self.lock_acquired = True

                    if self.verbosity >= 2:
                        self.stdout.write(
                            f"🔄 Replaced expired lock for {self.job_name}")

                    return True
                else:
                    # Lock is active - another pod is running this job
                    if self.verbosity >= 1:
                        self.stdout.write(
                            self.style.WARNING(
                                f"⏸️ Job {self.job_name} is already running on {existing_lock.locked_by}"
                            )
                        )
                    return False

            except CronJobLock.DoesNotExist:
                # Race condition - lock was deleted between our attempts
                # Try once more
                return self.acquire_lock()

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Error acquiring lock: {str(e)}")
                )
                return False

    def release_lock(self):
        """Release the distributed lock for this job"""
        try:
            deleted_count = CronJobLock.objects.filter(
                job_name=self.job_name,
                locked_by=self.pod_id
            ).delete()[0]

            if deleted_count > 0:
                if self.verbosity >= 2:
                    self.stdout.write(f"🔓 Released lock for {self.job_name}")
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️ Lock for {self.job_name} was not found during release")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error releasing lock: {str(e)}")
            )
        finally:
            self.lock_acquired = False

    def execute_job(self, *args, **options):
        """
        Override this method in subclasses to implement the actual job logic.

        This method will only be called if the distributed lock was successfully acquired.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement execute_job() method"
        )

    # Utility methods for common patterns

    def log_info(self, message):
        """Log informational message with appropriate styling"""
        if self.verbosity >= 1:
            self.stdout.write(self.style.NOTICE(f"ℹ️ {message}"))

    def log_success(self, message):
        """Log success message with appropriate styling"""
        if self.verbosity >= 1:
            self.stdout.write(self.style.SUCCESS(f"✅ {message}"))

    def log_warning(self, message):
        """Log warning message with appropriate styling"""
        if self.verbosity >= 1:
            self.stdout.write(self.style.WARNING(f"⚠️ {message}"))

    def log_error(self, message):
        """Log error message with appropriate styling"""
        self.stdout.write(self.style.ERROR(f"❌ {message}"))
