"""Browser coverage for privileged profile contact reveals."""

from siteconfig.models import SiteConfiguration

from .conftest import DjangoPlaywrightTestCase


class TestMemberContactPrivacyRevealE2E(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )
        self.viewer = self.create_test_member(username="privacy_staff", is_staff=True)
        self.subject = self.create_test_member(
            username="privacy_subject",
            email="private@example.com",
            phone="6615550100",
            address="1 Private Way",
            city="Lancaster",
            state_code="CA",
            zip_code="93534",
            contact_visibility={"email": "hide", "phone": "hide", "address": "hide"},
        )

    def test_privileged_contact_reveals_are_hidden_until_activated(self):
        self.login(username=self.viewer.username)
        self.page.goto(f"{self.live_server_url}/members/{self.subject.pk}/view/")

        email_value = self.page.locator("#contact-email-value")
        phone_value = self.page.locator("#contact-phone-value")
        address_value = self.page.locator("#contact-address-value")
        assert not email_value.is_visible()
        assert not phone_value.is_visible()
        assert not address_value.is_visible()

        self.page.locator("#contact-email-reveal").click()
        assert email_value.is_visible()
        assert (
            self.page.locator("#contact-email-reveal").get_attribute("aria-expanded")
            == "true"
        )
        assert not self.page.locator("#contact-email-reveal").is_visible()

        phone_button = self.page.locator("#contact-phone-reveal")
        phone_button.focus()
        self.page.keyboard.press("Enter")
        assert phone_value.is_visible()

        address_button = self.page.locator("#contact-address-reveal")
        address_button.focus()
        self.page.keyboard.press("Space")
        assert address_value.is_visible()
