from datetime import date
from unittest.mock import patch

import pytest
from django.core.management import call_command

from logsheet.models import (
    Airfield,
    FinalizationEmailOutbox,
    Logsheet,
    LogsheetCloseout,
)
from logsheet.utils.finalization_email import enqueue_finalization_summary_email_job
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
class TestFinalizationEmailOutboxCommand:
    @pytest.fixture(autouse=True)
    def setup(self):
        MembershipStatus.objects.update_or_create(
            name="Full Member",
            defaults={"is_active": True},
        )
        self.airfield = Airfield.objects.create(identifier="KOUT", name="Outbox Field")
        self.member = Member.objects.create_user(
            username="duty",
            password="testpass",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
            is_active=True,
            email="duty@example.com",
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date(2025, 9, 1),
            airfield=self.airfield,
            created_by=self.member,
            duty_officer=self.member,
            finalized=True,
        )
        LogsheetCloseout.objects.create(
            logsheet=self.logsheet,
            operations_summary="<p>Done.</p>",
        )

    @patch("logsheet.utils.finalization_email.send_mail")
    def test_command_processes_pending_outbox_to_sent(self, mock_send_mail):
        outbox = enqueue_finalization_summary_email_job(self.logsheet.pk)
        self.assert_pending(outbox)

        call_command("process_finalization_email_outbox", limit=10, verbosity=0)

        outbox.refresh_from_db()
        assert outbox.status == FinalizationEmailOutbox.STATUS_SENT
        assert outbox.processed_at is not None
        assert outbox.attempt_count == 1
        assert mock_send_mail.called

    @patch(
        "logsheet.utils.finalization_email.send_mail",
        side_effect=Exception("SMTP down"),
    )
    def test_command_marks_failed_when_delivery_fails(self, mock_send_mail):
        outbox = enqueue_finalization_summary_email_job(self.logsheet.pk)

        call_command("process_finalization_email_outbox", limit=10, verbosity=0)

        outbox.refresh_from_db()
        assert outbox.status == FinalizationEmailOutbox.STATUS_FAILED
        assert outbox.attempt_count == 1
        assert "Failed to deliver" in outbox.last_error
        assert mock_send_mail.called

    @staticmethod
    def assert_pending(outbox):
        outbox.refresh_from_db()
        assert outbox.status == FinalizationEmailOutbox.STATUS_PENDING
        assert outbox.processed_at is None
