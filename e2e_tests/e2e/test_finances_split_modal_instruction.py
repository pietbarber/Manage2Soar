from datetime import date, time
from decimal import Decimal

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Flight, Glider, Logsheet
from siteconfig.models import SiteConfiguration


class TestFinancesSplitModalInstructionE2E(DjangoPlaywrightTestCase):
    """Verify finalized split modal includes instruction-fee allocations."""

    def setUp(self):
        super().setUp()

        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        self.duty_officer = self.create_test_member(
            username="do_split_modal",
            first_name="Duty",
            last_name="Officer",
            duty_officer=True,
        )
        self.partner = self.create_test_member(
            username="split_partner",
            first_name="Split",
            last_name="Partner",
        )

        self.airfield = Airfield.objects.create(identifier="E2ES", name="E2E Split")
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N900SM",
            competition_number="SM",
            seats=2,
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.duty_officer,
            duty_officer=self.duty_officer,
        )

        self.flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.duty_officer,
            split_with=self.partner,
            split_type="tow",
            glider=self.glider,
            flight_type="dual",
            launch_time=time(10, 0),
            landing_time=time(10, 30),
            release_altitude=3000,
            tow_cost_actual=Decimal("30.00"),
            rental_cost_actual=Decimal("12.00"),
            instruction_fee_actual=Decimal("8.00"),
        )

        self.logsheet.finalized = True
        self.logsheet.save(update_fields=["finalized"])

    def test_view_split_modal_shows_instruction_breakdown(self):
        self.login(username="do_split_modal")
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/finances/"
        )

        self.page.click("button.view-split-btn")
        self.page.wait_for_selector("#viewSplitModal.show")

        breakdown_text = self.page.text_content("#view-split-breakdown") or ""
        assert "Instruction Fee" in breakdown_text
        assert "$8.00" in breakdown_text

        pilot_total = self.page.text_content("#view-pilot-total") or ""
        partner_total = self.page.text_content("#view-partner-total") or ""
        total_amount = self.page.text_content("#view-total-amount") or ""

        # Tow-only split: pilot pays rental + instruction, partner pays tow.
        assert "$20.00" in pilot_total
        assert "$30.00" in partner_total
        assert "$50.00" in total_amount
