"""
E2E coverage for Issue #1120 — Duty Roster "Fill a Roster Hole" page.

Verifies the new ``roster_home`` landing page and the un-gated volunteer-fill
flow work end-to-end in a real browser:

* Anonymous users see the inviting empty state with a sign-in call-to-action.
* A logged-in qualified instructor (with ``schedule_instructors=False``) sees
  the open instructor slot in the table, clicks "Volunteer", confirms, and
  the assignment is filled.
* The calendar-day modal "Volunteer to fill" button is also visible and works
  when the flag is OFF (Issue #1120 core fix).
"""

from datetime import date, timedelta

from duty_roster.models import DutyAssignment
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestRosterHomePage(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        # Issue #1120 scenario: club does NOT pre-schedule tow pilots or
        # instructors (both flags OFF — the default).
        config, _ = SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )
        config.schedule_instructors = False
        config.schedule_tow_pilots = False
        config.save(update_fields=["schedule_instructors", "schedule_tow_pilots"])

    def test_anonymous_sees_empty_state(self):
        """Anonymous visitor to roster_home sees the inviting empty state."""
        self.page.goto(f"{self.live_server_url}/duty_roster/")
        self.page.wait_for_selector("text=Fill a Roster Hole")

        # The "Volunteer Opportunities" card should be present.
        self.page.wait_for_selector("text=Volunteer Opportunities")

        # Anonymous: no table rows, but a sign-in call-to-action.
        sign_in = self.page.locator("a:has-text('Sign in')")
        assert sign_in.count() >= 1

        # The empty-state sign-in message should be visible.
        self.page.wait_for_selector(
            "text=Sign in to see open duty slots you are qualified to fill."
        )

        # No "Volunteer" action buttons (no opportunities for anon).
        # Scope to the table so we don't match the "Sign in to volunteer" CTA.
        volunteer_buttons = self.page.locator("table a.btn:has-text('Volunteer')")
        assert volunteer_buttons.count() == 0

    def test_member_lists_qualified_instructor_when_flag_off(self):
        """
        Issue #1120 core: a qualified instructor sees the open instructor slot
        in roster_home even when schedule_instructors is OFF.
        """
        self.create_test_member(
            username="instr_vol",
            instructor=True,
            membership_status="Full Member",
        )
        self.login(username="instr_vol")

        target_day = date.today() + timedelta(days=10)
        assignment = DutyAssignment.objects.create(date=target_day)

        self.page.goto(f"{self.live_server_url}/duty_roster/")
        self.page.wait_for_selector("text=Volunteer Opportunities")

        # The instructor hole should be listed with a "Volunteer" button.
        # (role_label is "Instructor" by default from config)
        instructor_row = self.page.locator("tr:has-text('Instructor') >> nth=0")
        assert instructor_row.count() >= 1

        volunteer_button = instructor_row.locator("a:has-text('Volunteer')")
        assert volunteer_button.count() == 1
        volunteer_button.first.click()

        # Should land on the confirmation page.
        self.page.wait_for_selector("text=Volunteer to Fill Instructor")

        # Confirm.
        self.page.get_by_role("button", name="Yes, I'll fill this role").click()

        # After confirmation, the slot is filled.
        assignment.refresh_from_db()
        assert assignment.instructor is not None

    def test_modal_volunteer_button_visible_when_flag_off(self):
        """
        Issue #1120 core: the calendar day modal also shows "Volunteer to fill"
        for a qualified member when schedule_instructors is OFF.
        """
        self.create_test_member(
            username="instr_modal",
            instructor=True,
            membership_status="Full Member",
        )
        self.login(username="instr_modal")

        target_day = date.today() + timedelta(days=12)
        assignment = DutyAssignment.objects.create(date=target_day)

        # Navigate to the month calendar and open the day modal.
        self.page.goto(
            f"{self.live_server_url}/duty_roster/calendar/"
            f"{target_day.year}/{target_day.month}/"
        )
        self.page.wait_for_selector("#calendar-body")

        day_cell = self.page.locator(
            f'td[hx-get="/duty_roster/calendar/day/'
            f'{target_day.year}/{target_day.month}/{target_day.day}/"]'
        )
        day_cell.first.click()
        self.page.wait_for_selector("#modal-body")

        # The "Volunteer to fill" button for instructor should be visible,
        # even though schedule_instructors is OFF.
        # Wait for the actual button to appear (HTMX async response).
        volunteer_link = self.page.locator("a:has-text('Volunteer to fill')")
        volunteer_link.first.wait_for(state="visible")
        assert volunteer_link.count() >= 1
        volunteer_link.first.click()

        # Confirmation page.
        self.page.wait_for_selector("text=Volunteer to Fill Instructor")
        self.page.get_by_role("button", name="Yes, I'll fill this role").click()

        assignment.refresh_from_db()
        assert assignment.instructor is not None


class TestRosterHomeUnqualified(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        config, _ = SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )
        config.schedule_instructors = True
        config.schedule_tow_pilots = True
        config.save(update_fields=["schedule_instructors", "schedule_tow_pilots"])

    def test_unqualified_member_sees_empty_state(self):
        """Member without any qualifications sees the empty state."""
        self.create_test_member(
            username="no_qual",
            instructor=False,
            towpilot=False,
            membership_status="Full Member",
        )
        self.login(username="no_qual")

        # Ensure an open slot exists
        target_day = date.today() + timedelta(days=8)
        assignment = DutyAssignment.objects.create(date=target_day)

        self.page.goto(f"{self.live_server_url}/duty_roster/")
        self.page.wait_for_selector("text=Volunteer Opportunities")

        # No "Volunteer" action buttons (member has no qualifications).
        # Scope to the table so we don't match the "Sign in to volunteer" CTA.
        volunteer_buttons = self.page.locator("table a.btn:has-text('Volunteer')")
        assert volunteer_buttons.count() == 0

        # Empty state message.
        self.page.wait_for_selector(
            "text=No openings match your qualifications right now."
        )


class TestCommercialPilotHoleGate(DjangoPlaywrightTestCase):
    """Issue #1129: the Commercial Pilot "hole to fill" is only offered to
    clubs that BOTH enable commercial rides and schedule commercial pilots.
    Clubs like ssc (both flags OFF) should see no Commercial Pilot card.
    """

    def setUp(self):
        super().setUp()
        config, _ = SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )
        # Start with both commercial flags OFF (the ssc case). Individual tests
        # override this to exercise the positive path.
        config.schedule_instructors = True
        config.schedule_tow_pilots = True
        config.commercial_rides_enabled = False
        config.schedule_commercial_pilots = False
        config.save(
            update_fields=[
                "schedule_instructors",
                "schedule_tow_pilots",
                "commercial_rides_enabled",
                "schedule_commercial_pilots",
            ]
        )

    def test_modal_hides_commercial_when_flags_off(self):
        """Calendar day modal does NOT render the Commercial Pilot card when
        both commercial flags are OFF (default: ssc-like club). Issue #1129."""
        self.create_test_member(
            username="cp_off",
            glider_rating="commercial",
            membership_status="Full Member",
        )
        self.login(username="cp_off")

        target_day = date.today() + timedelta(days=9)
        DutyAssignment.objects.create(date=target_day)

        self.page.goto(
            f"{self.live_server_url}/duty_roster/calendar/"
            f"{target_day.year}/{target_day.month}/"
        )
        self.page.wait_for_selector("#calendar-body")

        day_cell = self.page.locator(
            f'td[hx-get="/duty_roster/calendar/day/'
            f'{target_day.year}/{target_day.month}/{target_day.day}/"]'
        )
        day_cell.first.click()
        self.page.wait_for_selector("#modal-body")

        # The commercial-pilot card should not be rendered at all.
        commercial_label = self.page.locator("text=Commercial Pilot")
        assert commercial_label.count() == 0

        # No "Volunteer to fill" button for commercial pilot.
        self.page.wait_for_timeout(200)  # allow HTMX response to settle
        volunteer_commercial = self.page.locator("a[href*='/commercial_pilot/']")
        assert volunteer_commercial.count() == 0

    def test_modal_shows_commercial_when_both_flags_on(self):
        """Calendar day modal DOES render the Commercial Pilot card with a
        "Volunteer to fill" button when both flags are ON. Issue #1129."""
        config = SiteConfiguration.objects.first()
        config.commercial_rides_enabled = True
        config.schedule_commercial_pilots = True
        config.save(
            update_fields=["commercial_rides_enabled", "schedule_commercial_pilots"]
        )

        self.create_test_member(
            username="cp_on",
            glider_rating="commercial",
            membership_status="Full Member",
        )
        self.login(username="cp_on")

        target_day = date.today() + timedelta(days=11)
        assignment = DutyAssignment.objects.create(date=target_day)

        self.page.goto(
            f"{self.live_server_url}/duty_roster/calendar/"
            f"{target_day.year}/{target_day.month}/"
        )
        self.page.wait_for_selector("#calendar-body")

        day_cell = self.page.locator(
            f'td[hx-get="/duty_roster/calendar/day/'
            f'{target_day.year}/{target_day.month}/{target_day.day}/"]'
        )
        day_cell.first.click()
        self.page.wait_for_selector("#modal-body")

        # The commercial-pilot card should be rendered.
        commercial_label = self.page.locator("text=Commercial Pilot")
        assert commercial_label.count() >= 1

        # And a "Volunteer to fill" button pointing at commercial_pilot.
        volunteer_link = self.page.locator(
            "a[href*='/commercial_pilot/']:has-text('Volunteer')"
        )
        volunteer_link.first.wait_for(state="visible")
        assert volunteer_link.count() >= 1

        volunteer_link.first.click()
        self.page.wait_for_selector("text=Volunteer to Fill")

        self.page.get_by_role("button", name="Yes, I'll fill this role").click()

        assignment.refresh_from_db()
        assert assignment.commercial_pilot is not None
