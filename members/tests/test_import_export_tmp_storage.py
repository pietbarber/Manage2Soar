from django.contrib import admin
from django.test import TestCase
from import_export.tmp_storages import MediaStorage, TempFolderStorage

from members.admin import MemberAdmin
from members.models import Member


class MemberImportTmpStorageTests(TestCase):
    """Tests for issue #1071: cross-pod shared tmp storage for import/export.

    On GKE (2 replicas), the default TempFolderStorage writes to pod-local /tmp,
    so the import confirmation request landing on a different pod raised
    ``FileNotFoundError``. We switch to the shared MediaStorage backend, which
    resolves to STORAGES["default"] (GCS in production, FileSystemStorage in
    dev/tests).
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

    def test_media_storage_resolves_to_configured_default_backend(self):
        """MediaStorage should target the configured STORAGES["default"] backend."""
        from django.core.files.storage import StorageHandler

        expected_default = StorageHandler()["default"]
        media_storage = MediaStorage()
        # Compare backend class (StorageHandler returns a fresh instance per call).
        self.assertIs(type(media_storage._storage), type(expected_default))
