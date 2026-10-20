from django.db import migrations, models


def set_flight_eligibility_defaults(apps, schema_editor):
    MembershipStatus = apps.get_model("siteconfig", "MembershipStatus")
    MembershipStatus.objects.filter(is_active=True).exclude(
        name__in=("Family Member", "Service Member")
    ).update(can_be_pilot=True)
    MembershipStatus.objects.exclude(name="Deceased").update(can_be_passenger=True)
    MembershipStatus.objects.filter(name="Deceased").update(
        can_be_pilot=False, can_be_passenger=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0055_siteconfiguration_member_name_ordering"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershipstatus",
            name="can_be_passenger",
            field=models.BooleanField(
                default=True,
                help_text="Members with this status may be selected as a passenger on flights.",
            ),
        ),
        migrations.AddField(
            model_name="membershipstatus",
            name="can_be_pilot",
            field=models.BooleanField(
                default=False,
                help_text="Members with this status may be selected as a pilot on flights.",
            ),
        ),
        migrations.RunPython(
            set_flight_eligibility_defaults, migrations.RunPython.noop
        ),
    ]
