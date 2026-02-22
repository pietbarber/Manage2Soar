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
from unittest.mock import patch

from django.test import TestCase

from duty_roster.models import (
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    MemberBlackout,
)
from duty_roster.ortools_scheduler import (
    DutyRosterScheduler,
    SchedulingData,
    extract_scheduling_data,
    generate_roster_ortools,
)
from members.constants.membership import DEFAULT_ROLES
from members.models import Member


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

        scheduler = DutyRosterScheduler(data)
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
        scheduler = DutyRosterScheduler(data)
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
        scheduler = DutyRosterScheduler(data)
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
        scheduler = DutyRosterScheduler(data)
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

        start_time = time.time()
        result = generate_roster_ortools(
            year=2026, month=3, roles=DEFAULT_ROLES, timeout_seconds=10.0
        )
        solve_time = time.time() - start_time

        # Should solve in < 1 second (target from Phase 1 findings)
        self.assertLess(solve_time, 1.0, f"Solver took {solve_time:.3f}s (target: <1s)")
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
