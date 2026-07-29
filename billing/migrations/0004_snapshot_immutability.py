from django.db import migrations


def install_snapshot_triggers(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TRIGGER billing_snapshot_no_update
                BEFORE UPDATE ON billing_flightchargesnapshot
                BEGIN
                    SELECT RAISE(ABORT, 'flight charge snapshots are immutable');
                END;
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER billing_snapshot_no_delete
                BEFORE DELETE ON billing_flightchargesnapshot
                BEGIN
                    SELECT RAISE(ABORT, 'flight charge snapshots are immutable');
                END;
                """
            )
    elif connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE FUNCTION billing_reject_snapshot_mutation() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'flight charge snapshots are immutable';
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER billing_snapshot_no_update
                BEFORE UPDATE OR DELETE ON billing_flightchargesnapshot
                FOR EACH ROW EXECUTE FUNCTION billing_reject_snapshot_mutation();
                """
            )


def remove_snapshot_triggers(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute("DROP TRIGGER IF EXISTS billing_snapshot_no_update")
            cursor.execute("DROP TRIGGER IF EXISTS billing_snapshot_no_delete")
        elif connection.vendor == "postgresql":
            cursor.execute(
                """
                DROP TRIGGER IF EXISTS billing_snapshot_no_update
                    ON billing_flightchargesnapshot;
                DROP FUNCTION IF EXISTS billing_reject_snapshot_mutation();
                """
            )


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_ledgerentry_flight_flightchargesnapshot")]
    operations = [
        migrations.RunPython(install_snapshot_triggers, remove_snapshot_triggers),
    ]
