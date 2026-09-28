from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from cms.models import Document, HomePageContent, Page


class Command(BaseCommand):
    help = (
        "Audit PDF documents and optionally rewrite CMS content to use "
        "the controlled PDF endpoint."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Rewrite valid PDF references to the controlled endpoint.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        documents = Document.objects.filter(
            file__iendswith=".pdf",
        )
        inspected = rewritten = invalid = 0

        for document in documents.select_related("page").iterator():
            inspected += 1
            old_name = document.file.name
            if not old_name:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping document id={document.id} with no stored file name"
                    )
                )
                continue
            try:
                old_url = document.file.url
                with document.file.open("rb") as stored_file:
                    if stored_file.read(5) != b"%PDF-":
                        invalid += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping non-PDF document id={document.id}: {old_name}"
                            )
                        )
                        continue

                endpoint_url = reverse(
                    "cms:document_pdf", kwargs={"document_id": document.id}
                )
                page_rewrites = list(
                    Page.objects.filter(content__contains=old_url).only("id", "content")
                )
                homepage_rewrites = list(
                    HomePageContent.objects.filter(content__contains=old_url).only(
                        "id", "content"
                    )
                )
                reference_count = sum(
                    item.content.count(old_url)
                    for item in [*page_rewrites, *homepage_rewrites]
                )
                if not reference_count:
                    continue
                if not apply_changes:
                    rewritten += reference_count
                    continue

                with transaction.atomic():
                    now = timezone.now()
                    for page in page_rewrites:
                        Page.objects.filter(pk=page.pk).update(
                            content=page.content.replace(old_url, endpoint_url),
                            updated_at=now,
                        )
                    for homepage in homepage_rewrites:
                        HomePageContent.objects.filter(pk=homepage.pk).update(
                            content=homepage.content.replace(old_url, endpoint_url),
                            updated_at=now,
                        )
                rewritten += reference_count
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed document id={document.id} ({old_name}): {exc}"
                    )
                )

        action = "rewritten" if apply_changes else "ready to rewrite"
        self.stdout.write(
            self.style.SUCCESS(
                f"Legacy PDF audit complete. Inspected: {inspected}; "
                f"references {action}: {rewritten}; invalid: {invalid}."
            )
        )
