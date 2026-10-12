from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0031_migrate_legacy_contact_redaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="pending_email",
            field=models.EmailField(
                blank=True,
                help_text="Email address awaiting member confirmation.",
                max_length=254,
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="pending_email_requested_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the pending email confirmation was requested.",
                null=True,
            ),
        ),
    ]
