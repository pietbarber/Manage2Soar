from django.db import migrations, models


# Why this migration exists:
# Some environments ended up with members_member.is_stats_monger while the
# project state around 0023 expects the field name stats_monger. This migration
# normalizes the physical column name to is_stats_monger when needed and keeps
# Django model state aligned via AlterField(db_column=...).
#
# The SQL is conditional so it is safe on both schemas:
# - If only stats_monger exists, it is renamed to is_stats_monger.
# - If is_stats_monger already exists, no-op.


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0023_member_is_stats_monger"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'members_member'
                              AND column_name = 'stats_monger'
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'members_member'
                              AND column_name = 'is_stats_monger'
                        ) THEN
                            ALTER TABLE members_member
                            RENAME COLUMN stats_monger TO is_stats_monger;
                        END IF;
                    END $$;
                    """,
                    reverse_sql="""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'members_member'
                              AND column_name = 'is_stats_monger'
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'members_member'
                              AND column_name = 'stats_monger'
                        ) THEN
                            ALTER TABLE members_member
                            RENAME COLUMN is_stats_monger TO stats_monger;
                        END IF;
                    END $$;
                    """,
                )
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="member",
                    name="stats_monger",
                    field=models.BooleanField(
                        db_column="is_stats_monger",
                        default=False,
                        help_text="Allows the member to export raw flight statistics CSV dumps.",
                    ),
                )
            ],
        )
    ]
