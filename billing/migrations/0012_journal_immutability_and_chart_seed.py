from django.db import migrations

JOURNAL_TABLES = ("billing_journalentry", "billing_journalline")

# A generic starting chart of accounts. Clubs rename, renumber, and add
# accounts (including more bank accounts, as 111, 112, ...) from the Club
# Finances pages.
SEED_ACCOUNTS = (
    ("100", "Undeposited Funds", "asset", True, "undeposited_funds"),
    ("110", "Checking", "asset", True, None),
    ("120", "Member Receivables", "asset", False, "member_receivables"),
    ("200", "Accounts Payable", "liability", False, None),
    ("300", "General Fund", "equity", False, "general_fund"),
    ("390", "Opening Balance Equity", "equity", False, "opening_balance_equity"),
    ("400", "Membership Dues", "income", False, None),
    ("410", "Tow Fees", "income", False, "tow_revenue"),
    ("420", "Glider Rental", "income", False, "rental_revenue"),
    ("430", "Instruction", "income", False, "instruction_revenue"),
    ("440", "Guest Flights", "income", False, "guest_flight_revenue"),
    ("450", "Miscellaneous Charges", "income", False, "default_charge_revenue"),
    ("460", "Donations", "income", False, None),
    ("490", "Other Income", "income", False, None),
    ("500", "Field Rent", "expense", False, None),
    ("510", "Aircraft Maintenance", "expense", False, None),
    ("520", "Fuel and Oil", "expense", False, None),
    ("530", "Insurance", "expense", False, None),
    ("540", "Utilities", "expense", False, None),
    ("550", "Bank Fees", "expense", False, None),
    ("580", "Member Credits and Discounts", "expense", False, "member_credits"),
    ("590", "Bad Debt and Write-offs", "expense", False, "bad_debt"),
)


def install_journal_triggers(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            for table in JOURNAL_TABLES:
                for action in ("UPDATE", "DELETE"):
                    cursor.execute(
                        f"""
                        CREATE TRIGGER {table}_no_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, 'posted journal records are immutable');
                        END;
                        """
                    )
        elif connection.vendor == "postgresql":
            cursor.execute(
                """
                CREATE FUNCTION billing_reject_journal_mutation() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'posted journal records are immutable';
                END;
                $$ LANGUAGE plpgsql;
                """
            )
            for table in JOURNAL_TABLES:
                cursor.execute(
                    f"""
                    CREATE TRIGGER {table}_no_mutation
                    BEFORE UPDATE OR DELETE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION billing_reject_journal_mutation();
                    """
                )


def remove_journal_triggers(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            for table in JOURNAL_TABLES:
                for action in ("update", "delete"):
                    cursor.execute(f"DROP TRIGGER IF EXISTS {table}_no_{action}")
        elif connection.vendor == "postgresql":
            for table in JOURNAL_TABLES:
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS {table}_no_mutation ON {table}"
                )
            cursor.execute("DROP FUNCTION IF EXISTS billing_reject_journal_mutation()")


def seed_chart_of_accounts(apps, schema_editor):
    Account = apps.get_model("billing", "Account")
    if Account.objects.exists():
        return
    for code, name, account_type, is_cash, role in SEED_ACCOUNTS:
        Account.objects.create(
            code=code,
            name=name,
            type=account_type,
            is_cash=is_cash,
            system_role=role,
        )


def unseed_chart_of_accounts(apps, schema_editor):
    Account = apps.get_model("billing", "Account")
    Account.objects.filter(
        code__in=[row[0] for row in SEED_ACCOUNTS], lines__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0011_club_accounting")]

    operations = [
        migrations.RunPython(install_journal_triggers, remove_journal_triggers),
        migrations.RunPython(seed_chart_of_accounts, unseed_chart_of_accounts),
    ]
