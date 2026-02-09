"""
Tests for Issue #618: Roll Again should remember which dates have been removed.

Verifies that when a user removes dates from a proposed roster, those dates
stay removed when clicking Roll Again, and can be restored with Restore All Dates.
"""

from datetime import date

import pytest
from django.urls import reverse

from duty_roster.roster_generator import clear_operational_season_cache, generate_roster
from logsheet.models import Airfield
from members.models import Member


@pytest.mark.django_db
class TestGenerateRosterExcludeDates:
    """Test that generate_roster respects the exclude_dates parameter."""

    @pytest.fixture(autouse=True)
    def setup_operational_season(self):
        """Clear cache for reliable testing - missing SiteConfiguration defaults to year-round."""
        clear_operational_season_cache()
        yield
        clear_operational_season_cache()

    def test_exclude_dates_removes_dates_from_output(self):
        """Dates in exclude_dates should not appear in generated roster."""
        Member.objects.create(
            username="test_exc",
            email="test@test.com",
            first_name="Test",
            last_name="Exclude",
            instructor=True,
            is_active=True,
            membership_status="Full Member",
            joined_club=date.today(),
        )

        # Generate full roster for a known month with predictable weekends
        full_roster = generate_roster(year=2026, month=3, roles=["instructor"])
        assert full_roster and len(full_roster) > 0

        # Pick the first date to exclude
        date_to_exclude = full_roster[0]["date"]

        # Regenerate with that date excluded
        filtered_roster = generate_roster(
            year=2026, month=3, roles=["instructor"], exclude_dates=[date_to_exclude]
        )

        # The excluded date should not be in the filtered roster
        filtered_dates = [entry["date"] for entry in filtered_roster]
        assert date_to_exclude not in filtered_dates

        # The filtered roster should be shorter
        assert len(filtered_roster) == len(full_roster) - 1

    def test_exclude_multiple_dates(self):
        """Multiple dates can be excluded at once."""
        Member.objects.create(
            username="test_multi",
            email="multi@test.com",
            first_name="Multi",
            last_name="Test",
            instructor=True,
            is_active=True,
            membership_status="Full Member",
            joined_club=date.today(),
        )

        full_roster = generate_roster(year=2026, month=3, roles=["instructor"])
        assert len(full_roster) >= 2

        dates_to_exclude = [full_roster[0]["date"], full_roster[1]["date"]]
        filtered_roster = generate_roster(
            year=2026, month=3, roles=["instructor"], exclude_dates=dates_to_exclude
        )

        filtered_dates = [entry["date"] for entry in filtered_roster]
        for d in dates_to_exclude:
            assert d not in filtered_dates

        assert len(filtered_roster) == len(full_roster) - 2

    def test_exclude_dates_none_is_noop(self):
        """Passing None for exclude_dates should produce same result as omitting it."""
        Member.objects.create(
            username="test_none",
            email="none@test.com",
            first_name="None",
            last_name="Test",
            instructor=True,
            is_active=True,
            membership_status="Full Member",
            joined_club=date.today(),
        )

        roster_default = generate_roster(year=2026, month=3, roles=["instructor"])
        roster_none = generate_roster(
            year=2026, month=3, roles=["instructor"], exclude_dates=None
        )

        assert len(roster_default) == len(roster_none)

    def test_exclude_dates_empty_list_is_noop(self):
        """Passing empty list for exclude_dates should produce same result."""
        Member.objects.create(
            username="test_empty",
            email="empty@test.com",
            first_name="Empty",
            last_name="Test",
            instructor=True,
            is_active=True,
            membership_status="Full Member",
            joined_club=date.today(),
        )

        roster_default = generate_roster(year=2026, month=3, roles=["instructor"])
        roster_empty = generate_roster(
            year=2026, month=3, roles=["instructor"], exclude_dates=[]
        )

        assert len(roster_default) == len(roster_empty)


@pytest.mark.django_db
class TestProposeRosterSessionTracking:
    """Test the propose_roster view tracks removed dates in the session."""

    @pytest.fixture
    def airfield(self):
        """Create a default airfield for publishing."""
        return Airfield.objects.create(
            id=1,
            name="Test Field",
            identifier="TEST",
        )

    @pytest.fixture
    def rostermeister(self):
        """Create a user with rostermeister permissions."""
        user = Member.objects.create_user(
            username="rostermeister",
            email="rm@test.com",
            password="testpass123",
            first_name="Roster",
            last_name="Meister",
            is_active=True,
            membership_status="Full Member",
            joined_club=date.today(),
        )
        user.rostermeister = True
        user.save()
        return user

    @pytest.fixture
    def instructor_member(self):
        """Create a member eligible for instructor role."""
        return Member.objects.create(
            username="test_instructor",
            email="instructor@test.com",
            first_name="Test",
            last_name="Instructor",
            instructor=True,
            is_active=True,
            membership_status="Full Member",
            joined_club=date.today(),
        )

    def test_remove_dates_stores_in_session(
        self, client, rostermeister, instructor_member
    ):
        """Removing dates should store them in session for Roll Again."""
        client.login(username="rostermeister", password="testpass123")
        url = reverse("duty_roster:propose_roster")

        # First, do a GET for any initial session setup
        resp = client.get(url, {"year": 2026, "month": 3})
        assert resp.status_code == 200

        # Seed the session with a deterministic proposed roster entry
        session = client.session
        session["proposed_roster"] = [{"date": "2026-03-07", "slots": {}}]
        session.save()
        date_to_remove = session["proposed_roster"][0]["date"]

        # POST to remove that date
        client.post(
            url,
            {
                "year": 2026,
                "month": 3,
                "action": "remove_dates",
                "remove_date": [date_to_remove],
            },
        )

        # Check session has the removed date tracked (scoped to 2026-03)
        session = client.session
        removed_key = "removed_roster_dates_2026_03"
        removed = session.get(removed_key, [])
        assert date_to_remove in removed

    def test_cancel_clears_removed_dates(self, client, rostermeister):
        """Cancelling should clear both proposed roster and removed dates."""
        client.login(username="rostermeister", password="testpass123")
        url = reverse("duty_roster:propose_roster")

        # First do a GET to establish the session
        client.get(url, {"year": 2026, "month": 3})

        # Set up session data
        session = client.session
        session["proposed_roster"] = [{"date": "2026-03-07", "slots": {}}]
        removed_key = "removed_roster_dates_2026_03"
        session[removed_key] = ["2026-03-01"]
        session.save()

        # Cancel
        client.post(
            url,
            {"year": 2026, "month": 3, "action": "cancel"},
        )

        session = client.session
        assert "proposed_roster" not in session
        assert removed_key not in session

    def test_restore_dates_clears_removed_dates(self, client, rostermeister):
        """Restore All Dates should clear the removed dates list."""
        client.login(username="rostermeister", password="testpass123")
        url = reverse("duty_roster:propose_roster")

        # First do a GET to establish the session
        client.get(url, {"year": 2026, "month": 3})

        # Set up session data
        session = client.session
        session["proposed_roster"] = [
            {"date": "2026-03-07", "slots": {}, "diagnostics": {}}
        ]
        removed_key = "removed_roster_dates_2026_03"
        session[removed_key] = ["2026-03-01"]
        session.save()

        # Restore dates
        client.post(
            url,
            {"year": 2026, "month": 3, "action": "restore_dates"},
        )

        session = client.session
        assert removed_key not in session

    def test_roll_again_respects_removed_dates(
        self, client, rostermeister, instructor_member
    ):
        """Integration test: removed dates stay removed when clicking Roll Again (Issue #618)."""
        client.login(username="rostermeister", password="testpass123")
        url = reverse("duty_roster:propose_roster")

        # Generate initial roster
        resp = client.get(url, {"year": 2026, "month": 3})
        assert resp.status_code == 200

        # Verify we got a roster
        session = client.session
        proposed = session.get("proposed_roster", [])
        assert len(proposed) >= 2, (
            f"Expected at least 2 dates in proposed_roster for this test, "
            f"got {len(proposed)}. This likely indicates an issue with roster "
            "generation or operational-season configuration."
        )

        date_to_remove = proposed[0]["date"]

        # Remove one date
        client.post(
            url,
            {
                "year": 2026,
                "month": 3,
                "action": "remove_dates",
                "remove_date": [date_to_remove],
            },
        )

        # Verify date was removed
        session = client.session
        proposed_after_remove = session.get("proposed_roster", [])
        dates_after_remove = {e["date"] for e in proposed_after_remove}
        assert date_to_remove not in dates_after_remove

        # Now click "Roll Again"
        client.post(
            url,
            {"year": 2026, "month": 3, "action": "roll"},
        )

        # Verify the removed date did NOT reappear
        session = client.session
        proposed_after_roll = session.get("proposed_roster", [])
        dates_after_roll = {e["date"] for e in proposed_after_roll}
        assert (
            date_to_remove not in dates_after_roll
        ), f"Date {date_to_remove} should still be excluded after Roll Again"

    def test_publish_clears_removed_dates(self, client, rostermeister, airfield):
        """Publishing roster should clear both proposed roster and removed dates."""
        client.login(username="rostermeister", password="testpass123")
        url = reverse("duty_roster:propose_roster")

        # First do a GET to establish the session
        client.get(url, {"year": 2026, "month": 3})

        # Set up session data
        session = client.session
        session["proposed_roster"] = [{"date": "2026-03-07", "slots": {}}]
        removed_key = "removed_roster_dates_2026_03"
        session[removed_key] = ["2026-03-01"]
        session.save()

        # Publish (this will redirect)
        response = client.post(
            url,
            {"year": 2026, "month": 3, "action": "publish"},
        )

        # Verify redirect
        assert response.status_code == 302

        # Verify session was cleaned up
        session = client.session
        assert "proposed_roster" not in session
        assert removed_key not in session
