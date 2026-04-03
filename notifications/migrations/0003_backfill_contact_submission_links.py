import re

from django.db import migrations


CONTACT_URL_RE = re.compile(r"/admin/cms/visitorcontact/(?P<pk>\d+)/change/?$")


def backfill_contact_submission_links(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    VisitorContact = apps.get_model("cms", "VisitorContact")

    candidates = Notification.objects.filter(contact_submission__isnull=True).exclude(
        url__isnull=True
    ).exclude(url="")

    for notification in candidates.iterator():
        match = CONTACT_URL_RE.search(notification.url)
        if not match:
            continue

        contact_pk = int(match.group("pk"))
        if VisitorContact.objects.filter(pk=contact_pk).exists():
            notification.contact_submission_id = contact_pk
            notification.save(update_fields=["contact_submission"])


def noop_reverse(apps, schema_editor):
    # No reverse data migration needed; preserving backfilled links is safe.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_notification_contact_submission"),
    ]

    operations = [
        migrations.RunPython(backfill_contact_submission_links, noop_reverse),
    ]
