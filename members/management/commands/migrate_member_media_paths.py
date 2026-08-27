import json
import os
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from members.models import Biography, Member


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
            required=True,
            help=(
                "Absolute path on durable storage for the manifest used to "
                "resume legacy-file cleanup."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        delete_old = options["delete_old"]
        self.pending_file = Path(options["pending_file"])
        if not self.pending_file.is_absolute():
            raise CommandError("--pending-file must be an absolute durable path")
        self.pending = self._load_pending()
        migrated = 0
        already_present = 0
        missing = 0

        if delete_old and not dry_run:
            self._cleanup_pending()

        for member in Member.objects.only("pk", "profile_photo"):
            if not member.profile_photo:
                continue
            # Pylance infers profile_photo as str after .only(); cast to FieldFile
            old_path = member.profile_photo.name  # type: ignore[attr-defined]
            new_path = f"generated_avatars/profile_{member.pk}.png"
            if not old_path.startswith("generated_avatars/") or old_path == new_path:
                continue
            result = self._migrate_field(
                member,
                "profile_photo",
                old_path,
                new_path,
                dry_run,
                delete_old,
            )
            migrated += result == "migrated"
            already_present += result == "existing"
            missing += result == "missing"

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
                dry_run,
                delete_old,
            )
            migrated += result == "migrated"
            already_present += result == "existing"
            missing += result == "missing"

        self.stdout.write(
            self.style.SUCCESS(
                f"Migrated: {migrated}; already present: {already_present}; missing: {missing}"
            )
        )

    def _migrate_field(
        self, instance, field_name, old_path, new_path, dry_run, delete_old
    ):
        if default_storage.exists(new_path):
            self.stdout.write(f"Already present: {old_path} -> {new_path}")
            if not dry_run:
                self._record_pending(old_path, new_path)
                type(instance).objects.filter(pk=instance.pk).update(
                    **{field_name: new_path}
                )
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

        type(instance).objects.filter(pk=instance.pk).update(**{field_name: new_path})
        if delete_old:
            self._cleanup_pending()
        return "migrated"

    def _load_pending(self):
        if not self.pending_file.exists():
            return {}
        return json.loads(self.pending_file.read_text(encoding="utf-8"))

    def _record_pending(self, old_path, new_path):
        if self.pending.get(old_path) != new_path:
            self.pending[old_path] = new_path
            self._save_pending()

    def _save_pending(self):
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
                Member.objects.filter(profile_photo=old_path).exists()
                or Biography.objects.filter(uploaded_image=old_path).exists()
                or not default_storage.exists(new_path)
            ):
                remaining[old_path] = new_path
                continue
            if default_storage.exists(old_path):
                try:
                    default_storage.delete(old_path)
                except Exception:
                    self.stderr.write(f"Cleanup deferred: {old_path}")
                    remaining[old_path] = new_path
        self.pending = remaining
        if self.pending:
            self._save_pending()
        elif self.pending_file.exists():
            self.pending_file.unlink()
