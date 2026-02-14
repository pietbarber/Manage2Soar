"""
End-to-end tests for the Member Charge creation workflow.

Issue #615: Verify the full browser-based workflow for adding
miscellaneous charges during logsheet management.
"""

from datetime import date
from decimal import Decimal

from logsheet.models import Airfield, Logsheet, MemberCharge
from siteconfig.models import ChargeableItem, SiteConfiguration

from .conftest import DjangoPlaywrightTestCase


class TestAddMemberChargeE2E(DjangoPlaywrightTestCase):
    """Test the Add Charge workflow end-to-end with Playwright."""

    def setUp(self):
        super().setUp()

        # Create site config
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        # Create duty officer
        self.duty_officer = self.create_test_member(
            username="do_charge",
            first_name="Duty",
            last_name="Officer",
        )
        self.duty_officer.duty_officer = True
        self.duty_officer.save()

        # Create a member to charge
        self.pilot = self.create_test_member(
            username="pilot_charge",
            first_name="Test",
            last_name="Pilot",
        )

        # Create airfield and logsheet
        self.airfield = Airfield.objects.create(
            name="Test Airfield",
            identifier="E2EC",
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.duty_officer,
        )

        # Create chargeable items
        self.tshirt = ChargeableItem.objects.create(
            name="T-Shirt Large",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=True,
            sort_order=10,
        )
        self.retrieve = ChargeableItem.objects.create(
            name="Aerotow Retrieve",
            price=Decimal("120.00"),
            unit=ChargeableItem.UnitType.HOUR,
            allows_decimal_quantity=True,
            is_active=True,
            sort_order=20,
        )
        ChargeableItem.objects.create(
            name="Retired Item",
            price=Decimal("99.00"),
            is_active=False,
            sort_order=30,
        )

    def test_add_charge_button_visible_on_finances_page(self):
        """Test that the 'Add Charge' button is visible on the finances page."""
        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/finances/"
        )
        # Should see the Add Charge button
        add_charge_btn = self.page.locator("a:has-text('Add Charge')")
        assert add_charge_btn.is_visible()

    def test_add_charge_form_renders(self):
        """Test that the Add Charge form renders correctly with all fields."""
        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/add-charge/"
        )

        # Check page title
        h1_text = self.page.text_content("h1") or ""
        assert "Add Miscellaneous Charge" in h1_text

        # Check form fields exist
        assert self.page.locator("#id_member").is_visible()
        assert self.page.locator("#id_chargeable_item").is_visible()
        assert self.page.locator("#id_quantity").is_visible()
        assert self.page.locator("#id_notes").is_visible()

        # Check submit and cancel buttons
        assert self.page.locator("button:has-text('Add Charge')").is_visible()
        assert self.page.locator("a:has-text('Cancel')").is_visible()

    def test_add_charge_form_only_shows_active_items(self):
        """Test that inactive chargeable items are excluded from the dropdown."""
        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/add-charge/"
        )

        # Get all option texts in the chargeable item dropdown
        options = self.page.locator("#id_chargeable_item option").all_text_contents()
        options_text = " ".join(options)

        assert "T-Shirt Large" in options_text
        assert "Aerotow Retrieve" in options_text
        assert "Retired Item" not in options_text

    def test_submit_charge_creates_record(self):
        """Test submitting the form creates a MemberCharge and redirects."""
        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/add-charge/"
        )

        # Fill out the form
        self.page.select_option("#id_member", str(self.pilot.pk))
        self.page.select_option("#id_chargeable_item", str(self.tshirt.pk))
        self.page.fill("#id_quantity", "2")
        self.page.fill("#id_notes", "Two large t-shirts")

        # Submit
        self.page.click("button:has-text('Add Charge')")

        # Should redirect to finances page
        self.page.wait_for_url(f"**/finances/")

        # Verify the charge was created in the database
        charge = MemberCharge.objects.get(logsheet=self.logsheet, member=self.pilot)
        assert charge.chargeable_item == self.tshirt
        assert charge.quantity == Decimal("2")
        assert charge.total_price == Decimal("50.00")
        assert charge.notes == "Two large t-shirts"

    def test_charge_appears_in_finances_after_creation(self):
        """Test that a newly created charge appears in the finances table."""
        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/add-charge/"
        )

        # Add a charge
        self.page.select_option("#id_member", str(self.pilot.pk))
        self.page.select_option("#id_chargeable_item", str(self.tshirt.pk))
        self.page.fill("#id_quantity", "1")
        self.page.click("button:has-text('Add Charge')")

        # After redirect, verify the charge appears
        self.page.wait_for_url(f"**/finances/")
        content = self.page.text_content("body") or ""
        assert "T-Shirt Large" in content
        assert "Miscellaneous Charges" in content

    def test_cancel_button_returns_to_finances(self):
        """Test that the Cancel button navigates back to finances."""
        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/add-charge/"
        )

        self.page.click("a:has-text('Cancel')")
        self.page.wait_for_url(f"**/finances/")

    def test_add_charge_hidden_on_finalized_logsheet(self):
        """Test that the Add Charge button is hidden when logsheet is finalized."""
        self.logsheet.finalized = True
        self.logsheet.save()

        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/finances/"
        )

        # Should NOT see the Add Charge button
        add_charge_btn = self.page.locator("a:has-text('Add Charge')")
        assert add_charge_btn.count() == 0

    def test_delete_charge_button_works(self):
        """Test that the delete button removes a charge."""
        # Create a charge first
        charge = MemberCharge.objects.create(
            member=self.pilot,
            chargeable_item=self.tshirt,
            quantity=Decimal("1"),
            logsheet=self.logsheet,
            entered_by=self.duty_officer,
        )

        self.login(username="do_charge")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/finances/"
        )

        # Accept the browser confirmation dialog
        self.page.on("dialog", lambda dialog: dialog.accept())

        # Click the delete button
        delete_button = self.page.locator(
            f'form[action*="delete-charge/{charge.pk}"] button'
        )
        delete_button.click()

        # Should redirect back to finances
        self.page.wait_for_url(f"**/finances/")

        # Verify charge was deleted
        assert MemberCharge.objects.count() == 0
