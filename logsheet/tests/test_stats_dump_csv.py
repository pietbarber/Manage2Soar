import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from logsheet.models import StatsDumpOutbox
from members.models import Member


@pytest.mark.django_db
def test_stats_dump_csv_requires_stats_monger_permission(client):
    user = Member.objects.create_user(
        username="no_stats_access",
        password="pass",
        membership_status="Full Member",
        stats_monger=False,
    )
    client.force_login(user)

    resp = client.get(reverse("logsheet:stats_dump_csv"))

    assert resp.status_code == 403


@pytest.mark.django_db
def test_stats_dump_csv_queues_job_and_redirects_to_status(client):
    requester = Member.objects.create_user(
        username="stats_owner",
        password="pass",
        membership_status="Full Member",
        stats_monger=True,
    )

    client.force_login(requester)
    resp = client.get(reverse("logsheet:stats_dump_csv"))

    assert resp.status_code == 302
    outbox = StatsDumpOutbox.objects.get()
    assert outbox.requested_by == requester
    assert outbox.status == StatsDumpOutbox.STATUS_PENDING
    assert resp.url == reverse("logsheet:stats_dump_export_status", args=[outbox.pk])


@pytest.mark.django_db
def test_stats_dump_status_rejects_other_non_superusers(client):
    requester = Member.objects.create_user(
        username="stats_owner_access",
        password="pass",
        membership_status="Full Member",
        stats_monger=True,
    )
    other = Member.objects.create_user(
        username="stats_other_access",
        password="pass",
        membership_status="Full Member",
        stats_monger=True,
    )
    outbox = StatsDumpOutbox.objects.create(requested_by=requester)

    client.force_login(other)
    resp = client.get(reverse("logsheet:stats_dump_export_status", args=[outbox.pk]))

    assert resp.status_code == 403


@pytest.mark.django_db
def test_stats_dump_download_returns_file_for_ready_export(client, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    requester = Member.objects.create_user(
        username="stats_owner_download",
        password="pass",
        membership_status="Full Member",
        stats_monger=True,
    )
    outbox = StatsDumpOutbox.objects.create(
        requested_by=requester,
        status=StatsDumpOutbox.STATUS_READY,
        completed_at=timezone.now(),
        result_filename="stats_dump_test.csv",
    )
    outbox.result_file.save(
        "stats_dump_test.csv",
        ContentFile("flight_tracking_id\n1\n"),
        save=True,
    )

    client.force_login(requester)
    resp = client.get(reverse("logsheet:stats_dump_export_download", args=[outbox.pk]))

    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert 'attachment; filename="stats_dump_test.csv"' in resp["Content-Disposition"]


@pytest.mark.django_db
def test_stats_dump_download_redirects_when_not_ready(client):
    requester = Member.objects.create_user(
        username="stats_owner_waiting",
        password="pass",
        membership_status="Full Member",
        stats_monger=True,
    )
    outbox = StatsDumpOutbox.objects.create(
        requested_by=requester,
        status=StatsDumpOutbox.STATUS_PENDING,
    )

    client.force_login(requester)
    resp = client.get(
        reverse("logsheet:stats_dump_export_download", args=[outbox.pk]),
        follow=False,
    )

    assert resp.status_code == 302
    assert resp.url == reverse("logsheet:stats_dump_export_status", args=[outbox.pk])
