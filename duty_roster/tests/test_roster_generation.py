"""
Unit tests for roster generation with smart prioritization and diagnostics.

Tests for Issue #616: Roster generation improvements including default eligibility,
role scarcity prioritization, and diagnostic output.
"""

from collections import defaultdict
from datetime import date, timedelta

import pytest

from duty_roster.models import DutyPreference, MemberBlackout
from duty_roster.roster_generator import (
    calculate_role_scarcity,
    diagnose_empty_slot,
    generate_roster,
)
from members.models import Member


@pytest.mark.django_db
class TestRosterGenerationDefaults:
    """Test that members without DutyPreference are treated as eligible."""

    def test_member_without_preference_is_eligible(self):
        """Members with no DutyPreference should be eligible with default constraints."""
        # Create only one member with role flag but no preference (deterministic test)
        Member.objects.create(
            username="nopref",
            email="nopref@test.com",
            first_name="No",
            last_name="Pref",
            instructor=True,
            is_active=True,
            membership_status="Full Member",
            joined_club=date.today() - timedelta(days=365),
        )

        # Generate roster for current month with only instructor role
        roster = generate_roster(roles=["instructor"])

        # Verify roster was generated and member appears in assignments
        assert roster is not None
        assert len(roster) > 0

        # Count how many instructor slots are filled
        filled_slots = sum(
            1 for day in roster if day.get("slots", {}).get("instructor")
        )
        # With only one eligible instructor and no preference restrictions,
        # at least some slots should be filled (not zero)
        assert (
            filled_slots > 0
        ), "Member without DutyPreference should be assigned to instructor slots"

    def test_member_without_preference_respects_blackouts(self):
        """Members without preference should still respect blackouts."""
        member = Member.objects.create(
            username="blackout_test",
            email="blackout@test.com",
            first_name="Black",
            last_name="Out",
            towpilot=True,
            is_active=True,
        )

        # Add blackout for today
        today = date.today()
        MemberBlackout.objects.create(member=member, date=today)

        # Generate roster
        roster = generate_roster(roles=["towpilot"])

        # Find today's entry
        today_entry = None
        for entry in roster:
            if entry["date"] == today:
                today_entry = entry
                break

        # If today is operational, verify member isn't assigned
        if today_entry:
            assert (
                today_entry["slots"].get("towpilot") != member.id
            ), "Blacked-out member should not be assigned"


@pytest.mark.django_db
class TestRoleScarcity:
    """Test role scarcity calculation for prioritization."""

    def test_calculate_role_scarcity_basic(self):
        """Role scarcity should prioritize roles with fewer available members."""
        # Create members with different role flags
        Member.objects.create(
            username="inst1",
            email="inst1@test.com",
            first_name="I",
            last_name="One",
            instructor=True,
            is_active=True,
        )
        Member.objects.create(
            username="inst2",
            email="inst2@test.com",
            first_name="I",
            last_name="Two",
            instructor=True,
            is_active=True,
        )
        Member.objects.create(
            username="tow1",
            email="tow1@test.com",
            first_name="T",
            last_name="One",
            towpilot=True,
            is_active=True,
        )

        members = Member.objects.filter(is_active=True)
        prefs = {}
        blackouts = set()

        today = date.today()
        operational_dates = [today + timedelta(days=i) for i in range(7)]

        # Calculate scarcity for towpilot role
        scarcity = calculate_role_scarcity(
            members, prefs, blackouts, operational_dates, "towpilot"
        )

        # Towpilot should show scarcity data
        assert "scarcity_score" in scarcity
        assert "total_members" in scarcity
        assert scarcity["total_members"] == 1  # Only one towpilot

        # Calculate scarcity for instructor role
        scarcity_instructor = calculate_role_scarcity(
            members, prefs, blackouts, operational_dates, "instructor"
        )

        # Instructor should have more members available
        assert scarcity_instructor["total_members"] == 2  # Two instructors


@pytest.mark.django_db
class TestDiagnostics:
    """Test diagnostic output for empty slots."""

    def test_diagnose_empty_slot_basic(self):
        """Diagnostics should identify why slots can't be filled."""
        member = Member.objects.create(
            username="diag_test",
            email="diag@test.com",
            first_name="Diag",
            last_name="Test",
            duty_officer=True,
            is_active=True,
        )

        # Create preference with dont_schedule=True
        DutyPreference.objects.create(member=member, dont_schedule=True)

        members = Member.objects.filter(is_active=True)
        prefs = {m.id: DutyPreference.objects.filter(member=m).first() for m in members}
        blackouts = set()
        avoidances = set()
        assignments = defaultdict(int)
        assigned_today = set()

        diagnostic = diagnose_empty_slot(
            "duty_officer",
            date.today(),
            members,
            prefs,
            blackouts,
            avoidances,
            assignments,
            assigned_today,
        )

        assert "reasons" in diagnostic
        assert "summary" in diagnostic
        assert "dont_schedule" in diagnostic["reasons"]
        assert len(diagnostic["reasons"]["dont_schedule"]) > 0

    def test_diagnose_empty_slot_with_anti_repeat(self):
        """Diagnostics should track anti-repeat constraint."""
        member = Member.objects.create(
            username="repeat_test",
            email="repeat@test.com",
            first_name="Repeat",
            last_name="Test",
            instructor=True,
            is_active=True,
        )

        members = Member.objects.filter(is_active=True)
        prefs = {}
        blackouts = set()
        avoidances = set()
        assignments = defaultdict(int)
        assigned_today = set()
        last_assigned = {"instructor": member.id}

        diagnostic = diagnose_empty_slot(
            "instructor",
            date.today(),
            members,
            prefs,
            blackouts,
            avoidances,
            assignments,
            assigned_today,
            last_assigned,
        )

        assert "assigned_yesterday" in diagnostic["reasons"]
        assert len(diagnostic["reasons"]["assigned_yesterday"]) > 0


@pytest.mark.django_db
class TestRosterGeneration:
    """Test full roster generation with new features."""

    def test_generate_roster_returns_diagnostics(self):
        """Generated roster should include diagnostics for each day."""
        # Create basic member with role
        Member.objects.create(
            username="gen_test",
            email="gen@test.com",
            first_name="Gen",
            last_name="Test",
            instructor=True,
            towpilot=True,
            is_active=True,
        )

        roster = generate_roster(roles=["instructor", "towpilot"])

        assert roster is not None
        assert len(roster) > 0

        # Each entry should have diagnostics
        for entry in roster:
            assert "date" in entry
            assert "slots" in entry
            assert "diagnostics" in entry
            assert isinstance(entry["diagnostics"], dict)
