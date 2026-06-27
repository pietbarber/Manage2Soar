from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from logsheet.management.commands.process_stats_dump_outbox import MAX_ATTEMPTS
from logsheet.models import Airfield, Flight, Glider, Logsheet, StatsDumpOutbox
from logsheet.utils.stats_dump import (
    MAX_LAST_ERROR_LENGTH,
    iter_stats_dump_rows,
    process_stats_dump_outbox_job,
)
from members.models import Member


@pytest.mark.django_db
class TestStatsDumpOutboxCommand:
    @pytest.fixture(autouse=True)
    def setup(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        self.requester = Member.objects.create_user(
            username="stats_requester",
            password="testpass",
            membership_status="Full Member",
            stats_monger=True,
            first_name="Stats",
            last_name="Requester",
        )
        self.pilot = Member.objects.create_user(
            username="stats_pilot",
            password="testpass",
            membership_status="Full Member",
            first_name="Pilot",
            last_name="One",
        )
        self.airfield = Airfield.objects.create(identifier="KTS1", name="Stats Field")
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N321AA",
            rental_rate=Decimal("45.00"),
            club_owned=True,
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today() - timedelta(days=1),
            airfield=self.airfield,
            created_by=self.requester,
            finalized=False,
        )
        Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.pilot,
            glider=self.glider,
            flight_type="Dual",
            launch_time=time(10, 0, 0),
            landing_time=time(10, 20, 0),
            release_altitude=2200,
        )

    def test_command_generates_ready_export(self):
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_PENDING,
        )

        call_command("process_stats_dump_outbox", limit=10, verbosity=0)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_READY
        assert outbox.result_file
        assert outbox.completed_at is not None
        assert outbox.attempt_count == 1

        content = outbox.result_file.read().decode("utf-8")
        assert "flight_tracking_id" in content
        assert "Pilot One" in content
        assert "KTS1" in content

    @patch(
        "logsheet.utils.stats_dump.iter_stats_dump_rows", side_effect=Exception("boom")
    )
    def test_command_marks_failed_when_generation_errors(self, _mock_rows):
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_PENDING,
        )

        call_command("process_stats_dump_outbox", limit=10, verbosity=0)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_FAILED
        assert outbox.attempt_count == 1
        assert "boom" in outbox.last_error

    def test_command_skips_jobs_at_max_attempts(self):
        """Jobs that have exhausted MAX_ATTEMPTS retries are not re-queued."""
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_FAILED,
            attempt_count=MAX_ATTEMPTS,
        )

        call_command("process_stats_dump_outbox", limit=10, verbosity=0)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_FAILED
        assert outbox.attempt_count == MAX_ATTEMPTS

    def test_process_job_skips_already_processing_job(self, settings, tmp_path):
        """process_stats_dump_outbox_job is idempotent for STATUS_PROCESSING."""
        settings.MEDIA_ROOT = str(tmp_path)
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_PROCESSING,
            attempt_count=1,
        )

        process_stats_dump_outbox_job(outbox.pk)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_PROCESSING
        assert outbox.attempt_count == 1

    def test_process_job_skips_already_ready_job(self, settings, tmp_path):
        """process_stats_dump_outbox_job is idempotent for STATUS_READY."""
        settings.MEDIA_ROOT = str(tmp_path)
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_READY,
            attempt_count=1,
        )

        process_stats_dump_outbox_job(outbox.pk)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_READY
        assert outbox.attempt_count == 1

    def test_command_recovers_stale_processing_job(self):
        """Stale processing jobs are moved back into retry flow."""
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_PROCESSING,
            started_at=timezone.now() - timedelta(hours=1),
            attempt_count=0,
        )

        call_command("process_stats_dump_outbox", limit=10, verbosity=0)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_READY
        assert outbox.attempt_count == 1

    @patch(
        "logsheet.utils.stats_dump.iter_stats_dump_rows",
        side_effect=Exception("x" * 5000),
    )
    def test_process_job_truncates_last_error(self, _mock_rows):
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_PENDING,
        )

        process_stats_dump_outbox_job(outbox.pk)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_FAILED
        assert len(outbox.last_error) == MAX_LAST_ERROR_LENGTH

    @patch("logsheet.utils.stats_dump.logger.exception")
    @patch(
        "logsheet.utils.stats_dump.iter_stats_dump_rows",
        side_effect=Exception("boom"),
    )
    def test_process_job_logs_exception_when_generation_fails(
        self,
        _mock_rows,
        mock_log_exception,
    ):
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_PENDING,
        )

        process_stats_dump_outbox_job(outbox.pk)

        mock_log_exception.assert_called_once()

    def test_process_job_refreshes_completed_at_on_retry(self):
        stale_completed_at = timezone.now() - timedelta(days=2)
        outbox = StatsDumpOutbox.objects.create(
            requested_by=self.requester,
            status=StatsDumpOutbox.STATUS_FAILED,
            completed_at=stale_completed_at,
        )

        process_stats_dump_outbox_job(outbox.pk)

        outbox.refresh_from_db()
        assert outbox.status == StatsDumpOutbox.STATUS_READY
        assert outbox.completed_at is not None
        assert outbox.completed_at > stale_completed_at

    def test_iter_stats_dump_rows_orders_by_flight_date(self):
        older_logsheet = Logsheet.objects.create(
            log_date=self.logsheet.log_date - timedelta(days=7),
            airfield=self.airfield,
            created_by=self.requester,
            finalized=False,
        )
        Flight.objects.create(
            logsheet=older_logsheet,
            pilot=self.pilot,
            glider=self.glider,
            flight_type="Dual",
            launch_time=time(9, 0, 0),
            landing_time=time(9, 20, 0),
            release_altitude=2000,
        )

        rows = list(iter_stats_dump_rows())
        data_rows = rows[1:]

        assert len(data_rows) >= 2
        flight_dates = [row[1] for row in data_rows]
        assert flight_dates == sorted(flight_dates)
