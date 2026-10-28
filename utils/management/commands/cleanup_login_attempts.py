"""
CronJob command that cleans up stale django-axes rows (Issue #1110).

django-axes (v8) stores two kinds of per-attempt rows in PostgreSQL:

- ``axes.models.AccessAttempt`` — one row per (username, IP, user-agent)
  combination, with a ``failures_since_start`` counter and an
  ``AccessAttemptExpiration`` sidecar that holds the cool-off deadline.
  This is what the throttle budget is computed from.
- ``axes.models.AccessFailureLog`` — one row per failed login, kept for
  auditing.

Without cleanup both tables grow unboundedly — in a production deployment
behind a load balancer, every attempt from every user on the internet
lands on the same row set (the IP column is the *real* client IP thanks
to ``AXES_CLIENT_IP_CALLABLE`` in ``manage2soar/settings.py``).

This command deletes rows older than 24 hours.  The 24 h horizon is well
past the 15-minute ``AXES_COOLOFF_TIME`` window, so deleting old rows
cannot break an in-flight throttle.

Scheduled via the ``cleanup-login-attempts`` CronJob in ``k8s-cronjobs.yaml``
(Ansible template: ``infrastructure/ansible/roles/gke-deploy/templates/k8s-cronjobs.yml.j2``)
to run hourly.  The ``BaseCronJobCommand`` base class provides distributed
locking so multiple pods don't race on the same cleanup.
"""

from datetime import timedelta

from django.utils import timezone

from utils.management.commands.base_cronjob import BaseCronJobCommand

# Rows older than this horizon are safe to delete (well past the 15-min
# AXES_COOLOFF_TIME window used by Issue #1110).
RETENTION_HOURS = 24


class Command(BaseCronJobCommand):
    help = "Delete stale django-axes AccessAttempt/AccessFailureLog rows (Issue #1110 cleanup)."
    job_name = "cleanup_login_attempts"
    max_execution_time = timedelta(minutes=5)

    def execute_job(self, *args, **options):
        # Local import keeps the module importable even if axes is absent
        # (e.g. in a test harness that doesn't install it).
        from axes.models import AccessAttempt, AccessFailureLog

        cutoff = timezone.now() - timedelta(hours=RETENTION_HOURS)

        if options.get("dry_run"):
            attempt_count = AccessAttempt.objects.filter(
                attempt_time__lt=cutoff
            ).count()
            failure_count = AccessFailureLog.objects.filter(
                attempt_time__lt=cutoff
            ).count()
            self.log_info(
                f"Would delete {attempt_count} AccessAttempt row(s) and "
                f"{failure_count} AccessFailureLog row(s) older than {RETENTION_HOURS} h"
            )
            return

        # AccessAttempt is a OneToOne source of AccessAttemptExpiration, so
        # deleting the attempt cascades to its expiration row automatically.
        deleted_details = {}
        for model in (AccessAttempt, AccessFailureLog):
            deleted, _details = model.objects.filter(attempt_time__lt=cutoff).delete()
            deleted_details[model.__name__] = deleted

        total_deleted = sum(deleted_details.values())
        self.log_success(
            f"Deleted {deleted_details} row(s) older than {RETENTION_HOURS} h"
            f" (total: {total_deleted})"
        )
        # Return None (not the int count): BaseCronJobCommand.handle propagates
        # this to call_command(), which would otherwise do stdout.write(int)
        # and raise TypeError.  The count is already logged above.
        return None
