from datetime import date

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Glider, Logsheet
from siteconfig.models import SiteConfiguration


class TestCommercialRideFormToggle(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.editor = self.create_test_member(
            username="commercial_editor",
            is_superuser=True,
        )
        self.passenger = self.create_test_member(username="commercial_passenger")
        self.login(username="commercial_editor")

        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="example.org",
            club_abbreviation="TC",
            commercial_rides_enabled=True,
        )

        self.airfield = Airfield.objects.create(
            identifier="KFRR",
            name="Front Royal",
            is_active=True,
        )
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N808CR",
            competition_number="C8",
            seats=2,
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date(2026, 4, 9),
            airfield=self.airfield,
            created_by=self.editor,
            duty_officer=self.editor,
        )

    def test_toggle_disables_passenger_fields_and_requires_ticket(self):
        self.page.goto(
            f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/add-flight/"
        )
        self.page.wait_for_selector("#id_commercial_ride")

        self.page.fill("#id_passenger_name", "Guest Rider")
        self.page.select_option("#id_passenger", str(self.passenger.pk))

        self.page.check("#id_commercial_ride")

        assert self.page.is_disabled("#id_passenger")
        assert self.page.is_disabled("#id_passenger_name")
        assert self.page.input_value("#id_passenger") == ""
        assert self.page.input_value("#id_passenger_name") == ""

        ticket_visible = self.page.evaluate(
            "getComputedStyle(document.getElementById('ticket-number-group')).display !== 'none'"
        )
        ticket_required = self.page.evaluate(
            "document.getElementById('id_ticket_number').required"
        )
        assert ticket_visible is True
        assert ticket_required is True

        self.page.uncheck("#id_commercial_ride")

        assert self.page.is_enabled("#id_passenger")
        assert self.page.is_enabled("#id_passenger_name")
        ticket_hidden = self.page.evaluate(
            "getComputedStyle(document.getElementById('ticket-number-group')).display === 'none'"
        )
        ticket_required_after_uncheck = self.page.evaluate(
            "document.getElementById('id_ticket_number').required"
        )
        assert ticket_hidden is True
        assert ticket_required_after_uncheck is False
