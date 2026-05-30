from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from duty_roster.models import DutySwapRequest
from duty_roster.views_swap import send_request_expired_notifications
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = (
        "Expire open duty swap requests for dates in the past and auto-decline "
        "their pending offers"
    )
    job_name = "expire_past_swap_requests"
    max_execution_time = timedelta(
        minutes=5
    )  # Matches K8s CronJob activeDeadlineSeconds=300

    def execute_job(self, *args, **options):
        today = timezone.now().date()
        dry_run = options.get("dry_run", False)

        stale_request_ids = list(
            DutySwapRequest.objects.filter(
                status="open",
                original_date__lt=today,
            ).values_list("id", flat=True)
        )

        if not stale_request_ids:
            self.log_info("No past-dated open duty swap requests found")
            return

        expired_count = 0
        declined_offers_count = 0
        skipped_count = 0

        for request_id in stale_request_ids:
            with transaction.atomic():
                swap_request = DutySwapRequest.objects.select_for_update().get(
                    pk=request_id
                )

                if swap_request.status != "open" or swap_request.original_date >= today:
                    skipped_count += 1
                    continue

                pending_offers = list(
                    swap_request.offers.select_for_update().filter(status="pending")
                )

                if dry_run:
                    self.log_info(
                        f"[DRY RUN] Would expire swap request {swap_request.pk} "
                        f"for {swap_request.original_date} and auto-decline "
                        f"{len(pending_offers)} pending offer(s)"
                    )
                    expired_count += 1
                    declined_offers_count += len(pending_offers)
                    continue

                now_ts = timezone.now()
                swap_request.status = "expired"
                swap_request.save(update_fields=["status", "updated_at"])

                for offer in pending_offers:
                    offer.status = "auto_declined"
                    offer.responded_at = now_ts
                    offer.save(update_fields=["status", "responded_at"])

                transaction.on_commit(
                    lambda req=swap_request, offers=pending_offers: send_request_expired_notifications(
                        req,
                        auto_declined_offers=offers,
                    )
                )

                expired_count += 1
                declined_offers_count += len(pending_offers)

        if dry_run:
            self.log_info(
                "[DRY RUN] Would expire "
                f"{expired_count} request(s) and auto-decline "
                f"{declined_offers_count} offer(s); skipped {skipped_count}"
            )
            return

        self.log_success(
            f"Expired {expired_count} request(s) and auto-declined "
            f"{declined_offers_count} offer(s); skipped {skipped_count}"
        )
