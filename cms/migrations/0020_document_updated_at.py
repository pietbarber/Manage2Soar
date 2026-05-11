from django.db import migrations, models
from django.db.models import F


def backfill_document_updated_at(apps, schema_editor):
    Document = apps.get_model("cms", "Document")
    Document.objects.filter(updated_at__isnull=True).update(updated_at=F("uploaded_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0019_document_file_size_bytes"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_document_updated_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="document",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
