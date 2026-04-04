from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0036_add_reservation_limit_period"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="contact_spam_keywords",
            field=models.TextField(
                blank=True,
                default=(
                    "viagra\ncialis\ncasino\nlottery\nwinner\nclick here\nact now\n"
                    "limited time\nmake money\nwork from home\nguaranteed\nrisk free"
                ),
                help_text=(
                    "Spam keywords for the public contact form, one phrase per line. "
                    "Matching is case-insensitive substring search on subject and message."
                ),
            ),
        ),
    ]
