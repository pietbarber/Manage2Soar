from datetime import timedelta

from django.db import models
from django.utils import timezone


class CronJobLock(models.Model):
    """
    Distributed locking mechanism for CronJobs in Kubernetes multi-pod environment.

    Prevents multiple pods from executing the same scheduled task simultaneously
    by using database-level atomic operations for lock acquisition and release.
    """

    job_name = models.CharField(
        max_length=100, unique=True, help_text="Unique identifier for the scheduled job"
    )
    locked_by = models.CharField(
        max_length=100, help_text="Pod identifier (hostname + process ID)"
    )
    locked_at = models.DateTimeField(
        # Use a callable default so test code can pass an explicit value and
        # comparisons are deterministic; avoid auto_now_add which can make
        # test-created timestamps differ slightly.
        default=timezone.now,
        help_text="When the lock was acquired",
    )
    expires_at = models.DateTimeField(
        help_text="When the lock expires (safety mechanism for crashed pods)"
    )

    class Meta:
        db_table = "cronjob_locks"
        verbose_name = "CronJob Lock"
        verbose_name_plural = "CronJob Locks"
        indexes = [
            models.Index(fields=["job_name"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        # Tests expect a compact representation like: "job_name (locked_by)"
        return f"{self.job_name} ({self.locked_by})"

    def is_expired(self):
        """Check if the lock has expired"""
        return timezone.now() > self.expires_at

    @classmethod
    def cleanup_expired_locks(cls):
        """Remove expired locks from the database"""
        expired_count = cls.objects.filter(expires_at__lt=timezone.now()).count()
        if expired_count > 0:
            cls.objects.filter(expires_at__lt=timezone.now()).delete()
            return expired_count
        return 0
