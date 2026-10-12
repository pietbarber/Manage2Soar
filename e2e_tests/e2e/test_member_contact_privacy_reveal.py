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

        redaction_modal = self.page.locator("#redaction-alert-modal")
        redaction_modal.wait_for(state="visible")
        assert (
            "Click a Redacted field to reveal it temporarily."
            in redaction_modal.inner_text()
        )
        redaction_modal.get_by_role("button", name="Dismiss").click()
        redaction_modal.wait_for(state="hidden")

        reveals = self.page.locator(".staff-reveal")
        assert reveals.count() == 3
        assert not reveals.nth(0).locator(".staff-revealed").is_visible()
        assert not reveals.nth(1).locator(".staff-revealed").is_visible()
        assert not reveals.nth(2).locator(".staff-revealed").is_visible()

        reveals.nth(0).click()
        assert "is-revealed" in (reveals.nth(0).get_attribute("class") or "")
        assert reveals.nth(0).locator(".staff-revealed").is_visible()

        phone_reveal = reveals.nth(1)
        phone_reveal.focus()
        self.page.keyboard.press("Enter")
        assert "is-revealed" in (phone_reveal.get_attribute("class") or "")
        assert phone_reveal.locator(".staff-revealed").is_visible()

        address_reveal = reveals.nth(2)
        address_reveal.focus()
        self.page.keyboard.press("Space")
        assert "is-revealed" in (address_reveal.get_attribute("class") or "")
        assert address_reveal.locator(".staff-revealed").is_visible()
