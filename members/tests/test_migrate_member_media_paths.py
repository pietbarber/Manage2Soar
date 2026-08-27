import json
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from members.management.commands import migrate_member_media_paths
from members.models import Biography, Member


def _member_kwargs(username):
    return {
        "username": username,
        "email": f"{username}@example.com",
        "membership_status": "Full Member",
    }


@override_settings(TESTING=True)
class MigrateMemberMediaPathsTests(TestCase):
    """Tests for the resumable legacy media path migration command.

    TESTING=True keeps Member.save() from auto-generating ID-based avatars,
    so tests can reproduce the historical blank-profile-photo state.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="m2s-media-test-"))
        self.media_root = self.temp_dir / "media"
        self.media_root.mkdir()
        self.pending_file = self.temp_dir / "pending.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _call_command(self, *args):
        output = StringIO()
        storage = FileSystemStorage(location=str(self.media_root))
        with mock.patch.object(migrate_member_media_paths, "default_storage", storage):
            call_command(
                "migrate_member_media_paths", *args, stdout=output, stderr=output
            )
        return output.getvalue()

    def _write(self, path, content):
        full = self.media_root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return path

    def _read(self, path):
        return (self.media_root / path).read_bytes()

    def _exists(self, path):
        return (self.media_root / path).exists()

    def _member_with_legacy_avatar(self, username, legacy_path):
        member = Member.objects.create(
            **_member_kwargs(username), profile_photo=legacy_path
        )
        self._write(legacy_path, f"avatar-bytes:{username}".encode("utf-8"))
        return member

    def test_success_copies_avatar_and_updates_field(self):
        member = self._member_with_legacy_avatar(
            "legacy_user", "generated_avatars/profile_legacy_user.png"
        )
        new_path = f"generated_avatars/profile_{member.pk}.png"

        self._call_command("--pending-file", str(self.pending_file))

        member.refresh_from_db()
        self.assertEqual(member.profile_photo, new_path)
        self.assertEqual(
            self._read(new_path),
            self._read("generated_avatars/profile_legacy_user.png"),
        )
        # Manifest must reflect the completed pending copy for resume support.
        pending = json.loads(self.pending_file.read_text(encoding="utf-8"))
        self.assertEqual(
            pending, {"generated_avatars/profile_legacy_user.png": new_path}
        )

    def test_interruption_resume_completes_pending_cleanup(self):
        member = self._member_with_legacy_avatar(
            "resume_user", "generated_avatars/profile_resume_user.png"
        )
        new_path = f"generated_avatars/profile_{member.pk}.png"
        legacy_path = "generated_avatars/profile_resume_user.png"

        # First run migrated the record but simulated an interruption before
        # the cleanup phase, leaving a stale manifest and legacy bytes behind.
        self._write(new_path, self._read(legacy_path))
        Member.objects.filter(pk=member.pk).update(profile_photo=new_path)
        self.pending_file.write_text(
            json.dumps({legacy_path: new_path}), encoding="utf-8"
        )

        # Second run resumes the pending cleanup and deletes the orphaned file.
        self._call_command("--pending-file", str(self.pending_file), "--delete-old")

        self.assertFalse(self._exists(legacy_path))
        member.refresh_from_db()
        self.assertEqual(member.profile_photo, new_path)
        self.assertFalse(self.pending_file.exists())

    def test_preexisting_destination_with_different_bytes_reports_conflict(self):
        member = self._member_with_legacy_avatar(
            "existing_user", "generated_avatars/profile_existing_user.png"
        )
        legacy_path = "generated_avatars/profile_existing_user.png"
        new_path = f"generated_avatars/profile_{member.pk}.png"
        self._write(new_path, b"existing-target-bytes")

        output = self._call_command(
            "--pending-file", str(self.pending_file), "--delete-old"
        )

        member.refresh_from_db()
        self.assertEqual(member.profile_photo, legacy_path)
        # Conflicting destination is preserved, source stays attached and is not deleted.
        self.assertEqual(self._read(legacy_path), b"avatar-bytes:existing_user")
        self.assertEqual(self._read(new_path), b"existing-target-bytes")
        self.assertTrue(self._exists(legacy_path))
        self.assertFalse(self.pending_file.exists())
        self.assertIn("Conflict:", output)

    def test_preexisting_destination_with_matching_bytes_updates_and_cleans_up(self):
        member = self._member_with_legacy_avatar(
            "existing_match", "generated_avatars/profile_existing_match.png"
        )
        legacy_path = "generated_avatars/profile_existing_match.png"
        new_path = f"generated_avatars/profile_{member.pk}.png"
        self._write(new_path, self._read(legacy_path))

        self._call_command("--pending-file", str(self.pending_file), "--delete-old")

        member.refresh_from_db()
        self.assertEqual(member.profile_photo, new_path)
        self.assertEqual(self._read(new_path), b"avatar-bytes:existing_match")
        self.assertFalse(self._exists(legacy_path))
        self.assertFalse(self.pending_file.exists())

    def test_missing_source_is_skipped(self):
        legacy_path = "generated_avatars/profile_missing_user.png"
        member = Member.objects.create(
            **_member_kwargs("missing_user"), profile_photo=legacy_path
        )

        self._call_command("--pending-file", str(self.pending_file))

        member.refresh_from_db()
        # Record is left untouched when the legacy bytes cannot be found.
        self.assertEqual(member.profile_photo, legacy_path)
        self.assertFalse(self.pending_file.exists())

    def test_dry_run_reports_without_writing(self):
        member = self._member_with_legacy_avatar(
            "dryrun_user", "generated_avatars/profile_dryrun_user.png"
        )
        new_path = f"generated_avatars/profile_{member.pk}.png"

        self._call_command("--pending-file", str(self.pending_file), "--dry-run")

        member.refresh_from_db()
        self.assertEqual(
            member.profile_photo, "generated_avatars/profile_dryrun_user.png"
        )
        self.assertFalse(self._exists(new_path))
        self.assertFalse(self.pending_file.exists())

    def test_delete_old_removes_legacy_file_after_migration(self):
        legacy_path = "generated_avatars/profile_delete_user.png"
        member = self._member_with_legacy_avatar("delete_user", legacy_path)
        new_path = f"generated_avatars/profile_{member.pk}.png"

        self._call_command("--pending-file", str(self.pending_file), "--delete-old")

        member.refresh_from_db()
        self.assertEqual(member.profile_photo, new_path)
        self.assertTrue(self._exists(new_path))
        self.assertFalse(self._exists(legacy_path))
        self.assertFalse(self.pending_file.exists())

    def test_relative_pending_file_is_rejected(self):
        with self.assertRaises(CommandError):
            self._call_command("--pending-file", "relative/pending.json")

    def test_biography_upload_uses_member_id_path(self):
        member = Member.objects.create(**_member_kwargs("bio_user"))
        legacy_path = "biography/someone_else/portrait.jpg"
        Biography.objects.create(member=member, uploaded_image=legacy_path)
        self._write(legacy_path, b"biography-bytes")
        new_path = f"biography/{member.pk}/portrait.jpg"

        self._call_command("--pending-file", str(self.pending_file))

        biography = Biography.objects.get(member=member)
        self.assertEqual(biography.uploaded_image, new_path)
        self.assertEqual(self._read(new_path), b"biography-bytes")

    def test_blank_photo_member_with_legacy_username_avatar_is_migrated(self):
        """Historical save() wrote profile_<username>.png without setting
        profile_photo, so most legacy generated avatars are blank-photo members.
        The command must probe the legacy path, copy the bytes, and attach the
        new ID-based path to the field."""
        member = Member.objects.create(
            **_member_kwargs("legacy_blank"), profile_photo=""
        )
        legacy_path = "generated_avatars/profile_legacy_blank.png"
        new_path = f"generated_avatars/profile_{member.pk}.png"
        self._write(legacy_path, f"legacy-bytes:{member.pk}".encode("utf-8"))

        self._call_command("--pending-file", str(self.pending_file), "--delete-old")

        member.refresh_from_db()
        self.assertEqual(member.profile_photo, new_path)
        self.assertEqual(
            self._read(new_path), f"legacy-bytes:{member.pk}".encode("utf-8")
        )
        self.assertFalse(self._exists(legacy_path))
        self.assertFalse(self.pending_file.exists())

    def test_blank_photo_member_without_legacy_avatar_is_skipped(self):
        member = Member.objects.create(**_member_kwargs("no_avatar"), profile_photo="")

        output = self._call_command("--pending-file", str(self.pending_file))

        member.refresh_from_db()
        self.assertFalse(member.profile_photo)
        self.assertFalse(self.pending_file.exists())
        self.assertNotIn("Migrate:", output)

    def test_cleanup_pending_requires_destination_db_reference(self):
        member = Member.objects.create(
            **_member_kwargs("partial_copy"), profile_photo=""
        )
        legacy_path = "generated_avatars/profile_partial_copy.png"
        new_path = f"generated_avatars/profile_{member.pk}.png"
        self._write(legacy_path, b"correct-source-bytes")
        self._write(new_path, b"partial-destination-bytes")
        self.pending_file.write_text(
            json.dumps({legacy_path: new_path}), encoding="utf-8"
        )

        self._call_command("--pending-file", str(self.pending_file), "--delete-old")

        # Destination is unreferenced, so cleanup must defer deletion.
        self.assertTrue(self._exists(legacy_path))
        self.assertTrue(self.pending_file.exists())
