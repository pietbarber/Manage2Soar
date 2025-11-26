# Generated manually for Issue #275 - Role Accounts

from django.db import migrations


def add_role_account_status(apps, schema_editor):
    """
    Add 'Role Account' membership status for system/robot accounts.

    Role accounts are used for:
    - Superuser accounts
    - Import bots
    - Field laptop accounts
    - Other automated/service accounts

    These accounts are NOT considered 'active' members and should not
    appear in member lists or be assigned duties, but they need to
    authenticate and perform specific system functions.
    """
    MembershipStatus = apps.get_model("siteconfig", "MembershipStatus")

    MembershipStatus.objects.get_or_create(
        name="Role Account",
        defaults={
            "is_active": False,  # Not an active member - won't get member privileges
            "sort_order": 250,  # After other inactive, before Deceased
            "description": (
                "System or robot account used for automated processes. "
                "Examples: superuser, import bot, field laptop. "
                "Not a human member - does not receive member privileges."
            ),
        },
    )


def remove_role_account_status(apps, schema_editor):
    """Remove the Role Account status if it exists."""
    MembershipStatus = apps.get_model("siteconfig", "MembershipStatus")
    MembershipStatus.objects.filter(name="Role Account").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0015_add_towplane_rental_setting"),
    ]

    operations = [
        migrations.RunPython(add_role_account_status, remove_role_account_status),
    ]
