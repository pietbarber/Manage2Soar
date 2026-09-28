from django.core.management.base import BaseCommand

from cms.models import Document, upload_document_to


class Command(BaseCommand):
    help = (
        "Audit public legacy PDF documents and optionally move valid files to "
        "the dedicated cms-pdfs/ path."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Move valid PDFs and update embedded document URLs.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        documents = Document.objects.filter(
            page__is_public=True,
            file__iendswith=".pdf",
        ).exclude(file__startswith="cms-pdfs/")
        inspected = migrated = invalid = 0

        for document in documents.select_related("page").iterator():
            inspected += 1
            old_name = document.file.name
            old_url = document.file.url
            try:
                with document.file.open("rb") as stored_file:
                    if stored_file.read(5) != b"%PDF-":
                        invalid += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping non-PDF document id={document.id}: {old_name}"
                            )
                        )
                        continue

                    new_name = upload_document_to(document, old_name.rsplit("/", 1)[-1])
                    if not apply_changes:
                        migrated += 1
                        continue

                    stored_file.seek(0)
                    saved_name = document.file.storage.save(new_name, stored_file)
                    document.file.name = saved_name
                    document.save()
                    document.file.storage.delete(old_name)

                new_url = document.file.url
                if old_url in document.page.content:
                    document.page.content = document.page.content.replace(
                        old_url, new_url
                    )
                    document.page.save(update_fields=["content", "updated_at"])
                migrated += 1
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed document id={document.id} ({old_name}): {exc}"
                    )
                )

        action = "migrated" if apply_changes else "ready to migrate"
        self.stdout.write(
            self.style.SUCCESS(
                f"Legacy PDF audit complete. Inspected: {inspected}; "
                f"{action}: {migrated}; invalid: {invalid}."
            )
        )
