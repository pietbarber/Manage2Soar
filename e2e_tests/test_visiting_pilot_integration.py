"""
Test visiting pilot integration with logsheet flight forms.
"""

from django.test import TestCase

from logsheet.forms import FlightForm
from logsheet.models import Airfield, Logsheet
from members.models import Member
from siteconfig.models import SiteConfiguration


class VisitingPilotFormIntegrationTest(TestCase):
    """Test visiting pilots appear in flight form dropdowns."""

    def setUp(self):
        """Set up test data."""
        # Create SiteConfiguration with visiting pilot enabled
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="testclub.org",
            club_abbreviation="TC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
            visiting_pilot_auto_approve=True,
        )

        # Create regular members
        self.active_member = Member.objects.create(
            username="active",
            first_name="Active",
            last_name="Member",
            email="active@example.com",
            membership_status="Full Member",
            SSA_member_number="12345",
        )

        self.inactive_member = Member.objects.create(
            username="inactive",
            first_name="Inactive",
            last_name="Member",
            email="inactive@example.com",
            membership_status="Inactive",
            SSA_member_number="12346",
        )

        # Create visiting pilot members
        self.visiting_pilot = Member.objects.create(
            username="visiting",
            first_name="Visiting",
            last_name="Pilot",
            email="visiting@example.com",
            membership_status="Affiliate Member",
            SSA_member_number="12347",
            home_club="Other Soaring Club",
        )

        self.visiting_instructor = Member.objects.create(
            username="visitinst",
            first_name="Visiting",
            last_name="Instructor",
            email="visitinst@example.com",
            membership_status="Affiliate Member",
            SSA_member_number="12348",
            home_club="Another Club",
            instructor=True,
        )

        self.visiting_towpilot = Member.objects.create(
            username="visittow",
            first_name="Visiting",
            last_name="TowPilot",
            email="visittow@example.com",
            membership_status="Affiliate Member",
            SSA_member_number="12349",
            home_club="Tow Club",
            towpilot=True,
        )

        # Create an airfield and logsheet for the form
        self.airfield = Airfield.objects.create(
            name="Test Field",
            identifier="TEST",
        )
        self.logsheet = Logsheet.objects.create(
            log_date="2024-01-15",
            airfield=self.airfield,
            created_by=self.active_member,
            duty_officer=self.active_member,
        )

    def test_visiting_pilots_in_pilot_dropdown(self):
        """Test visiting pilots appear in pilot dropdown."""
        form = FlightForm(logsheet=self.logsheet)
        pilot_choices = list(form.fields["pilot"].choices)

        # Should have "-------", optgroups for active members, visiting pilots
        self.assertEqual(pilot_choices[0], ("", "-------"))

        # Find the optgroups
        optgroups = pilot_choices[1:]
        optgroup_names = [group[0] for group in optgroups]

        self.assertIn("Active Members", optgroup_names)
        self.assertIn("Visiting Pilots", optgroup_names)

        # Check visiting pilots optgroup contains our visiting pilot
        visiting_group = next(
            group for group in optgroups if group[0] == "Visiting Pilots"
        )
        visiting_choices = visiting_group[1]

        # Should include visiting pilot with home club
        visiting_pilot_choice = next(
            choice for choice in visiting_choices if choice[0] == self.visiting_pilot.pk
        )
        self.assertIn("Other Soaring Club", visiting_pilot_choice[1])

    def test_visiting_instructors_in_instructor_dropdown(self):
        """Test visiting instructors appear in instructor dropdown."""
        form = FlightForm(logsheet=self.logsheet)
        instructor_choices = list(form.fields["instructor"].choices)

        # Should have "-------", optgroups
        self.assertEqual(instructor_choices[0], ("", "-------"))

        # Find the optgroups
        optgroups = instructor_choices[1:]
        optgroup_names = [group[0] for group in optgroups]

        self.assertIn("Visiting Instructors", optgroup_names)

        # Check visiting instructors optgroup contains our visiting instructor
        visiting_group = next(
            group for group in optgroups if group[0] == "Visiting Instructors"
        )
        visiting_choices = visiting_group[1]

        # Should include visiting instructor with home club
        visiting_instructor_choice = next(
            choice
            for choice in visiting_choices
            if choice[0] == self.visiting_instructor.pk
        )
        self.assertIn("Another Club", visiting_instructor_choice[1])

    def test_visiting_towpilots_in_towpilot_dropdown(self):
        """Test visiting tow pilots appear in tow pilot dropdown."""
        form = FlightForm(logsheet=self.logsheet)
        tow_pilot_choices = list(form.fields["tow_pilot"].choices)

        # Should have "-------", optgroups
        self.assertEqual(tow_pilot_choices[0], ("", "-------"))

        # Find the optgroups
        optgroups = tow_pilot_choices[1:]
        optgroup_names = [group[0] for group in optgroups]

        self.assertIn("Visiting Tow Pilots", optgroup_names)

        # Check visiting tow pilots optgroup contains our visiting tow pilot
        visiting_group = next(
            group for group in optgroups if group[0] == "Visiting Tow Pilots"
        )
        visiting_choices = visiting_group[1]

        # Should include visiting tow pilot with home club
        visiting_towpilot_choice = next(
            choice
            for choice in visiting_choices
            if choice[0] == self.visiting_towpilot.pk
        )
        self.assertIn("Tow Club", visiting_towpilot_choice[1])

    def test_visiting_pilots_in_passenger_dropdown(self):
        """Test visiting pilots appear in passenger dropdown."""
        form = FlightForm(logsheet=self.logsheet)

        # Passenger field might not exist in all form contexts
        if "passenger" in form.fields:
            passenger_choices = list(form.fields["passenger"].choices)

            # Should have "-------", optgroups
            self.assertEqual(passenger_choices[0], ("", "-------"))

            # Find the optgroups
            optgroups = passenger_choices[1:]
            optgroup_names = [group[0] for group in optgroups]

            self.assertIn("Visiting Pilots", optgroup_names)

            # Check visiting pilots optgroup contains all visiting pilots
            visiting_group = next(
                group for group in optgroups if group[0] == "Visiting Pilots"
            )
            visiting_choices = visiting_group[1]

            # Should include all visiting pilots
            visiting_pks = [choice[0] for choice in visiting_choices]
            self.assertIn(self.visiting_pilot.pk, visiting_pks)
            self.assertIn(self.visiting_instructor.pk, visiting_pks)
            self.assertIn(self.visiting_towpilot.pk, visiting_pks)

    def test_visiting_pilots_disabled_no_optgroups(self):
        """Test visiting pilots don't appear when feature is disabled."""
        # Disable visiting pilots
        self.config.visiting_pilot_enabled = False
        self.config.save()

        form = FlightForm(logsheet=self.logsheet)

        # Check pilot dropdown doesn't have visiting pilots
        pilot_choices = list(form.fields["pilot"].choices)
        optgroups = pilot_choices[1:]
        optgroup_names = [group[0] for group in optgroups]

        self.assertNotIn("Visiting Pilots", optgroup_names)

    def test_no_home_club_shows_unknown(self):
        """Test visiting pilots without home club show 'Unknown Club'."""
        # Create visiting pilot without home club
        visiting_no_club = Member.objects.create(
            username="noclub",
            first_name="No",
            last_name="Club",
            email="noclub@example.com",
            membership_status="Affiliate Member",
            SSA_member_number="12350",
            home_club="",  # Empty home club
        )

        form = FlightForm(logsheet=self.logsheet)
        pilot_choices = list(form.fields["pilot"].choices)

        # Find visiting pilots optgroup
        optgroups = pilot_choices[1:]
        visiting_group = next(
            group for group in optgroups if group[0] == "Visiting Pilots"
        )
        visiting_choices = visiting_group[1]

        # Find the no-club pilot choice
        no_club_choice = next(
            choice for choice in visiting_choices if choice[0] == visiting_no_club.pk
        )
        self.assertIn("Unknown Club", no_club_choice[1])
