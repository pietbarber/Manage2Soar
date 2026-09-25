"""Promote 2-letter state codes stored in state_freeform into state_code.

Members residing in the District of Columbia (or APO/FPO/DPO regions) had
"DC" (or similar) stored in ``state_freeform`` because the value was not a
valid choice for ``state_code`` (issue #1062).  Now that the choices include
DC and the military regions, normalize such rows so the code lives in the
``state_code`` column and display code remains consistent.
"""

from django.db import migrations

# Valid 2-letter state codes, including DC and the USPS military regions.
# Kept inline (like 0027) so the migration never depends on app code.
VALID_STATE_CODES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
    "AA",
    "AE",
    "AP",
    "PO",
    "PP",
}


def promote_state_codes(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    qs = Member.objects.filter(
        state_code__isnull=True,
        state_freeform__isnull=False,
    ).exclude(state_freeform="")
    for member in qs.iterator():
        candidate = member.state_freeform.strip().upper()
        if len(candidate) == 2 and candidate in VALID_STATE_CODES:
            Member.objects.filter(pk=member.pk).update(
                state_code=candidate, state_freeform=""
            )


def revert_state_codes(apps, schema_editor):
    # Data migration rollback: keep state_code as-is.  Members can manually
    # move the value back if needed; nothing destructive to undo.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0027_alter_member_state_code"),
    ]

    operations = [
        migrations.RunPython(promote_state_codes, revert_state_codes),
    ]
