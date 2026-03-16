from django.core.management.base import BaseCommand

from cms.models import Document


class Command(BaseCommand):
    help = "Backfill cms.Document.file_size_bytes for existing documents in batches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Number of documents to process per batch (default: 200).",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Process only documents where file_size_bytes is null.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate updates without writing to the database.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        only_missing = options["only_missing"]
        dry_run = options["dry_run"]

        base_queryset = Document.objects.all()
        if only_missing:
            base_queryset = base_queryset.filter(file_size_bytes__isnull=True)

        total = base_queryset.count()
        processed = 0
        updated = 0
        last_id = 0

        self.stdout.write(
            self.style.NOTICE(
                f"Starting document size backfill for {total} documents "
                f"(batch_size={batch_size}, only_missing={only_missing}, dry_run={dry_run})"
            )
        )

        while True:
            batch = list(
                base_queryset.filter(id__gt=last_id).order_by("id")[:batch_size]
            )
            if not batch:
                break

            for doc in batch:
                last_id = doc.id
                processed += 1
                if not doc.file:
                    continue

                try:
                    size = doc.file.size
                except Exception as exc:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping document id={doc.id} ({doc.file.name}): {exc}"
                        )
                    )
                    continue

                if doc.file_size_bytes == size:
                    continue

                updated += 1
                if not dry_run:
                    Document.objects.filter(pk=doc.pk).update(file_size_bytes=size)

            self.stdout.write(
                f"Processed {processed}/{total} documents, pending updates: {updated}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete. Documents inspected: {processed}. "
                f"Documents {'to update' if dry_run else 'updated'}: {updated}."
            )
        )
