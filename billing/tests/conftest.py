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
