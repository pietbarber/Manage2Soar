import pytest

from siteconfig.models import SiteConfiguration


@pytest.fixture(autouse=True)
def enable_billing_app(db):
    config = SiteConfiguration.objects.first() or SiteConfiguration.objects.create(
        club_name="Billing Test Club",
        domain_name="billing-test.example.com",
        club_abbreviation="BTC",
    )
    config.billing_app_enabled = True
    config.save(update_fields=["billing_app_enabled"])
    return config


@pytest.fixture
def seeded_chart(db):
    """Ensure the migration-seeded chart of accounts exists.

    Transactional tests flush the database, which removes data that
    migrations seeded, so tests that rely on the chart re-seed it here.
    """
    from importlib import import_module

    from billing.models import Account

    seed = import_module("billing.migrations.0012_journal_immutability_and_chart_seed")
    for code, name, account_type, is_cash, role in seed.SEED_ACCOUNTS:
        Account.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "type": account_type,
                "is_cash": is_cash,
                "system_role": role,
            },
        )


@pytest.fixture
def enable_club_accounting(enable_billing_app, seeded_chart):
    enable_billing_app.club_accounting_enabled = True
    enable_billing_app.club_accounting_start_date = None
    enable_billing_app.save(
        update_fields=["club_accounting_enabled", "club_accounting_start_date"]
    )
    return enable_billing_app
