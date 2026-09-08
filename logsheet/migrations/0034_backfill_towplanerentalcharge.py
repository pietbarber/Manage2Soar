"""Backfill TowplaneRentalCharge from legacy single-renter closeout fields.

For every ``TowplaneCloseout`` row that has a non-null ``rental_charged_to``
and a positive ``rental_hours_chargeable``, create one
``TowplaneRentalCharge`` row carrying that member's hours. Rows without
either field are skipped (nothing to migrate).

The reverse pass deletes every ``TowplaneRentalCharge`` row that matches the
legacy (closeout, member, hours) combination. If a later UI-created row has
the same values, it is also deleted during rollback; the migration does not
record row provenance.
"""

from django.db import migrations


def forward_backfill(apps, schema_editor):
    TowplaneCloseout = apps.get_model("logsheet", "TowplaneCloseout")
    TowplaneRentalCharge = apps.get_model("logsheet", "TowplaneRentalCharge")

    for closeout in TowplaneCloseout.objects.filter(
        rental_charged_to__isnull=False,
        rental_hours_chargeable__isnull=False,
        rental_hours_chargeable__gt=0,
    ).iterator():
        TowplaneRentalCharge.objects.get_or_create(
            closeout=closeout,
            member=closeout.rental_charged_to,
            defaults={"hours": closeout.rental_hours_chargeable},
        )


def reverse_backfill(apps, schema_editor):
    TowplaneCloseout = apps.get_model("logsheet", "TowplaneCloseout")
    TowplaneRentalCharge = apps.get_model("logsheet", "TowplaneRentalCharge")

    # Delete every charge row whose (closeout, member, hours) triple matches
    # the legacy closeout data. Matching rows created later by the UI are also
    # deleted because this migration does not record row provenance.
    for closeout in TowplaneCloseout.objects.filter(
        rental_charged_to__isnull=False,
        rental_hours_chargeable__isnull=False,
        rental_hours_chargeable__gt=0,
    ).iterator():
        TowplaneRentalCharge.objects.filter(
            closeout=closeout,
            member=closeout.rental_charged_to,
            hours=closeout.rental_hours_chargeable,
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("logsheet", "0033_towplanerentalcharge"),
    ]

    operations = [
        migrations.RunPython(
            code=forward_backfill,
            reverse_code=reverse_backfill,
        ),
    ]
