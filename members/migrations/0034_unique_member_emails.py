from collections import defaultdict

from django.db import migrations, models
from django.db.models.functions import Lower


def reject_existing_duplicate_emails(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    duplicates = defaultdict(list)
    for member_id, email in Member.objects.exclude(email="").values_list("pk", "email"):
        duplicates[email.casefold()].append((member_id, email))

    conflicts = {
        email: members for email, members in duplicates.items() if len(members) > 1
    }
    if conflicts:
        details = "; ".join(
            f"{email}: {[member_id for member_id, _ in members]}"
            for email, members in sorted(conflicts.items())
        )
        raise RuntimeError(
            "Cannot enforce unique member emails; resolve these duplicate addresses "
            f"first: {details}"
        )


class Migration(migrations.Migration):
    dependencies = [("members", "0033_member_manager_emergency_contact_permissions")]

    operations = [
        migrations.RunPython(reject_existing_duplicate_emails),
        migrations.AddConstraint(
            model_name="member",
            constraint=models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="member_unique_nonblank_email_ci",
            ),
        ),
    ]
