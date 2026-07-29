from django.db import migrations


def install_immutability_triggers(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute(
                """
            CREATE TRIGGER billing_ledgerentry_no_update
            BEFORE UPDATE ON billing_ledgerentry
            BEGIN
                SELECT RAISE(ABORT, 'posted billing entries are immutable');
            END;
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER billing_ledgerentry_no_delete
            BEFORE DELETE ON billing_ledgerentry
            BEGIN
                SELECT RAISE(ABORT, 'posted billing entries are immutable');
            END;
                """
            )
    elif connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE FUNCTION billing_reject_entry_mutation() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'posted billing entries are immutable';
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER billing_ledgerentry_no_update
                BEFORE UPDATE OR DELETE ON billing_ledgerentry
                FOR EACH ROW EXECUTE FUNCTION billing_reject_entry_mutation();
                """
            )


def remove_immutability_triggers(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(
                "DROP TRIGGER IF EXISTS billing_ledgerentry_no_update"
            )
            cursor.execute(
                "DROP TRIGGER IF EXISTS billing_ledgerentry_no_delete"
            )
        elif connection.vendor == "postgresql":
            cursor.execute(
                """
                DROP TRIGGER IF EXISTS billing_ledgerentry_no_update ON billing_ledgerentry;
                DROP FUNCTION IF EXISTS billing_reject_entry_mutation();
                """
            )


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [
        migrations.RunPython(install_immutability_triggers, remove_immutability_triggers),
    ]
