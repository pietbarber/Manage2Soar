import os

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

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

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        delete_old = options["delete_old"]
        migrated = 0
        already_present = 0
        missing = 0

        for member in Member.objects.only("pk", "profile_photo"):
            if not member.profile_photo:
                continue
            old_path = member.profile_photo.name
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
            "uploaded_image", "member__pk"
        ):
            if not biography.uploaded_image:
                continue
            old_path = biography.uploaded_image.name
            path_parts = old_path.split("/")
            new_prefix = f"biography/{biography.member_id}/"
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
                type(instance).objects.filter(pk=instance.pk).update(
                    **{field_name: new_path}
                )
                if delete_old:
                    default_storage.delete(old_path)
            return "existing"

        if not default_storage.exists(old_path):
            self.stdout.write(f"Missing: {old_path}")
            return "missing"

        self.stdout.write(f"Migrate: {old_path} -> {new_path}")
        if dry_run:
            return "migrated"

        with default_storage.open(old_path, "rb") as source:
            saved_path = default_storage.save(new_path, ContentFile(source.read()))
        if saved_path != new_path:
            raise RuntimeError(
                f"Storage saved {old_path} as unexpected path {saved_path}"
            )

        type(instance).objects.filter(pk=instance.pk).update(**{field_name: new_path})
        if delete_old:
            default_storage.delete(old_path)
        return "migrated"
