"""Backfill TowplaneRentalCharge from legacy single-renter closeout fields.

For every ``TowplaneCloseout`` row that has a non-null ``rental_charged_to``
and a positive ``rental_hours_chargeable``, create one
``TowplaneRentalCharge`` row carrying that member's hours. Rows without
either field are skipped (nothing to migrate).

Reversible: the backfill only *adds* rows; the reverse deletes every
``TowplaneRentalCharge`` row that was created in the forward pass. To keep
the reverse safe, we delete all rows that match the legacy (closeout,
member, hours) combination that the forward pass would have written.
"""

from django.db import migrations


def forward_backfill(apps, schema_editor):
    TowplaneCloseout = apps.get_model("logsheet", "TowplaneCloseout")
    TowplaneRentalCharge = apps.get_model("logsheet", "TowplaneRentalCharge")

    for closeout in TowplaneCloseout.objects.filter(
        rental_charged_to__isnull=False,
        rental_hours_chargeable__isnull=False,
        rental_hours_chargeable__gt=0,
    ):
        TowplaneRentalCharge.objects.get_or_create(
            closeout=closeout,
            member=closeout.rental_charged_to,
            defaults={"hours": closeout.rental_hours_chargeable},
        )


def reverse_backfill(apps, schema_editor):
    TowplaneCloseout = apps.get_model("logsheet", "TowplaneCloseout")
    TowplaneRentalCharge = apps.get_model("logsheet", "TowplaneRentalCharge")

    # Delete every charge row whose (closeout, member, hours) triple matches
    # the legacy closeout data. This is the inverse of the forward pass and
    # will not touch any rows created by the new UI.
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
