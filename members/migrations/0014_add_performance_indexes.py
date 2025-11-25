# Generated manually for Issue #285 - Performance optimization for logsheet finances
from django.db import migrations


class Migration(migrations.Migration):
    
    dependencies = [
        ('members', '0013_add_foreign_pilot_choice'),
    ]

    operations = [
        # Add index on membership_status for faster filtering
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS members_member_membership_status_idx ON members_member (membership_status);",
            reverse_sql="DROP INDEX IF EXISTS members_member_membership_status_idx;"
        ),
        # Add composite index for name sorting (used in finances view)
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS members_member_name_sort_idx ON members_member (last_name, first_name);",
            reverse_sql="DROP INDEX IF EXISTS members_member_name_sort_idx;"
        ),
    ]