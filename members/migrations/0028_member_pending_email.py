from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0027_member_contact_visibility_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="pending_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="member",
            name="pending_email_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
