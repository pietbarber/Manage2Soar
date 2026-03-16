from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0018_page_navbar_rank_page_navbar_title_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="file_size_bytes",
            field=models.BigIntegerField(
                blank=True,
                help_text="Cached document size in bytes to avoid storage metadata lookups during page render.",
                null=True,
            ),
        ),
    ]
