from datetime import date, timedelta

from django.conf import settings
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from instructors.utils import (
    PENDING_SPR_NOTIFICATION_FRAGMENT,
    get_pending_sprs_for_date,
)
from logsheet.models import Logsheet
from notifications.models import Notification
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.management.commands.base_cronjob import BaseCronJobCommand
from utils.url_helpers import build_absolute_url, get_canonical_url


class Command(BaseCronJobCommand):
    help = "Notify instructors about pending SPRs from a finalized flying day"
    job_name = "notify_pending_sprs"
    max_execution_time = timedelta(minutes=10)

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--days-ago",
            type=int,
            default=None,
            help="Send reminders for finalized flights from N days ago",
        )
        parser.add_argument(
            "--flight-date",
            type=lambda value: date.fromisoformat(value),
            help="Override target flight date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--max-days",
            type=int,
            default=30,
            help="Maximum number of past days to search for pending SPRs when no date is specified (default: 30)",
        )

    def execute_job(self, *args, **options):
        today = timezone.now().date()
        pending_sprs = None  # may be pre-populated by the default discovery loop
        if options.get("flight_date"):
            target_date = options["flight_date"]
        elif options.get("days_ago") is not None:
            # Explicit --days-ago override: compute from UTC midnight.
            target_date = today - timedelta(days=options["days_ago"])
        else:
            # Default: find the most recent finalized flying day that still
            # has at least one pending SPR. Bounded to --max-days (default 30)
            # to avoid scanning the full Logsheet history on quiet days and
            # risking the 10-minute CronJob deadline.
            max_days = options["max_days"]
            search_start = today - timedelta(days=max_days)
            recent_dates = (
                Logsheet.objects.filter(
                    finalized=True,
                    log_date__lt=today,
                    log_date__gte=search_start,
                    flights__instructor__isnull=False,
                )
                .order_by("-log_date")
                .values_list("log_date", flat=True)
                .distinct()
            )
            target_date = None
            for candidate_date in recent_dates:
                result = get_pending_sprs_for_date(candidate_date)
                if not result:
                    continue
                # Skip this date if every eligible instructor has already
                # received a notification for it. Without this check, the job
                # would stall on a fully-notified newer date and never fall back
                # to older dates that still need a first reminder (e.g., when
                # multiple logsheets are finalized late on different days).
                date_iso = candidate_date.isoformat()
                already_notified_ids = set(
                    Notification.objects.filter(user__in=result.keys())
                    .filter(
                        Q(message__contains=PENDING_SPR_NOTIFICATION_FRAGMENT)
                        & Q(message__contains=date_iso)
                    )
                    .values_list("user_id", flat=True)
                )
                eligible = [
                    instr for instr in result if instr.pk not in already_notified_ids
                ]
                if eligible:
                    target_date = candidate_date
                    # Reuse the already-fetched result to avoid a second query
                    # for the same date immediately after this loop.
                    pending_sprs = result
                    break
            if target_date is None:
                self.log_info(
                    f"No finalized logsheets with pending SPRs found in the last {max_days} days"
                )
                return
        self.log_info(
            f"Checking for pending SPRs from finalized flights on {target_date}"
        )

        # Use the result cached during date discovery; fall back to an explicit
        # query when a date was supplied via --flight-date or --days-ago.
        if pending_sprs is None:
            pending_sprs = get_pending_sprs_for_date(target_date)
        if not pending_sprs:
            self.log_info("No pending SPRs found")
            return

        total_instructors = len(pending_sprs)
        total_pending = sum(len(sprs) for sprs in pending_sprs.values())
        self.log_info(
            f"Found {total_pending} pending SPRs for {total_instructors} instructor(s)"
        )

        # Load global config once to avoid repeated DB queries per instructor.
        config = SiteConfiguration.objects.first()
        canonical_base = get_canonical_url(config)

        notifications_sent = 0
        for instructor, spr_data in pending_sprs.items():
            if options.get("dry_run"):
                self.log_info(
                    f"Would notify {instructor.full_display_name} about {len(spr_data)} pending SPR(s) from {target_date}"
                )
                continue

            try:
                if self._send_notification(
                    instructor, spr_data, target_date, config, canonical_base
                ):
                    notifications_sent += 1
            except Exception as e:
                self.log_error(f"Failed to notify {instructor.full_display_name}: {e}")

        if notifications_sent:
            self.log_success(
                f"Sent pending SPR reminders to {notifications_sent} instructor(s)"
            )
        else:
            self.log_info("No reminders sent")

    def _send_notification(
        self, instructor, spr_data, target_date, config, canonical_base
    ):
        message = (
            f"You have {len(spr_data)} {PENDING_SPR_NOTIFICATION_FRAGMENT}(s) "
            f"from {target_date.isoformat()}."
        )
        existing = Notification.objects.filter(
            user=instructor,
        ).filter(
            Q(message__contains=PENDING_SPR_NOTIFICATION_FRAGMENT)
            & Q(message__contains=target_date.isoformat())
        )
        if existing.exists():
            self.log_info(
                f"Skipping duplicate pending SPR reminder for {instructor.full_display_name} on {target_date}"
            )
            return False

        dashboard_url = build_absolute_url("/instructors/", canonical=canonical_base)
        pending_sprs = [
            {
                "student_name": spr["student"].full_display_name,
                "report_url": build_absolute_url(
                    reverse(
                        "instructors:fill_instruction_report",
                        args=[spr["student"].pk, target_date],
                    ),
                    canonical=canonical_base,
                ),
            }
            for spr in spr_data
        ]

        context = {
            "instructor_name": instructor.full_display_name,
            "flight_date": target_date.strftime("%A, %B %d, %Y"),
            "pending_sprs": pending_sprs,
            "pending_count": len(pending_sprs),
            "club_name": config.club_name if config else "Soaring Club",
            "club_logo_url": get_absolute_club_logo_url(config),
            "dashboard_url": dashboard_url,
            "site_url": canonical_base,
        }

        subject = (
            "Student Progress Report Reminder - "
            f"{len(pending_sprs)} Pending Report(s) from {target_date.strftime('%B %d, %Y')}"
        )
        html_message = render_to_string(
            "instructors/emails/pending_sprs_notification.html", context
        )
        text_message = render_to_string(
            "instructors/emails/pending_sprs_notification.txt", context
        )

        # Let send_mail() normalise the sender via enforce_noreply_from_email()
        # so From headers are correct even when DEFAULT_FROM_EMAIL is in
        # "Name <addr@domain>" format.
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or (
            f"noreply@{config.domain_name}"
            if config and config.domain_name
            else "noreply@manage2soar.com"
        )

        if not instructor.email:
            self.log_info(
                f"Skipping {instructor.full_display_name}: no email address on file"
            )
            return False

        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[instructor.email],
            html_message=html_message,
            fail_silently=False,
        )

        # Use a relative URL for the in-app notification so it stays on the
        # current host rather than redirecting to the canonical domain.
        Notification.objects.create(
            user=instructor,
            message=message,
            url="/instructors/",
        )
        self.log_success(
            f"Notified {instructor.full_display_name} about {len(pending_sprs)} pending SPR(s)"
        )
        return True
