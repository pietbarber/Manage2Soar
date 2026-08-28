import json
import os
from hashlib import sha256
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from members.models import Biography, Member

LEGACY_AVATAR_PREFIX = "generated_avatars/"
ID_AVATAR_PREFIX = "generated_avatars/by-member-id/"


class Command(BaseCommand):
    help = "Migrate member media paths from username-based paths to member IDs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without copying files or updating database fields.",
        )
        parser.add_argument(
            "--delete-old",
            action="store_true",
            help="Delete legacy files after their database references are updated.",
        )
        parser.add_argument(
            "--pending-file",
            help=(
                "Absolute path for the pending manifest used to resume "
                "legacy-file cleanup (development/local only)."
            ),
        )
        parser.add_argument(
            "--pending-storage-key",
            help=(
                "Default-storage object key for the pending manifest. Use this "
                "in production so state survives pod restarts."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        delete_old = options["delete_old"]
        pending_file_option = options.get("pending_file")
        pending_storage_key = options.get("pending_storage_key")
        if not pending_file_option and not pending_storage_key:
            raise CommandError(
                "Provide --pending-storage-key (recommended) or --pending-file"
            )
        if pending_file_option and pending_storage_key:
            raise CommandError("Use either --pending-file or --pending-storage-key")

        self.pending_storage_key = pending_storage_key
        self.pending_file = Path(pending_file_option) if pending_file_option else None
        self.use_storage_manifest = self.pending_storage_key is not None

        if self._is_kubernetes_runtime() and not self.use_storage_manifest:
            raise CommandError(
                "In Kubernetes, --pending-storage-key is required so pending "
                "state is durable across pod restarts"
            )

        if self.pending_file is not None and not self.pending_file.is_absolute():
            raise CommandError("--pending-file must be an absolute path")

        self.pending = self._load_pending()
        migrated = 0
        already_present = 0
        missing = 0
        conflicts = 0
        blank = 0

        if delete_old and not dry_run:
            self._cleanup_pending()

        for member in Member.objects.only("pk", "username", "profile_photo").iterator(
            chunk_size=500
        ):
            # Pylance infers profile_photo as str after .only(); cast to FieldFile
            photo = member.profile_photo  # type: ignore[attr-defined]
            was_blank = not photo
            if photo:
                old_path = photo.name  # type: ignore[attr-defined]
                expected_current_value = old_path
            else:
                # Historical save path wrote
                # generated_avatars/profile_<username>.png without assigning
                # profile_photo, so most legacy generated avatars belong to
                # members with a blank field. Probe the legacy path and
                # migrate/attach the stored bytes instead of regenerating.
                legacy_path = self._legacy_username_avatar_path(member.username)
                if not default_storage.exists(legacy_path):
                    continue
                old_path = legacy_path
                expected_current_value = ""
            new_path = self._member_id_avatar_path(member.pk)
            if not old_path.startswith(LEGACY_AVATAR_PREFIX) or old_path == new_path:
                continue
            result = self._migrate_field(
                member,
                "profile_photo",
                old_path,
                new_path,
                expected_current_value,
                dry_run,
                delete_old,
            )
            migrated += result == "migrated"
            already_present += result == "existing"
            missing += result == "missing"
            conflicts += result == "conflict"
            blank += was_blank

        for biography in Biography.objects.select_related("member").only(
            "uploaded_image", "member_id"
        ):
            if not biography.uploaded_image:
                continue
            old_path = biography.uploaded_image.name
            path_parts = old_path.split("/")
            # Pylance cannot infer the FK accessor via select_related
            member_id = biography.member_id  # type: ignore[attr-defined]
            new_prefix = f"biography/{member_id}/"
            if old_path.startswith(new_prefix) or len(path_parts) < 2:
                continue
            new_path = f"{new_prefix}{os.path.basename(old_path)}"
            result = self._migrate_field(
                biography,
                "uploaded_image",
                old_path,
                new_path,
                old_path,
                dry_run,
                delete_old,
            )
            migrated += result == "migrated"
            already_present += result == "existing"
            missing += result == "missing"
            conflicts += result == "conflict"

        self.stdout.write(
            self.style.SUCCESS(
                f"Migrated: {migrated}; already present: {already_present}; "
                f"missing: {missing}; conflicts: {conflicts}; blank-photo: {blank}"
            )
        )

    def _migrate_field(
        self,
        instance,
        field_name,
        old_path,
        new_path,
        expected_current_value,
        dry_run,
        delete_old,
    ):
        if default_storage.exists(new_path):
            # Resume incomplete copies from a previous interrupted run. If this
            # mapping is still pending and no DB row points to the destination,
            # treat destination bytes as incomplete and retry the copy.
            if self.pending.get(old_path) == new_path and not self._is_referenced(
                new_path
            ):
                if dry_run:
                    self.stdout.write(
                        f"Would resume copy by replacing incomplete destination: {old_path} -> {new_path}"
                    )
                    return "migrated"
                try:
                    default_storage.delete(new_path)
                except Exception:
                    self.stderr.write(
                        f"Cleanup deferred: could not remove incomplete destination {new_path}"
                    )
                    return "conflict"

                if default_storage.exists(new_path):
                    self.stderr.write(
                        f"Conflict: could not remove incomplete destination {new_path}"
                    )
                    return "conflict"

            if default_storage.exists(new_path):
                if not default_storage.exists(old_path):
                    self.stdout.write(f"Missing: {old_path}")
                    return "missing"
                if not self._paths_match(old_path, new_path):
                    self.stderr.write(f"Conflict: {old_path} -> {new_path}")
                    return "conflict"
                self.stdout.write(f"Already present: {old_path} -> {new_path}")
                if not dry_run:
                    if not self._compare_and_set(
                        instance,
                        field_name,
                        expected_current_value,
                        new_path,
                    ):
                        self.stderr.write(
                            f"Skip concurrent update: {field_name} changed for {type(instance).__name__}#{instance.pk}"
                        )
                        return "conflict"
                    self._record_pending(old_path, new_path)
                    if delete_old:
                        self._cleanup_pending()
                return "existing"

        if not default_storage.exists(old_path):
            self.stdout.write(f"Missing: {old_path}")
            return "missing"

        self.stdout.write(f"Migrate: {old_path} -> {new_path}")
        if dry_run:
            return "migrated"

        self._record_pending(old_path, new_path)
        with default_storage.open(old_path, "rb") as source:
            saved_path = default_storage.save(new_path, ContentFile(source.read()))
        if saved_path != new_path:
            raise RuntimeError(
                f"Storage saved {old_path} as unexpected path {saved_path}"
            )

        if not self._compare_and_set(
            instance,
            field_name,
            expected_current_value,
            new_path,
        ):
            self.stderr.write(
                f"Skip concurrent update: {field_name} changed for {type(instance).__name__}#{instance.pk}"
            )
            return "conflict"
        if delete_old:
            self._cleanup_pending()
        return "migrated"

    def _compare_and_set(self, instance, field_name, expected_current_value, new_path):
        queryset = type(instance).objects.filter(pk=instance.pk)
        if expected_current_value in (None, ""):
            queryset = queryset.filter(
                Q(**{f"{field_name}__isnull": True}) | Q(**{field_name: ""})
            )
        else:
            queryset = queryset.filter(**{field_name: expected_current_value})
        return queryset.update(**{field_name: new_path}) == 1

    def _paths_match(self, old_path, new_path):
        return self._storage_hash(old_path) == self._storage_hash(new_path)

    def _storage_hash(self, path):
        digest = sha256()
        with default_storage.open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _is_referenced(self, path):
        return (
            Member.objects.filter(profile_photo=path).exists()
            or Biography.objects.filter(uploaded_image=path).exists()
        )

    def _legacy_username_avatar_path(self, username):
        return f"{LEGACY_AVATAR_PREFIX}profile_{username}.png"

    def _member_id_avatar_path(self, member_id):
        return f"{ID_AVATAR_PREFIX}profile_{member_id}.png"

    def _load_pending(self):
        if self.use_storage_manifest:
            key = self.pending_storage_key
            if key is None:
                raise RuntimeError("pending_storage_key is not configured")
            if not default_storage.exists(key):
                return {}
            with default_storage.open(key, "r") as handle:
                return json.load(handle)

        if self.pending_file is None or not self.pending_file.exists():
            return {}
        return json.loads(self.pending_file.read_text(encoding="utf-8"))

    def _record_pending(self, old_path, new_path):
        if self.pending.get(old_path) != new_path:
            self.pending[old_path] = new_path
            self._save_pending()

    def _save_pending(self):
        if self.use_storage_manifest:
            key = self.pending_storage_key
            if key is None:
                raise RuntimeError("pending_storage_key is not configured")
            payload = json.dumps(self.pending, indent=2, sort_keys=True)
            default_storage.delete(key)
            default_storage.save(key, ContentFile(payload.encode("utf-8")))
            return

        if self.pending_file is None:
            raise RuntimeError("pending_file is not configured")
        self.pending_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.pending_file.with_suffix(f"{self.pending_file.suffix}.tmp")
        temporary.write_text(
            json.dumps(self.pending, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(self.pending_file)

    def _cleanup_pending(self):
        remaining = {}
        for old_path, new_path in self.pending.items():
            if (
                self._is_referenced(old_path)
                or not self._is_referenced(new_path)
                or not default_storage.exists(new_path)
            ):
                remaining[old_path] = new_path
                continue
            if default_storage.exists(old_path):
                try:
                    if not self._paths_match(old_path, new_path):
                        self.stderr.write(
                            f"Cleanup deferred: destination bytes differ for {old_path}"
                        )
                        remaining[old_path] = new_path
                        continue
                except Exception:
                    self.stderr.write(
                        f"Cleanup deferred: could not verify destination bytes for {old_path}"
                    )
                    remaining[old_path] = new_path
                    continue
                try:
                    default_storage.delete(old_path)
                except Exception:
                    self.stderr.write(f"Cleanup deferred: {old_path}")
                    remaining[old_path] = new_path
        self.pending = remaining
        if self.pending:
            self._save_pending()
        elif self.use_storage_manifest:
            key = self.pending_storage_key
            if key is None:
                raise RuntimeError("pending_storage_key is not configured")
            default_storage.delete(key)
        elif self.pending_file is not None and self.pending_file.exists():
            self.pending_file.unlink()

    def _is_kubernetes_runtime(self):
        return "KUBERNETES_SERVICE_HOST" in os.environ
