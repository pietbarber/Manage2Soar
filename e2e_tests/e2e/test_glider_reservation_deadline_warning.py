from datetime import timedelta

from django.utils import timezone

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import DeadlineType, Glider, MaintenanceDeadline
from siteconfig.models import SiteConfiguration


class TestGliderReservationDeadlineWarning(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
                "allow_glider_reservations": True,
                "allow_two_seater_reservations": True,
                "max_reservations_per_year": 3,
            }
        )

    def test_reservation_succeeds_with_expired_deadline_warning(self):
        member = self.create_test_member(
            username="deadline_warning_user",
            email="deadline_warning_user@example.com",
            membership_status="Full Member",
        )

        glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N99001",
            competition_number="DW",
            seats=2,
            is_active=True,
            club_owned=True,
        )

        MaintenanceDeadline.objects.create(
            glider=glider,
            description=DeadlineType.ANNUAL,
            due_date=timezone.now().date() - timedelta(days=10),
        )

        target_date = timezone.now().date() + timedelta(days=7)

        self.login(username=member.username)
        self.page.goto(f"{self.live_server_url}/duty_roster/reservations/create/")
        self.page.wait_for_selector("h5:has-text('New Reservation')")

        self.page.fill('input[name="date"]', target_date.isoformat())
        self.page.select_option('select[name="glider"]', str(glider.pk))
        self.page.select_option('select[name="reservation_type"]', "solo")
        self.page.select_option('select[name="time_preference"]', "morning")
        self.page.get_by_role("button", name="Confirm Reservation").click()

        self.page.wait_for_url(f"{self.live_server_url}/duty_roster/reservations/")
        self.page.wait_for_selector("text=expired maintenance deadlines")
        self.page.wait_for_selector(f"text={glider}")
