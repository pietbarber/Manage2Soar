from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0006_alter_badge_image_alter_biography_uploaded_image_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="redact_contact",
            field=models.BooleanField(
                default=False,
                help_text="If set, personal contact details (address, phones, email, QR) are hidden from non-privileged viewers.",
            ),
        ),
    ]
