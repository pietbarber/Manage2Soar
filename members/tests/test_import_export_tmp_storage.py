import json
from pathlib import Path

from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import StorageHandler
from django.test import TestCase
from import_export.tmp_storages import MediaStorage, TempFolderStorage

from manage2soar.storage_backends import PrivateImportExportGCS
from members.admin import MemberAdmin
from members.models import Member


class MemberImportTmpStorageTests(TestCase):
    """Tests for issue #1071: cross-pod shared tmp storage for import/export.

    On GKE (2 replicas), the default TempFolderStorage writes to pod-local /tmp.
    MediaStorage uses a dedicated private import/export bucket in production.
    """

    def test_member_admin_uses_shared_media_storage(self):
        """MemberAdmin must resolve to the shared MediaStorage, not pod-local /tmp."""
        instance = MemberAdmin(Member, admin.site)
        self.assertIs(instance.get_tmp_storage_class(), MediaStorage)
        self.assertIsNot(instance.get_tmp_storage_class(), TempFolderStorage)

    def test_media_storage_round_trip_and_cleanup(self):
        """save -> read -> remove must work through the active shared backend."""
        payload = b"username,first_name\njane.doe,Jane\n"

        storage = MediaStorage()
        storage.save(payload)
        try:
            self.assertEqual(storage.read(), payload)
        finally:
            storage.remove()

        # After remove(), the underlying object should be gone from the backend,
        # so reading it back must fail. Both GCS (FileDoesNotExist) and the local
        # FileSystemStorage (FileNotFoundError) surface as OSError subclasses.
        with self.assertRaises(OSError):
            storage.read()

    def test_media_storage_resolves_to_configured_import_export_backend(self):
        """MediaStorage should use the dedicated import/export storage alias."""
        expected_import_export = StorageHandler()["import_export"]
        media_storage = MediaStorage()
        self.assertIs(type(media_storage._storage), type(expected_import_export))

    def test_private_gcs_backend_requires_its_own_bucket(self):
        from django.test import override_settings

        with override_settings(
            GS_BUCKET_NAME="public-media",
            GS_IMPORT_EXPORT_BUCKET_NAME=None,
        ):
            with self.assertRaises(ImproperlyConfigured):
                PrivateImportExportGCS()

        with override_settings(
            GS_BUCKET_NAME="public-media",
            GS_IMPORT_EXPORT_BUCKET_NAME="private-import-export",
        ):
            storage = PrivateImportExportGCS()
            self.assertEqual(storage.bucket_name, "private-import-export")
            self.assertEqual(storage.location, "django-import-export")
            self.assertTrue(storage.querystring_auth)
            self.assertIsNone(storage.default_acl)

    def test_import_export_lifecycle_expires_stale_objects(self):
        policy_path = (
            Path(__file__).resolve().parents[2]
            / "infrastructure/ansible/files/gcs-import-export-lifecycle.json"
        )
        policy = json.loads(policy_path.read_text())

        self.assertEqual(
            policy["rule"],
            [
                {
                    "action": {"type": "Delete"},
                    "condition": {
                        "age": 1,
                        "matchesPrefix": ["django-import-export/"],
                    },
                }
            ],
        )
