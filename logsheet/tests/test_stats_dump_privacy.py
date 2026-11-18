import importlib
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage, storages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import clear_url_caches, reverse
from django.utils import timezone

from logsheet.models import StatsDumpOutbox
from logsheet.stats_storage import StatsDumpStorage, stats_dump_upload_to
from logsheet.utils.stats_dump import process_stats_dump_outbox_job
from manage2soar.storage_backends import (
    PrivateStatsDumpFileSystemStorage,
    PrivateStatsDumpGCS,
)
from members.models import Member

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("private_stats_storage")]


@pytest.fixture
def export():
    owner = Member.objects.create_user(
        username="stats-owner", membership_status="Full Member", stats_monger=True
    )
    job = StatsDumpOutbox.objects.create(
        requested_by=owner,
        status=StatsDumpOutbox.STATUS_READY,
        completed_at=timezone.now(),
        result_filename="stats.csv",
    )
    job.result_file.save("stats.csv", ContentFile(b"flight_tracking_id\n1\n"))
    return job


def download(client, job):
    return client.get(reverse("logsheet:stats_dump_export_download", args=[job.pk]))


@pytest.mark.parametrize(
    "identity",
    ["anonymous", "non-stats", "other-owner", "inactive", "owner", "superuser"],
)
def test_download_permissions_and_cache_headers(client, export, identity):
    if identity == "owner":
        user = export.requested_by
    elif identity != "anonymous":
        user = Member.objects.create_user(
            username=identity,
            membership_status=(
                "Inactive" if identity in ("inactive", "superuser") else "Full Member"
            ),
            stats_monger=identity in ("other-owner", "inactive"),
            is_superuser=identity == "superuser",
        )
        if identity in ("non-stats", "inactive"):
            export.requested_by = user
            export.save(update_fields=["requested_by"])
    if identity != "anonymous":
        client.force_login(user)
    response = download(client, export)
    expected = (
        200
        if identity in ("owner", "superuser")
        else (302 if identity in ("anonymous", "inactive") else 403)
    )
    assert response.status_code == expected
    assert "private" in response["Cache-Control"]
    assert "no-store" in response["Cache-Control"]
    if expected == 200:
        assert b"".join(response.streaming_content) == b"flight_tracking_id\n1\n"


@pytest.mark.parametrize(
    "field,value",
    [("stats_monger", False), ("membership_status", "Inactive"), ("is_active", False)],
)
def test_download_rechecks_revoked_permission(client, export, field, value):
    client.force_login(export.requested_by)
    first = download(client, export)
    assert first.status_code == 200
    assert b"".join(first.streaming_content)
    Member.objects.filter(pk=export.requested_by_id).update(**{field: value})
    assert download(client, export).status_code in (302, 403)


def test_names_are_random_and_storage_has_no_urls(export, settings):
    name = export.result_file.name
    assert name.startswith(settings.CLUB_PREFIX + "/")
    assert name != stats_dump_upload_to(export, "stats.csv")
    with pytest.raises(NotImplementedError):
        _ = export.result_file.url
    with pytest.raises(NotImplementedError):
        storages["stats_dumps"].url(name)
    assert not default_storage.exists(name)
    path = Path(settings.STATS_DUMP_ROOT) / name
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_two_tenants_with_overlapping_job_ids_cannot_read_each_other(client, export):
    client.force_login(export.requested_by)
    # Keep the same DB job/user IDs to model two independent tenant databases.
    # A foreign reference must fail even for a superuser in the second tenant.
    with override_settings(CLUB_PREFIX="other-club"):
        assert download(client, export).status_code == 410
        with pytest.raises(SuspiciousFileOperation):
            StatsDumpStorage().open(export.result_file.name)
        foreign_name = stats_dump_upload_to(export, "stats.csv")
        StatsDumpStorage().save(foreign_name, ContentFile(b"other club"))
    with pytest.raises(SuspiciousFileOperation):
        StatsDumpStorage().open(foreign_name)
    assert export.result_file.read() == b"flight_tracking_id\n1\n"


@pytest.mark.parametrize(
    "name",
    [
        "../ssc/test.csv",
        "exports/stats_dumps/old.csv",
        "/ssc/test.csv",
        "ssc/../other/test.csv",
    ],
)
def test_storage_rejects_legacy_and_traversal_names(name):
    with pytest.raises(SuspiciousFileOperation):
        StatsDumpStorage().open(name)
    with pytest.raises(SuspiciousFileOperation):
        StatsDumpStorage().save(name, ContentFile(b"private"))


@pytest.mark.parametrize("bucket", [None, "public-media"])
def test_gcs_fails_closed_without_distinct_private_bucket(settings, bucket):
    settings.GS_BUCKET_NAME = "public-media"
    settings.GS_IMPORT_EXPORT_BUCKET_NAME = bucket
    with pytest.raises(ImproperlyConfigured):
        PrivateStatsDumpGCS()


def test_private_gcs_options_override_public_defaults(settings):
    settings.GS_BUCKET_NAME = "public-media"
    settings.GS_IMPORT_EXPORT_BUCKET_NAME = "private-data"
    settings.GS_DEFAULT_ACL = "publicRead"
    settings.GS_OBJECT_PARAMETERS = {"cache_control": "public, max-age=3600"}
    backend = PrivateStatsDumpGCS()
    assert backend.bucket_name == "private-data"
    assert backend.location == "stats-dumps"
    assert backend.default_acl is None
    assert backend.querystring_auth is True
    assert backend.object_parameters["cache_control"] == "private, no-store, max-age=0"
    with pytest.raises(NotImplementedError):
        backend.url("known.csv")


def test_generation_does_not_fall_back_to_media(settings, export):
    settings.STORAGES = {
        k: v for k, v in settings.STORAGES.items() if k != "stats_dumps"
    }
    job = StatsDumpOutbox.objects.create(requested_by=export.requested_by)
    with patch(
        "logsheet.utils.stats_dump.iter_stats_dump_rows",
        return_value=iter([["header"]]),
    ):
        process_stats_dump_outbox_job(job.pk)
    job.refresh_from_db()
    assert job.status == StatsDumpOutbox.STATUS_FAILED
    assert not job.result_file
    assert not list(Path(settings.MEDIA_ROOT).rglob("*.csv"))


@pytest.mark.parametrize("root_setting", ["MEDIA_ROOT", "STATIC_ROOT", "BASE_DIR"])
def test_local_root_cannot_overlap_served_directories(settings, root_setting):
    settings.STATS_DUMP_ROOT = str(Path(getattr(settings, root_setting)) / "stats")
    with pytest.raises(ImproperlyConfigured):
        PrivateStatsDumpFileSystemStorage()


def test_local_production_requires_private_root(settings):
    settings.DEBUG = False
    settings.STATS_DUMP_ROOT = None
    with pytest.raises(ImproperlyConfigured):
        PrivateStatsDumpFileSystemStorage()


def test_expired_and_missing_files_return_gone(client, export):
    client.force_login(export.requested_by)
    export.completed_at = timezone.now() - timedelta(days=8)
    export.save(update_fields=["completed_at"])
    assert download(client, export).status_code == 410
    export.completed_at = timezone.now()
    export.save(update_fields=["completed_at"])
    export.result_file.storage.delete(export.result_file.name)
    assert download(client, export).status_code == 410


def test_worker_expires_private_exports_but_preserves_legacy_inventory(export):
    original_name = export.result_file.name
    export.completed_at = timezone.now() - timedelta(days=8)
    export.save(update_fields=["completed_at"])
    legacy = StatsDumpOutbox.objects.create(
        status=StatsDumpOutbox.STATUS_READY,
        result_file="exports/stats_dumps/old.csv",
        completed_at=export.completed_at,
    )
    call_command("process_stats_dump_outbox", verbosity=0)
    export.refresh_from_db()
    legacy.refresh_from_db()
    assert export.status == StatsDumpOutbox.STATUS_EXPIRED
    assert not export.result_file
    assert not storages["stats_dumps"].exists(original_name)
    assert legacy.result_file.name == "exports/stats_dumps/old.csv"
    process_stats_dump_outbox_job(export.pk)
    export.refresh_from_db()
    assert export.status == StatsDumpOutbox.STATUS_EXPIRED


def test_worker_dry_run_does_not_delete_expired_exports(export):
    export.completed_at = timezone.now() - timedelta(days=8)
    export.save(update_fields=["completed_at"])
    call_command("process_stats_dump_outbox", dry_run=True, verbosity=0)
    export.refresh_from_db()
    assert export.status == StatsDumpOutbox.STATUS_READY
    assert export.result_file.storage.exists(export.result_file.name)


@pytest.fixture
def legacy_export(export):
    name = default_storage.save(
        "exports/stats_dumps/legacy.csv", ContentFile(b"old data")
    )
    export.result_file = name
    export.save(update_fields=["result_file"])
    return export


def test_retirement_inventory_includes_orphans_then_removes_only_exports(
    legacy_export, client
):
    orphan = default_storage.save(
        "exports/stats_dumps/orphan.csv", ContentFile(b"orphan")
    )
    public = default_storage.save("photos/public.jpg", ContentFile(b"public"))
    out = StringIO()
    call_command("retire_public_stats_dumps", stdout=out)
    inventory = json.loads(out.getvalue())
    assert inventory["objects"] == sorted([legacy_export.result_file.name, orphan])
    assert inventory["jobs"][0]["id"] == legacy_export.pk
    assert default_storage.exists(orphan)
    client.force_login(legacy_export.requested_by)
    assert download(client, legacy_export).status_code == 410
    call_command("retire_public_stats_dumps", apply=True, stdout=StringIO())
    assert not default_storage.exists(orphan)
    assert not default_storage.exists(legacy_export.result_file.name)
    assert default_storage.exists(public)
    legacy_export.refresh_from_db()
    assert legacy_export.status == StatsDumpOutbox.STATUS_EXPIRED
    assert not legacy_export.result_file
    call_command("retire_public_stats_dumps", apply=True, stdout=StringIO())


def test_retirement_preserves_reference_on_delete_failure(legacy_export):
    name = legacy_export.result_file.name
    with patch.object(
        default_storage, "delete", side_effect=OSError("storage unavailable")
    ):
        with pytest.raises(OSError):
            call_command("retire_public_stats_dumps", apply=True, stdout=StringIO())
    legacy_export.refresh_from_db()
    assert legacy_export.result_file.name == name
    assert default_storage.exists(name)


@pytest.mark.parametrize("symlink_legacy_root", [False, True])
def test_retirement_rejects_symlink_to_unrelated_local_directory(
    symlink_legacy_root,
):
    media_root = Path(default_storage.location)
    unrelated = media_root / "unrelated-files"
    unrelated.mkdir(parents=True)
    protected_file = unrelated / "keep.csv"
    protected_file.write_text("do not delete")

    legacy_root = media_root / "exports" / "stats_dumps"
    legacy_root.parent.mkdir(parents=True)
    if symlink_legacy_root:
        legacy_root.symlink_to(unrelated, target_is_directory=True)
    else:
        legacy_root.mkdir()
        (legacy_root / "unrelated-files").symlink_to(
            unrelated, target_is_directory=True
        )

    with pytest.raises(CommandError, match="symlink"):
        call_command("retire_public_stats_dumps", apply=True, stdout=StringIO())

    assert protected_file.read_text() == "do not delete"


def test_retirement_rejects_running_workers(legacy_export):
    StatsDumpOutbox.objects.create(status=StatsDumpOutbox.STATUS_PROCESSING)
    with pytest.raises(CommandError, match="Stop and drain"):
        call_command("retire_public_stats_dumps", apply=True, stdout=StringIO())
    assert default_storage.exists(legacy_export.result_file.name)


def test_development_media_blocks_legacy_exports_but_serves_public_assets(
    client, legacy_export, settings
):
    public = default_storage.save("photos/public.txt", ContentFile(b"public"))
    import manage2soar.urls

    try:
        with override_settings(DEBUG=True, MEDIA_URL="/media/"):
            importlib.reload(manage2soar.urls)
            clear_url_caches()
            assert (
                client.get("/media/" + legacy_export.result_file.name).status_code
                == 404
            )
            for legacy_path in (
                "/media/exports//stats_dumps/legacy.csv",
                "/media/exports/x/../stats_dumps/legacy.csv",
            ):
                assert client.get(legacy_path).status_code == 404
            response = client.get("/media/" + public)
            assert response.status_code == 200
            assert b"".join(response.streaming_content) == b"public"
    finally:
        importlib.reload(manage2soar.urls)
        clear_url_caches()


def test_stats_lifecycle_is_separate_from_one_day_import_staging():
    path = (
        Path(__file__).resolve().parents[2]
        / "infrastructure/ansible/files/gcs-import-export-lifecycle.json"
    )
    rules = json.loads(path.read_text())["rule"]
    assert {
        "action": {"type": "Delete"},
        "condition": {"age": 7, "matchesPrefix": ["stats-dumps/"]},
    } in rules
    assert {
        "action": {"type": "Delete"},
        "condition": {"age": 1, "matchesPrefix": ["django-import-export/"]},
    } in rules
