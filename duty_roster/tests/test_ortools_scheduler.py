"""
Unit tests for OR-Tools duty roster scheduler.

Tests cover:
- Hard constraints (role qualification, blackouts, avoidances, etc.)
- Soft constraints (preferences, pairings, last duty date)
- Edge cases (no eligible members, infeasibility)
- Integration with Django ORM
- Performance benchmarking
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase

from duty_roster.models import (
    DutyAssignment,
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    DutyRoleDefinition,
    MemberBlackout,
)
from duty_roster.ortools_scheduler import (
    MAX_ASSIGNMENT_CONCENTRATION_WEIGHT,
    ROLE_SPLIT_BALANCE_WEIGHT,
    WEEKEND_SPACING_PENALTY_BY_LAG_WEEKS,
    DutyRosterScheduler,
    SchedulingData,
    extract_scheduling_data,
    generate_roster_ortools,
)
from duty_roster.roster_generator import (
    clear_operational_season_cache,
    get_default_max_assignments_per_month,
)
from members.constants.membership import DEFAULT_ROLES
from members.models import Member
from siteconfig.models import SiteConfiguration


class ORToolsSchedulerBasicTests(TestCase):
    """Test basic OR-Tools scheduler functionality."""

    def setUp(self):
        """Create minimal test data for scheduler validation."""
        # Create 4 members with different role qualifications
        self.instructor1 = Member.objects.create(
            username="instructor1",
            email="inst1@test.com",
            first_name="Alice",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )

        self.towpilot1 = Member.objects.create(
            username="towpilot1",
            email="tow1@test.com",
            first_name="Bob",
            last_name="Towpilot",
            membership_status="Full Member",
            towpilot=True,
            is_active=True,
        )

        self.do1 = Member.objects.create(
            username="do1",
            email="do1@test.com",
            first_name="Carol",
            last_name="DutyOfficer",
            membership_status="Full Member",
            duty_officer=True,
            is_active=True,
        )

        self.ado1 = Member.objects.create(
            username="ado1",
            email="ado1@test.com",
            first_name="Dave",
            last_name="AssistantDO",
            membership_status="Full Member",
            assistant_duty_officer=True,
            is_active=True,
        )

        # Create multi-role member
        self.multi = Member.objects.create(
            username="multi",
            email="multi@test.com",
            first_name="Eve",
            last_name="MultiRole",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
            is_active=True,
        )

        # Define test weekend dates
        base_date = date(2026, 3, 1)  # March 2026 starts on Sunday
        self.test_dates = [
            base_date,  # Sunday, March 1
            base_date + timedelta(days=6),  # Saturday, March 7
            base_date + timedelta(days=7),  # Sunday, March 8
        ]

        self.test_roles = [
            "instructor",
            "towpilot",
            "duty_officer",
            "assistant_duty_officer",
        ]

    def test_extract_scheduling_data_basic(self):
        """Test that extract_scheduling_data() retrieves Django ORM data correctly."""
        # No preferences or blackouts yet
        data = extract_scheduling_data(
            year=2026,
            month=3,
            roles=self.test_roles,
            exclude_dates=None,
        )

        self.assertIsInstance(data, SchedulingData)
        self.assertEqual(len(data.members), 5)  # All 5 members created
        self.assertEqual(len(data.roles), 4)
        self.assertGreater(
            len(data.duty_days), 0
        )  # At least some weekend days in March
        self.assertEqual(len(data.preferences), 0)  # No preferences created yet
        self.assertEqual(len(data.blackouts), 0)

    def test_scheduler_initialization(self):
        """Test that DutyRosterScheduler initializes without errors."""
        data = extract_scheduling_data(year=2026, month=3, roles=self.test_roles)
        scheduler = DutyRosterScheduler(data)

        self.assertIsNotNone(scheduler.model)
        self.assertIsNotNone(scheduler.solver)
        self.assertEqual(
            len(scheduler.x), 0
        )  # No variables created until _create_decision_variables()

    def test_sparse_variable_creation(self):
        """Test that sparse variable creation only creates valid tuples."""
        # Create one preference with dont_schedule=True
        DutyPreference.objects.create(
            member=self.instructor1,
            dont_schedule=True,
        )

        data = extract_scheduling_data(year=2026, month=3, roles=self.test_roles)
        scheduler = DutyRosterScheduler(data)
        scheduler._create_decision_variables()

        # instructor1 should have no variables (dont_schedule=True)
        instructor1_vars = [
            key for key in scheduler.x.keys() if key[0] == self.instructor1.id
        ]
        self.assertEqual(len(instructor1_vars), 0)

        # Other members should have variables
        towpilot1_vars = [
            key for key in scheduler.x.keys() if key[0] == self.towpilot1.id
        ]
        self.assertGreater(len(towpilot1_vars), 0)


class ORToolsHardConstraintsTests(TestCase):
    """Test individual hard constraints."""

    def setUp(self):
        """Create test data for constraint validation."""
        # Create members
        self.member1 = Member.objects.create(
            username="member1",
            email="m1@test.com",
            first_name="Member",
            last_name="One",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
            is_active=True,
        )

        self.member2 = Member.objects.create(
            username="member2",
            email="m2@test.com",
            first_name="Member",
            last_name="Two",
            membership_status="Full Member",
            instructor=True,
            duty_officer=True,
            is_active=True,
        )

        self.member3 = Member.objects.create(
            username="member3",
            email="m3@test.com",
            first_name="Member",
            last_name="Three",
            membership_status="Full Member",
            towpilot=True,
            assistant_duty_officer=True,
            is_active=True,
        )

        # Add extra members so that each scarce role (DO, ADO, towpilot, instructor)
        # has at least 2 qualifying members.  Without these, a single member must
        # cover all 9 March 2026 weekend days in that role, which exceeds
        # max_assignments_per_month=8 and makes the solver INFEASIBLE.
        self.member4 = Member.objects.create(
            username="member4",
            email="m4@test.com",
            first_name="Member",
            last_name="Four",
            membership_status="Full Member",
            instructor=True,
            duty_officer=True,
            is_active=True,
        )

        self.member5 = Member.objects.create(
            username="member5",
            email="m5@test.com",
            first_name="Member",
            last_name="Five",
            membership_status="Full Member",
            towpilot=True,
            assistant_duty_officer=True,
            is_active=True,
        )

        # Create preferences
        DutyPreference.objects.create(member=self.member1, max_assignments_per_month=8)
        DutyPreference.objects.create(member=self.member2, max_assignments_per_month=8)
        DutyPreference.objects.create(member=self.member3, max_assignments_per_month=8)
        DutyPreference.objects.create(member=self.member4, max_assignments_per_month=8)
        DutyPreference.objects.create(member=self.member5, max_assignments_per_month=8)

        self.test_dates = [
            date(2026, 3, 1),  # Sunday
            date(2026, 3, 2),  # Monday (consecutive)
        ]
        self.test_roles = [
            "instructor",
            "towpilot",
            "duty_officer",
            "assistant_duty_officer",
        ]

    def test_role_qualification_constraint(self):
        """Test that members are only assigned to roles they're qualified for."""
        data = SchedulingData(
            members=[self.member1, self.member2, self.member3],
            duty_days=self.test_dates,
            roles=self.test_roles,
            preferences={
                self.member1.id: DutyPreference.objects.get(member=self.member1),
                self.member2.id: DutyPreference.objects.get(member=self.member2),
                self.member3.id: DutyPreference.objects.get(member=self.member3),
            },
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={role: {"scarcity_score": 1.0} for role in self.test_roles},
            earliest_duty_day=self.test_dates[0],
        )

        scheduler = DutyRosterScheduler(data)
        scheduler._create_decision_variables()

        # member1 should NOT have variables for duty_officer or assistant_duty_officer
        member1_do_vars = [
            key
            for key in scheduler.x.keys()
            if key[0] == self.member1.id and key[1] == "duty_officer"
        ]
        self.assertEqual(len(member1_do_vars), 0)

        # member2 should NOT have variables for towpilot or assistant_duty_officer
        member2_tp_vars = [
            key
            for key in scheduler.x.keys()
            if key[0] == self.member2.id and key[1] == "towpilot"
        ]
        self.assertEqual(len(member2_tp_vars), 0)

        # member3 should NOT have variables for instructor or duty_officer
        member3_inst_vars = [
            key
            for key in scheduler.x.keys()
            if key[0] == self.member3.id and key[1] == "instructor"
        ]
        self.assertEqual(len(member3_inst_vars), 0)

    def test_blackout_constraint(self):
        """Test that members are not assigned on blackout dates."""
        # Create blackout for member1 on first test date
        MemberBlackout.objects.create(member=self.member1, date=self.test_dates[0])

        data = extract_scheduling_data(year=2026, month=3, roles=self.test_roles)
        scheduler = DutyRosterScheduler(data)
        scheduler._create_decision_variables()

        # member1 should have no variables for blackout date
        member1_blackout_vars = [
            key
            for key in scheduler.x.keys()
            if key[0] == self.member1.id and key[2] == self.test_dates[0]
        ]
        self.assertEqual(len(member1_blackout_vars), 0)

    def test_avoidance_constraint(self):
        """Test that members who avoid each other are not assigned on same day."""
        # Create avoidance: member1 avoids member2
        DutyAvoidance.objects.create(member=self.member1, avoid_with=self.member2)

        # Use a controlled 3-date window (2 non-consecutive + 1 pair) so that
        # the problem is feasible regardless of how the full March month looks.
        # Using extract_scheduling_data(year=2026, month=3) would produce 9
        # weekend days; with the avoidance applied, member4 would need to work
        # all 9 days alone to cover both instructor and DO—exceeding max=8.
        three_dates = [date(2026, 3, 1), date(2026, 3, 7), date(2026, 3, 8)]
        prefs = {
            m.id: DutyPreference.objects.get(member=m)
            for m in [
                self.member1,
                self.member2,
                self.member3,
                self.member4,
                self.member5,
            ]
        }
        avoidances = {(self.member1.id, self.member2.id)}
        data = SchedulingData(
            members=[
                self.member1,
                self.member2,
                self.member3,
                self.member4,
                self.member5,
            ],
            duty_days=three_dates,
            roles=self.test_roles,
            preferences=prefs,
            blackouts=set(),
            avoidances=avoidances,
            pairings=set(),
            role_scarcity={role: {"scarcity_score": 1.0} for role in self.test_roles},
            earliest_duty_day=three_dates[0],
        )

        # Verify avoidance is in data
        self.assertIn((self.member1.id, self.member2.id), data.avoidances)

        scheduler = DutyRosterScheduler(data, enforce_adjacent_weekend_spacing=False)
        result = scheduler.solve(timeout_seconds=5.0)

        # Assert solver found a solution
        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))

        schedule = result["schedule"]
        for day_schedule in schedule:
            assigned_members = set(
                member_id
                for member_id in day_schedule["slots"].values()
                if member_id is not None
            )
            # member1 and member2 should never both be in assigned_members
            self.assertFalse(
                self.member1.id in assigned_members
                and self.member2.id in assigned_members,
                f"Avoidance violated on {day_schedule['date']}: both member1 and member2 assigned",
            )

    def test_one_assignment_per_day_constraint(self):
        """Test that members are assigned to at most one role per day."""
        # Use a bounded 3-date window to keep the problem feasible with 5 members.
        # Using the full March 2026 month (9 weekend days) risks INFEASIBLE
        # when role coverage is tight; the constraint logic itself only needs a
        # handful of days to be verified.
        three_dates = [date(2026, 3, 1), date(2026, 3, 7), date(2026, 3, 8)]
        prefs = {
            m.id: DutyPreference.objects.get(member=m)
            for m in [
                self.member1,
                self.member2,
                self.member3,
                self.member4,
                self.member5,
            ]
        }
        data = SchedulingData(
            members=[
                self.member1,
                self.member2,
                self.member3,
                self.member4,
                self.member5,
            ],
            duty_days=three_dates,
            roles=self.test_roles,
            preferences=prefs,
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={role: {"scarcity_score": 1.0} for role in self.test_roles},
            earliest_duty_day=three_dates[0],
        )
        scheduler = DutyRosterScheduler(data, enforce_adjacent_weekend_spacing=False)
        result = scheduler.solve(timeout_seconds=5.0)

        # Assert solver found a solution
        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))

        schedule = result["schedule"]
        for day_schedule in schedule:
            member_role_count = {}
            for role, member_id in day_schedule["slots"].items():
                if member_id is not None:
                    member_role_count[member_id] = (
                        member_role_count.get(member_id, 0) + 1
                    )

            # No member should have more than 1 role on same day
            for member_id, count in member_role_count.items():
                self.assertLessEqual(
                    count,
                    1,
                    f"Member {member_id} assigned to {count} roles on {day_schedule['date']}",
                )

    def test_anti_repeat_constraint(self):
        """Test that members don't do same role on consecutive days."""
        # Use consecutive days (Sunday, Monday).
        # member5 is included so towpilot has 2 qualified members (member1 and
        # member5); without a second towpilot the hard anti-repeat constraint
        # makes the problem INFEASIBLE because member1 is the sole option and
        # cannot be assigned the same role on both consecutive days.
        data = SchedulingData(
            members=[self.member1, self.member2, self.member5],
            duty_days=[date(2026, 3, 1), date(2026, 3, 2)],  # Consecutive
            roles=["instructor", "towpilot"],
            preferences={
                self.member1.id: DutyPreference.objects.get(member=self.member1),
                self.member2.id: DutyPreference.objects.get(member=self.member2),
                self.member5.id: DutyPreference.objects.get(member=self.member5),
            },
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={
                "instructor": {"scarcity_score": 1.0},
                "towpilot": {"scarcity_score": 1.0},
            },
            earliest_duty_day=date(2026, 3, 1),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        # Assert solver found a solution
        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))

        schedule = result["schedule"]
        # Check both days
        day1_slots = schedule[0]["slots"]
        day2_slots = schedule[1]["slots"]

        for role in ["instructor", "towpilot"]:
            if day1_slots[role] is not None and day2_slots[role] is not None:
                self.assertNotEqual(
                    day1_slots[role],
                    day2_slots[role],
                    f"Member {day1_slots[role]} assigned to {role} on consecutive days",
                )

    def test_anti_repeat_constraint_applies_to_adjacent_duty_days(self):
        """Test anti-repeat across adjacent duty days with a calendar gap."""
        data = SchedulingData(
            members=[self.member1, self.member2],
            duty_days=[date(2026, 3, 1), date(2026, 3, 7)],
            roles=["instructor"],
            preferences={
                self.member1.id: DutyPreference.objects.get(member=self.member1),
                self.member2.id: DutyPreference.objects.get(member=self.member2),
            },
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 1),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        slots_day1 = result["schedule"][0]["slots"]["instructor"]
        slots_day2 = result["schedule"][1]["slots"]["instructor"]
        self.assertNotEqual(
            slots_day1,
            slots_day2,
            "Instructor should not repeat on adjacent duty days even across week gaps.",
        )

    def test_carryover_anti_repeat_blocks_first_day_repeat(self):
        """First generated day should respect prior published duty-day assignment."""
        DutyAssignment.objects.create(
            date=date(2026, 2, 28),
            instructor=self.member1,
        )

        data = extract_scheduling_data(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 1),
            roles=["instructor"],
        )

        self.assertEqual(data.prior_assignments.get("instructor"), self.member1.id)

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        assigned = result["schedule"][0]["slots"]["instructor"]
        self.assertNotEqual(
            assigned,
            self.member1.id,
            "Carry-over anti-repeat should prevent first-day same-role repeat.",
        )

    def test_carryover_uses_latest_scheduled_assignment_only(self):
        """Carry-over source should skip ad-hoc days and use latest scheduled day."""
        # Last published/scheduled roster day before anchor
        DutyAssignment.objects.create(
            date=date(2026, 2, 21),
            instructor=self.member1,
            is_scheduled=True,
        )
        # Later ad-hoc day should be ignored for carry-over sourcing
        DutyAssignment.objects.create(
            date=date(2026, 2, 28),
            instructor=self.member2,
            is_scheduled=False,
        )

        data = extract_scheduling_data(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 1),
            roles=["instructor"],
        )

        self.assertEqual(
            data.prior_assignments.get("instructor"),
            self.member1.id,
            "Expected latest scheduled assignment to be used for carry-over.",
        )

    def test_carryover_hard_block_skips_when_no_alternative_candidate(self):
        """Carry-over should not make model infeasible when first day has one option."""
        data = SchedulingData(
            members=[self.member1],
            duty_days=[date(2026, 3, 1)],
            roles=["instructor"],
            preferences={
                self.member1.id: DutyPreference.objects.get(member=self.member1),
            },
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 1),
            prior_assignments={"instructor": self.member1.id},
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        assigned = result["schedule"][0]["slots"]["instructor"]
        self.assertEqual(
            assigned,
            self.member1.id,
            "Expected first day to remain assignable when no alternative exists.",
        )

    def test_max_assignments_constraint(self):
        """Test that members don't exceed max_assignments_per_month."""
        # Set low max for member1
        pref1 = DutyPreference.objects.get(member=self.member1)
        pref1.max_assignments_per_month = 2
        pref1.save()

        # Create many duty days to trigger constraint
        many_dates = [
            date(2026, 3, 1) + timedelta(days=i * 7) for i in range(4)
        ]  # 4 Sundays

        data = SchedulingData(
            members=[self.member1, self.member2, self.member3],
            duty_days=many_dates,
            roles=["instructor"],  # Only one role to simplify
            preferences={
                self.member1.id: pref1,
                self.member2.id: DutyPreference.objects.get(member=self.member2),
                self.member3.id: DutyPreference.objects.get(member=self.member3),
            },
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=many_dates[0],
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        # Assert solver found a solution
        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))

        schedule = result["schedule"]
        member1_assignments = sum(
            1
            for day_schedule in schedule
            for member_id in day_schedule["slots"].values()
            if member_id == self.member1.id
        )
        self.assertLessEqual(
            member1_assignments,
            2,
            f"member1 assigned {member1_assignments} times (max is 2)",
        )

    def test_default_max_assignments_uses_site_configuration(self):
        """Members without preferences should use SiteConfiguration fallback cap."""
        clear_operational_season_cache()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="example.org",
            club_abbreviation="TC",
            duty_default_max_assignments_per_month=1,
        )

        member_without_pref = Member.objects.create(
            username="nopref_instructor",
            email="nopref@test.com",
            first_name="NoPref",
            last_name="Instructor",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )

        data = SchedulingData(
            members=[member_without_pref],
            duty_days=[date(2026, 3, 1), date(2026, 3, 8)],
            roles=["instructor"],
            preferences={},
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 1),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertEqual(result["status"], "INFEASIBLE")

    def test_default_max_assignments_cache_invalidates_after_config_save(self):
        """Updated SiteConfiguration values should be reflected without process restart."""
        clear_operational_season_cache()
        config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="example.org",
            club_abbreviation="TC",
            duty_default_max_assignments_per_month=1,
        )

        self.assertEqual(get_default_max_assignments_per_month(), 1)

        config.duty_default_max_assignments_per_month = 3
        config.save()

        self.assertEqual(get_default_max_assignments_per_month(), 3)

    def test_adjacent_weekend_spacing_allows_when_member_opted_in(self):
        """Members opted in to weekend doubles can be assigned adjacent weekends."""
        pref1 = DutyPreference.objects.get(member=self.member1)
        pref1.allow_weekend_double = True
        pref1.save()

        # Force member1 to be the only available member on two adjacent weekends.
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 7))
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 14))

        data = SchedulingData(
            members=[self.member1, self.member2],
            duty_days=[date(2026, 3, 7), date(2026, 3, 14)],
            roles=["instructor"],
            preferences={
                self.member1.id: pref1,
                self.member2.id: DutyPreference.objects.get(member=self.member2),
            },
            blackouts={
                (self.member2.id, date(2026, 3, 7)),
                (self.member2.id, date(2026, 3, 14)),
            },
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 7),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        assigned_member_ids = [
            day_schedule["slots"]["instructor"] for day_schedule in result["schedule"]
        ]
        self.assertEqual(assigned_member_ids, [self.member1.id, self.member1.id])

    def test_concentration_penalty_reduces_peak_load_in_two_month_window(self):
        """Max-load concentration penalty should lower peak assignments when feasible."""
        # Build a realistic pool similar to tenant-demo constraints: many eligible members,
        # with a subset marked very stale so baseline objective tends to over-prefer them.
        members = []
        for idx in range(20):
            member = Member.objects.create(
                username=f"fairness_member_{idx}",
                email=f"fairness_member_{idx}@test.com",
                first_name=f"Fair{idx}",
                last_name="Member",
                membership_status="Full Member",
                instructor=True,
                is_active=True,
            )
            members.append(member)

            pref = DutyPreference.objects.create(member=member)
            pref.instructor_percent = 100
            pref.max_assignments_per_month = 4
            if idx < 4:
                pref.last_duty_date = date(2020, 1, 1)
            else:
                pref.last_duty_date = date(2026, 3, 20)
            pref.save()

        two_month_sundays = [
            date(2026, 4, 5),
            date(2026, 4, 12),
            date(2026, 4, 19),
            date(2026, 4, 26),
            date(2026, 5, 3),
            date(2026, 5, 10),
            date(2026, 5, 17),
            date(2026, 5, 24),
            date(2026, 5, 31),
        ]

        data = SchedulingData(
            members=members,
            duty_days=two_month_sundays,
            roles=["instructor"],
            preferences={m.id: DutyPreference.objects.get(member=m) for m in members},
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=two_month_sundays[0],
            month_span=2,
        )

        with patch(
            "duty_roster.ortools_scheduler.MAX_ASSIGNMENT_CONCENTRATION_WEIGHT", 0
        ):
            baseline = DutyRosterScheduler(data).solve(timeout_seconds=10.0)
        tuned = DutyRosterScheduler(data).solve(timeout_seconds=10.0)

        self.assertIn(baseline["status"], ("OPTIMAL", "FEASIBLE"))
        self.assertIn(tuned["status"], ("OPTIMAL", "FEASIBLE"))
        self.assertGreater(MAX_ASSIGNMENT_CONCENTRATION_WEIGHT, 0)

        def _max_assignments(result):
            counts = {}
            for day in result["schedule"]:
                for member_id in day["slots"].values():
                    if member_id is None:
                        continue
                    counts[member_id] = counts.get(member_id, 0) + 1
            return max(counts.values()) if counts else 0

        baseline_peak = _max_assignments(baseline)
        tuned_peak = _max_assignments(tuned)

        self.assertLessEqual(
            tuned_peak,
            baseline_peak,
            f"Expected tuned objective to reduce or match peak load; baseline={baseline_peak}, tuned={tuned_peak}",
        )

    def test_role_split_penalty_reduces_dual_role_drift(self):
        """Role-split penalty should not worsen dual-role split drift."""
        dual_member = Member.objects.create(
            username="dual_split_member",
            email="dual_split_member@test.com",
            first_name="Dual",
            last_name="Split",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
            is_active=True,
        )
        dual_pref = DutyPreference.objects.create(member=dual_member)
        dual_pref.instructor_percent = 50
        dual_pref.towpilot_percent = 50
        dual_pref.max_assignments_per_month = 8
        dual_pref.allow_weekend_double = True
        dual_pref.last_duty_date = date(2019, 1, 1)
        dual_pref.save()

        instructor_only = Member.objects.create(
            username="instructor_only_split",
            email="instructor_only_split@test.com",
            first_name="Instructor",
            last_name="Only",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )
        DutyPreference.objects.create(
            member=instructor_only,
            instructor_percent=100,
            max_assignments_per_month=8,
            allow_weekend_double=True,
            last_duty_date=date(2026, 3, 20),
        )

        tow_only = Member.objects.create(
            username="tow_only_split",
            email="tow_only_split@test.com",
            first_name="Tow",
            last_name="Only",
            membership_status="Full Member",
            towpilot=True,
            is_active=True,
        )
        DutyPreference.objects.create(
            member=tow_only,
            towpilot_percent=100,
            max_assignments_per_month=8,
            allow_weekend_double=True,
            last_duty_date=date(2026, 3, 20),
        )

        duty_days = [
            date(2026, 4, 4),
            date(2026, 4, 5),
            date(2026, 4, 11),
            date(2026, 4, 12),
            date(2026, 4, 18),
            date(2026, 4, 19),
        ]

        data = SchedulingData(
            members=[dual_member, instructor_only, tow_only],
            duty_days=duty_days,
            roles=["instructor", "towpilot"],
            preferences={
                dual_member.id: dual_pref,
                instructor_only.id: DutyPreference.objects.get(member=instructor_only),
                tow_only.id: DutyPreference.objects.get(member=tow_only),
            },
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={
                "instructor": {"scarcity_score": 1.0},
                "towpilot": {"scarcity_score": 1.0},
            },
            earliest_duty_day=duty_days[0],
            month_span=1,
        )

        deterministic_seed = 12345

        baseline_scheduler = DutyRosterScheduler(data)
        baseline_scheduler.solver.parameters.num_search_workers = 1
        baseline_scheduler.solver.parameters.random_seed = deterministic_seed
        with patch("duty_roster.ortools_scheduler.ROLE_SPLIT_BALANCE_WEIGHT", 0):
            baseline = baseline_scheduler.solve(timeout_seconds=10.0)

        tuned_scheduler = DutyRosterScheduler(data)
        tuned_scheduler.solver.parameters.num_search_workers = 1
        tuned_scheduler.solver.parameters.random_seed = deterministic_seed
        tuned = tuned_scheduler.solve(timeout_seconds=10.0)

        self.assertIn(baseline["status"], ("OPTIMAL", "FEASIBLE"))
        self.assertIn(tuned["status"], ("OPTIMAL", "FEASIBLE"))
        self.assertGreater(ROLE_SPLIT_BALANCE_WEIGHT, 0)

        def _dual_counts(result):
            instructor_count = 0
            tow_count = 0
            for day in result["schedule"]:
                if day["slots"].get("instructor") == dual_member.id:
                    instructor_count += 1
                if day["slots"].get("towpilot") == dual_member.id:
                    tow_count += 1
            return instructor_count, tow_count

        baseline_inst, baseline_tow = _dual_counts(baseline)
        tuned_inst, tuned_tow = _dual_counts(tuned)

        baseline_drift = abs(baseline_inst - baseline_tow)
        tuned_drift = abs(tuned_inst - tuned_tow)

        self.assertLessEqual(
            tuned_drift,
            baseline_drift,
            f"Expected role split penalty to reduce or match drift; baseline={baseline_drift}, tuned={tuned_drift}",
        )

    def test_adjacent_weekend_spacing_skips_when_understaffed(self):
        """Adjacent-weekend hard spacing is skipped when either day has only one candidate."""
        pref1 = DutyPreference.objects.get(member=self.member1)
        pref1.allow_weekend_double = False
        pref1.save()

        # Force member1 to be the only available member on two adjacent weekends.
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 7))
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 14))

        data = SchedulingData(
            members=[self.member1, self.member2],
            duty_days=[date(2026, 3, 7), date(2026, 3, 14)],
            roles=["instructor"],
            preferences={
                self.member1.id: pref1,
                self.member2.id: DutyPreference.objects.get(member=self.member2),
            },
            blackouts={
                (self.member2.id, date(2026, 3, 7)),
                (self.member2.id, date(2026, 3, 14)),
            },
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 7),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        assigned_member_ids = [
            day_schedule["slots"]["instructor"] for day_schedule in result["schedule"]
        ]
        self.assertEqual(assigned_member_ids, [self.member1.id, self.member1.id])

    def test_adjacent_weekend_spacing_sat_sun_skips_understaffed_saturday_pair(self):
        """Saturday adjacent-weekend hard spacing is skipped when Saturday staffing is single-candidate."""
        pref1 = DutyPreference.objects.get(member=self.member1)
        pref1.allow_weekend_double = False
        pref1.save()

        # Only member1 can cover Saturdays; member2 can still cover Sundays.
        # Without Saturday->next Saturday spacing, this would incorrectly be feasible.
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 7))
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 14))

        data = SchedulingData(
            members=[self.member1, self.member2],
            duty_days=[
                date(2026, 3, 7),
                date(2026, 3, 8),
                date(2026, 3, 14),
                date(2026, 3, 15),
            ],
            roles=["instructor"],
            preferences={
                self.member1.id: pref1,
                self.member2.id: DutyPreference.objects.get(member=self.member2),
            },
            blackouts={
                (self.member2.id, date(2026, 3, 7)),
                (self.member2.id, date(2026, 3, 14)),
            },
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 7),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        saturday_slots = [
            day_schedule["slots"]["instructor"]
            for day_schedule in result["schedule"]
            if day_schedule["date"] in {date(2026, 3, 7), date(2026, 3, 14)}
        ]
        self.assertEqual(saturday_slots, [self.member1.id, self.member1.id])

    def test_adjacent_weekend_spacing_missing_preference_skips_when_understaffed(self):
        """Missing preference defaults remain, but hard spacing is skipped for single-candidate slots."""
        # Force member1 to be the only available member on two adjacent weekends.
        # member1 is intentionally omitted from preferences to validate default behavior.
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 7))
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 14))

        data = SchedulingData(
            members=[self.member1, self.member2],
            duty_days=[date(2026, 3, 7), date(2026, 3, 14)],
            roles=["instructor"],
            preferences={
                self.member2.id: DutyPreference.objects.get(member=self.member2),
            },
            blackouts={
                (self.member2.id, date(2026, 3, 7)),
                (self.member2.id, date(2026, 3, 14)),
            },
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 7),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        assigned_member_ids = [
            day_schedule["slots"]["instructor"] for day_schedule in result["schedule"]
        ]
        self.assertEqual(assigned_member_ids, [self.member1.id, self.member1.id])

    def test_adjacent_weekend_spacing_enforced_when_two_candidates_exist(self):
        """Hard spacing should still apply when both adjacent slots have >=2 candidates."""
        pref1 = DutyPreference.objects.get(member=self.member1)
        pref1.allow_weekend_double = False
        pref1.save()

        pref2 = DutyPreference.objects.get(member=self.member2)
        pref2.allow_weekend_double = False
        pref2.save()

        data = SchedulingData(
            members=[self.member1, self.member2],
            duty_days=[date(2026, 3, 7), date(2026, 3, 14)],
            roles=["instructor"],
            preferences={
                self.member1.id: pref1,
                self.member2.id: pref2,
            },
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 7),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        assigned_member_ids = [
            day_schedule["slots"]["instructor"] for day_schedule in result["schedule"]
        ]
        self.assertNotEqual(assigned_member_ids[0], assigned_member_ids[1])

    def test_adjacent_weekend_hint_not_added_without_seven_day_weekday_pair(self):
        """Do not emit adjacent-weekend hint when no day has a matching day+7."""
        pref1 = DutyPreference.objects.get(member=self.member1)
        pref1.allow_weekend_double = False
        pref1.max_assignments_per_month = 1
        pref1.save()

        # Keep member2 unavailable so infeasibility is caused by assignment capacity,
        # not by adjacent-weekend spacing.
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 7))
        MemberBlackout.objects.create(member=self.member2, date=date(2026, 3, 15))

        data = SchedulingData(
            members=[self.member1, self.member2],
            duty_days=[date(2026, 3, 7), date(2026, 3, 15)],
            roles=["instructor"],
            preferences={
                self.member1.id: pref1,
                self.member2.id: DutyPreference.objects.get(member=self.member2),
            },
            blackouts={
                (self.member2.id, date(2026, 3, 7)),
                (self.member2.id, date(2026, 3, 15)),
            },
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=date(2026, 3, 7),
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertEqual(result["status"], "INFEASIBLE")
        self.assertNotIn(
            "Adjacent-weekend same-role spacing constraints may be too strict for available staffing.",
            result["diagnostics"]["infeasible_hints"],
        )


class ORToolsSoftConstraintsTests(TestCase):
    """Test soft constraints (objective function optimization)."""

    def setUp(self):
        """Create test data for soft constraint validation."""
        # Create members
        self.member1 = Member.objects.create(
            username="member1",
            email="m1@test.com",
            first_name="Member",
            last_name="One",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )

        self.member2 = Member.objects.create(
            username="member2",
            email="m2@test.com",
            first_name="Member",
            last_name="Two",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )

        self.test_dates = [date(2026, 3, 1), date(2026, 3, 8)]
        self.test_roles = ["instructor"]

    def test_preference_weighting(self):
        """Test that higher preferences are honored in objective function."""
        # member1 has 100% preference, member2 has 50%
        DutyPreference.objects.create(
            member=self.member1,
            instructor_percent=100,
            max_assignments_per_month=8,
        )
        DutyPreference.objects.create(
            member=self.member2,
            instructor_percent=50,
            max_assignments_per_month=8,
        )

        data = extract_scheduling_data(year=2026, month=3, roles=self.test_roles)
        scheduler = DutyRosterScheduler(data, enforce_adjacent_weekend_spacing=False)
        result = scheduler.solve(timeout_seconds=5.0)

        # Assert solver found a solution
        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))

        schedule = result["schedule"]
        member1_assignments = sum(
            1
            for day_schedule in schedule
            for member_id in day_schedule["slots"].values()
            if member_id == self.member1.id
        )
        member2_assignments = sum(
            1
            for day_schedule in schedule
            for member_id in day_schedule["slots"].values()
            if member_id == self.member2.id
        )

        # member1 (100%) should get more assignments than member2 (50%)
        # This is a soft constraint, so verify the objective favors higher preference
        self.assertGreater(member1_assignments, 0)
        self.assertGreaterEqual(
            member1_assignments,
            member2_assignments,
            "Member with 100% preference should get at least as many assignments as member with 50%",
        )

    def test_pairing_affinity(self):
        """Test that paired members are scheduled together when possible."""
        # Create two more members with complementary roles
        # We need multiple members per role to make the problem feasible
        instructor2 = Member.objects.create(
            username="instructor2",
            email="inst2@test.com",
            first_name="Instructor",
            last_name="Two",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )

        towpilot1 = Member.objects.create(
            username="towpilot1",
            email="tp1@test.com",
            first_name="Tow",
            last_name="Pilot1",
            membership_status="Full Member",
            towpilot=True,
            is_active=True,
        )

        towpilot2 = Member.objects.create(
            username="towpilot2",
            email="tp2@test.com",
            first_name="Tow",
            last_name="Pilot2",
            membership_status="Full Member",
            towpilot=True,
            is_active=True,
        )

        # Create preferences
        DutyPreference.objects.create(member=self.member1, max_assignments_per_month=8)
        DutyPreference.objects.create(member=instructor2, max_assignments_per_month=8)
        DutyPreference.objects.create(member=towpilot1, max_assignments_per_month=8)
        DutyPreference.objects.create(member=towpilot2, max_assignments_per_month=8)

        # Create pairing: member1 prefers to work with towpilot1
        DutyPairing.objects.create(member=self.member1, pair_with=towpilot1)

        data = extract_scheduling_data(
            year=2026, month=3, roles=["instructor", "towpilot"]
        )
        scheduler = DutyRosterScheduler(data, enforce_adjacent_weekend_spacing=False)
        result = scheduler.solve(timeout_seconds=5.0)

        # Assert solver found a solution
        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))

        # Verify pairing affinity is applied: member1 and towpilot1 should be
        # co-scheduled at least once (soft constraint, highly likely with pairing bonus)
        schedule = result["schedule"]
        days_paired = 0
        for day_schedule in schedule:
            slots = day_schedule["slots"]
            if (
                slots.get("instructor") == self.member1.id
                and slots.get("towpilot") == towpilot1.id
            ):
                days_paired += 1

        # With the pairing bonus, they should be scheduled together at least once
        self.assertGreater(
            days_paired,
            0,
            "Paired members should be co-scheduled at least once with pairing affinity bonus",
        )

    def test_last_duty_date_balancing(self):
        """Test that staleness (last_duty_date) is factored into objective."""
        # member1 hasn't worked recently, member2 worked yesterday
        old_date = date(2025, 1, 1)
        recent_date = date(2026, 2, 28)

        pref1 = DutyPreference.objects.create(
            member=self.member1,
            last_duty_date=old_date,
            max_assignments_per_month=8,
        )
        pref2 = DutyPreference.objects.create(
            member=self.member2,
            last_duty_date=recent_date,
            max_assignments_per_month=8,
        )

        data = extract_scheduling_data(year=2026, month=3, roles=self.test_roles)
        scheduler = DutyRosterScheduler(data, enforce_adjacent_weekend_spacing=False)
        result = scheduler.solve(timeout_seconds=5.0)

        # Assert solver found a solution
        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))

        # Verify staleness affects scheduling: member1 (staler) should get more
        # assignments than member2 (recent) due to last_duty_date weighting
        schedule = result["schedule"]
        member1_assignments = sum(
            1
            for day_schedule in schedule
            for member_id in day_schedule["slots"].values()
            if member_id == self.member1.id
        )
        member2_assignments = sum(
            1
            for day_schedule in schedule
            for member_id in day_schedule["slots"].values()
            if member_id == self.member2.id
        )

        # With staleness weighting, staler member should get more assignments
        self.assertGreater(
            member1_assignments,
            member2_assignments,
            "Staler member (older last_duty_date) should get more assignments",
        )

    def test_spacing_penalty_weights_prefer_wider_gaps(self):
        """Lag penalties should decrease as weekend gap width increases."""
        self.assertGreater(
            WEEKEND_SPACING_PENALTY_BY_LAG_WEEKS[1],
            WEEKEND_SPACING_PENALTY_BY_LAG_WEEKS[2],
        )
        self.assertGreater(
            WEEKEND_SPACING_PENALTY_BY_LAG_WEEKS[2],
            WEEKEND_SPACING_PENALTY_BY_LAG_WEEKS[3],
        )

    def test_spacing_prefers_three_week_gap_over_two_week_gap(self):
        """When both are feasible, objective should prefer 3-week repeat over 2-week."""
        member3 = Member.objects.create(
            username="member3",
            email="m3@test.com",
            first_name="Member",
            last_name="Three",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )

        anchor = date(2026, 3, 7)
        duty_days = [anchor + timedelta(days=7 * i) for i in range(5)]

        pref1 = DutyPreference.objects.create(
            member=self.member1,
            max_assignments_per_month=2,
            allow_weekend_double=True,
            last_duty_date=date(2026, 1, 1),
        )
        pref2 = DutyPreference.objects.create(
            member=self.member2,
            max_assignments_per_month=2,
            allow_weekend_double=True,
            last_duty_date=date(2026, 1, 1),
        )
        pref3 = DutyPreference.objects.create(
            member=member3,
            max_assignments_per_month=1,
            allow_weekend_double=True,
            last_duty_date=date(2026, 1, 1),
        )

        # day1 must be member1, day2/day5 must be member2.
        # The only flexible choice is whether member1 takes day3 (2-week gap)
        # or day4 (3-week gap) from day1.
        blackouts = {
            (self.member1.id, duty_days[1]),
            (self.member1.id, duty_days[4]),
            (self.member2.id, duty_days[0]),
            (self.member2.id, duty_days[2]),
            (self.member2.id, duty_days[3]),
            (member3.id, duty_days[0]),
            (member3.id, duty_days[1]),
            (member3.id, duty_days[4]),
        }

        data = SchedulingData(
            members=[self.member1, self.member2, member3],
            duty_days=duty_days,
            roles=["instructor"],
            preferences={
                self.member1.id: pref1,
                self.member2.id: pref2,
                member3.id: pref3,
            },
            blackouts=blackouts,
            avoidances=set(),
            pairings=set(),
            role_scarcity={"instructor": {"scarcity_score": 1.0}},
            earliest_duty_day=duty_days[0],
        )

        scheduler = DutyRosterScheduler(data)
        result = scheduler.solve(timeout_seconds=5.0)

        self.assertIn(result["status"], ("OPTIMAL", "FEASIBLE"))
        schedule_by_day = {
            day_schedule["date"]: day_schedule["slots"]["instructor"]
            for day_schedule in result["schedule"]
        }

        self.assertEqual(schedule_by_day[duty_days[0]], self.member1.id)
        self.assertEqual(schedule_by_day[duty_days[1]], self.member2.id)
        self.assertEqual(schedule_by_day[duty_days[4]], self.member2.id)

        # Core assertion: choose 3-week spacing for member1 (day1 -> day4),
        # not 2-week spacing (day1 -> day3).
        self.assertEqual(schedule_by_day[duty_days[3]], self.member1.id)
        self.assertEqual(schedule_by_day[duty_days[2]], member3.id)


class ORToolsEdgeCasesTests(TestCase):
    """Test edge cases and error handling."""

    def test_no_eligible_members_for_role(self):
        """Test handling when no members qualify for a role."""
        # Create member without any role flags
        member = Member.objects.create(
            username="member",
            email="m@test.com",
            first_name="Member",
            last_name="NoRoles",
            membership_status="Full Member",
            is_active=True,
        )

        # Try to schedule for a role nobody has - should raise RuntimeError
        with self.assertRaises(RuntimeError) as cm:
            generate_roster_ortools(
                year=2026, month=3, roles=["instructor"], timeout_seconds=2.0
            )

        # Expected behavior - verify error message contains stable fragment
        self.assertIn("no eligible members", str(cm.exception).lower())

    def test_all_members_blacked_out(self):
        """Test handling when all members are blacked out on a day."""
        member = Member.objects.create(
            username="member",
            email="m@test.com",
            first_name="Member",
            last_name="One",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )

        # Blackout on all March weekends
        march_weekends = [
            date(2026, 3, 1),
            date(2026, 3, 7),
            date(2026, 3, 8),
            date(2026, 3, 14),
            date(2026, 3, 15),
        ]
        for weekend_date in march_weekends:
            MemberBlackout.objects.create(member=member, date=weekend_date)

        # Solver should fail (infeasible)
        with self.assertRaises(RuntimeError):
            result = generate_roster_ortools(
                year=2026, month=3, roles=["instructor"], timeout_seconds=2.0
            )

    def test_empty_duty_days(self):
        """Test handling when no duty days in month (outside operational season)."""
        # Mock is_within_operational_season in the correct module
        with patch(
            "duty_roster.roster_generator.is_within_operational_season"
        ) as mock_season:
            mock_season.return_value = False

            data = extract_scheduling_data(year=2026, month=3, roles=["instructor"])

            # Should have zero duty days
            self.assertEqual(len(data.duty_days), 0)

    @patch("duty_roster.ortools_scheduler.DutyRosterScheduler")
    @patch("duty_roster.ortools_scheduler.extract_scheduling_data")
    def test_generate_roster_retries_relaxed_after_infeasible(
        self, mock_extract, mock_scheduler_cls
    ):
        """Strict infeasible solve should retry with relaxed repeat constraints."""
        mock_extract.return_value = SchedulingData(
            members=[],
            duty_days=[],
            roles=[],
            preferences={},
            blackouts=set(),
            avoidances=set(),
            pairings=set(),
            role_scarcity={},
            earliest_duty_day=date(2026, 4, 1),
        )

        strict_scheduler = MagicMock()
        relaxed_scheduler = MagicMock()
        mock_scheduler_cls.side_effect = [strict_scheduler, relaxed_scheduler]

        strict_scheduler.solve.return_value = {
            "status": "INFEASIBLE",
            "schedule": [],
            "diagnostics": {"infeasible_hints": []},
        }
        relaxed_scheduler.solve.return_value = {
            "status": "FEASIBLE",
            "schedule": [
                {
                    "date": date(2026, 4, 5),
                    "slots": {"instructor": 1},
                    "diagnostics": {"instructor": None},
                }
            ],
            "diagnostics": {"infeasible_hints": []},
        }

        schedule = generate_roster_ortools(year=2026, month=4, roles=["instructor"])

        self.assertEqual(len(schedule), 1)
        self.assertEqual(schedule[0]["slots"]["instructor"], 1)

        self.assertEqual(mock_scheduler_cls.call_count, 2)
        _, strict_kwargs = mock_scheduler_cls.call_args_list[0]
        _, relaxed_kwargs = mock_scheduler_cls.call_args_list[1]
        self.assertTrue(strict_kwargs.get("enforce_anti_repeat", True))
        self.assertTrue(strict_kwargs.get("enforce_adjacent_weekend_spacing", True))
        self.assertFalse(relaxed_kwargs.get("enforce_anti_repeat", True))
        self.assertFalse(relaxed_kwargs.get("enforce_adjacent_weekend_spacing", True))


class ORToolsIntegrationTests(TestCase):
    """Integration tests with Django ORM and legacy scheduler comparison."""

    def setUp(self):
        """Create realistic test data matching production scenario."""
        # Create 10 members with various role combinations
        self.members = []
        for i in range(10):
            member = Member.objects.create(
                username=f"member{i}",
                email=f"m{i}@test.com",
                first_name=f"Member{i}",
                last_name="Test",
                membership_status="Full Member",
                instructor=(i % 3 == 0),  # Every 3rd member
                towpilot=(i % 2 == 0),  # Every 2nd member
                duty_officer=(i % 4 == 0),  # Every 4th member
                assistant_duty_officer=True,  # All members
                is_active=True,
            )
            self.members.append(member)

            # Create preferences with varying percentages
            DutyPreference.objects.create(
                member=member,
                instructor_percent=100 if member.instructor else 0,
                towpilot_percent=100 if member.towpilot else 0,
                duty_officer_percent=100 if member.duty_officer else 0,
                ado_percent=100,
                max_assignments_per_month=8,
                last_duty_date=date(2026, 1, 1) + timedelta(days=i * 7),
            )

    def test_full_month_scheduling(self):
        """Test scheduling a full month with realistic data."""
        result = generate_roster_ortools(
            year=2026, month=3, roles=DEFAULT_ROLES, timeout_seconds=10.0
        )

        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        # Verify 100% slot fill
        for day_schedule in result:
            for role, member_id in day_schedule["slots"].items():
                self.assertIsNotNone(
                    member_id, f"Unfilled slot: {role} on {day_schedule['date']}"
                )

    def test_performance_benchmark(self):
        """Benchmark solve time for realistic problem size."""
        import time

        timeout_seconds = 10.0
        start_time = time.time()
        result = generate_roster_ortools(
            year=2026,
            month=3,
            roles=DEFAULT_ROLES,
            timeout_seconds=timeout_seconds,
        )
        solve_time = time.time() - start_time

        # Keep this as a regression guard that solver runtime should stay close
        # to configured timeout budget in CI environments.
        self.assertLess(
            solve_time,
            timeout_seconds + 2.0,
            f"Solver took {solve_time:.3f}s (budget: <{timeout_seconds + 2.0:.1f}s)",
        )
        self.assertGreater(len(result), 0)
        print(f"\nPerformance: Solved in {solve_time:.3f}s")


class ORToolsRegressionTests(TestCase):
    """Regression tests to ensure OR-Tools matches expected behavior."""

    def setUp(self):
        """Create minimal reproducible test case."""
        self.member1 = Member.objects.create(
            username="alice",
            email="alice@test.com",
            first_name="Alice",
            last_name="Test",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
            is_active=True,
        )

        self.member2 = Member.objects.create(
            username="bob",
            email="bob@test.com",
            first_name="Bob",
            last_name="Test",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
            duty_officer=True,
            assistant_duty_officer=True,
            is_active=True,
        )

        DutyPreference.objects.create(member=self.member1, max_assignments_per_month=8)
        DutyPreference.objects.create(member=self.member2, max_assignments_per_month=8)

    def test_deterministic_output(self):
        """Test that solver produces deterministic results for same input."""
        # Note: OR-Tools may not be perfectly deterministic, but should be consistent
        # with same random seed and single-threaded solving
        data1 = extract_scheduling_data(year=2026, month=3, roles=DEFAULT_ROLES)
        scheduler1 = DutyRosterScheduler(data1)
        scheduler1.solver.parameters.num_search_workers = 1  # Single-threaded
        scheduler1.solver.parameters.random_seed = 123  # Fixed seed for determinism
        result1 = scheduler1.solve(timeout_seconds=5.0)

        data2 = extract_scheduling_data(year=2026, month=3, roles=DEFAULT_ROLES)
        scheduler2 = DutyRosterScheduler(data2)
        scheduler2.solver.parameters.num_search_workers = 1  # Single-threaded
        scheduler2.solver.parameters.random_seed = 123  # Fixed seed for determinism
        result2 = scheduler2.solve(timeout_seconds=5.0)

        # Both should produce the same status
        self.assertEqual(result1["status"], result2["status"])

        # For FEASIBLE/OPTIMAL solutions, the schedule and objective should be identical
        if result1["status"] in {"FEASIBLE", "OPTIMAL"}:
            self.assertEqual(
                result1.get("objective_value"),
                result2.get("objective_value"),
            )
            # Schedules should also be identical (same assignments)
            self.assertEqual(len(result1["schedule"]), len(result2["schedule"]))
            for day1, day2 in zip(result1["schedule"], result2["schedule"]):
                self.assertEqual(day1["date"], day2["date"])
                self.assertEqual(day1["slots"], day2["slots"])


class ORToolsDynamicRoleSupportTests(TestCase):
    """Ensure OR-Tools scheduler supports dynamic role keys."""

    def setUp(self):
        self.site_config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="test.example.com",
            club_abbreviation="TSC",
            enable_dynamic_duty_roles=True,
            use_ortools_scheduler=True,
        )

        DutyRoleDefinition.objects.create(
            site_configuration=self.site_config,
            key="am_tow",
            display_name="AM Tow",
            legacy_role_key="towpilot",
            shift_code="am",
            is_active=True,
            sort_order=10,
        )

        self.member1 = Member.objects.create(
            username="dynamic_tow_1",
            email="dynamic_tow_1@test.com",
            first_name="Dynamic",
            last_name="TowOne",
            membership_status="Full Member",
            towpilot=True,
            is_active=True,
        )
        self.member2 = Member.objects.create(
            username="dynamic_tow_2",
            email="dynamic_tow_2@test.com",
            first_name="Dynamic",
            last_name="TowTwo",
            membership_status="Full Member",
            towpilot=True,
            is_active=True,
        )

        DutyPreference.objects.create(member=self.member1, max_assignments_per_month=8)
        DutyPreference.objects.create(member=self.member2, max_assignments_per_month=8)

    @patch("duty_roster.roster_generator.is_within_operational_season")
    def test_extract_data_maps_dynamic_role_to_legacy_percent_basis(
        self, mock_in_season
    ):
        mock_in_season.return_value = True
        data = extract_scheduling_data(year=2026, month=4, roles=["am_tow"])

        self.assertEqual(data.role_percent_basis["am_tow"], "towpilot")
        self.assertIn("am_tow", data.role_eligible_member_ids)
        self.assertIn(self.member1.id, data.role_eligible_member_ids["am_tow"])
        self.assertIn(self.member2.id, data.role_eligible_member_ids["am_tow"])
        self.assertEqual(data.role_scarcity["am_tow"]["total_members"], 2)

    @patch("duty_roster.roster_generator.is_within_operational_season")
    def test_generate_roster_ortools_fills_dynamic_tow_slots(self, mock_in_season):
        mock_in_season.return_value = True

        schedule = generate_roster_ortools(
            start_date=date(2026, 4, 4),
            end_date=date(2026, 4, 5),
            roles=["am_tow"],
            timeout_seconds=5.0,
        )

        self.assertGreater(len(schedule), 0)
        for day_schedule in schedule:
            assigned_member_id = day_schedule["slots"].get("am_tow")
            self.assertIn(assigned_member_id, {self.member1.id, self.member2.id})

    def test_dynamic_subset_respects_explicit_zero_percent_preference(self):
        member = Member.objects.create(
            username="dynamic_tow_with_other_capability",
            email="dynamic_tow_with_other_capability@test.com",
            first_name="Dynamic",
            last_name="TowInstructor",
            membership_status="Full Member",
            towpilot=True,
            instructor=True,
            is_active=True,
        )
        pref = DutyPreference.objects.create(
            member=member,
            towpilot_percent=0,
            instructor_percent=100,
            max_assignments_per_month=8,
        )

        data = extract_scheduling_data(year=2026, month=4, roles=["am_tow"])
        scheduler = DutyRosterScheduler(data)

        self.assertFalse(scheduler._is_role_allowed(member, "am_tow", pref))
        self.assertEqual(scheduler._calculate_preference_weight(member, "am_tow"), 0)
