"""
Tests for the maintenance log view (Issue #537).

The maintenance_log view shows a complete history of all maintenance issues
(both open and resolved), with filtering by aircraft type.
"""

import pytest
from django.urls import reverse

from logsheet.models import MaintenanceIssue, Towplane


@pytest.mark.django_db
class TestMaintenanceLogView:
    """Tests for the maintenance_log view."""

    def test_view_requires_authentication(self, client):
        """Unauthenticated users should be redirected to login."""
        response = client.get(reverse("logsheet:maintenance_log"))
        assert response.status_code == 302
        assert "/login/" in response.url or "/accounts/login/" in response.url

    def test_view_accessible_by_active_member(self, client, active_member):
        """Active members should be able to access the maintenance log."""
        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_log"))
        assert response.status_code == 200

    def test_context_contains_expected_data(self, client, active_member):
        """View should provide all expected context variables."""
        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_log"))

        assert "issues" in response.context
        assert "gliders" in response.context
        assert "towplanes" in response.context
        assert "total_issues" in response.context
        assert "open_issues_count" in response.context
        assert "resolved_issues_count" in response.context
        assert "grounded_count" in response.context

    def test_shows_both_open_and_resolved_issues(
        self, client, active_member, glider_for_meister
    ):
        """View should show both open and resolved maintenance issues."""
        # Create an open issue
        MaintenanceIssue.objects.create(
            description="Open brake issue",
            glider=glider_for_meister,
            resolved=False,
        )
        # Create a resolved issue
        MaintenanceIssue.objects.create(
            description="Resolved canopy issue",
            glider=glider_for_meister,
            resolved=True,
            resolution_notes="Fixed the latch",
        )

        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_log"))

        issues = list(response.context["issues"])
        assert len(issues) == 2
        assert any(i.description == "Open brake issue" for i in issues)
        assert any(i.description == "Resolved canopy issue" for i in issues)

    def test_filter_by_glider(self, client, active_member, glider_for_meister):
        """View should filter by glider when aircraft_type=glider."""
        # Create a glider issue
        MaintenanceIssue.objects.create(
            description="Glider wheel issue",
            glider=glider_for_meister,
            resolved=False,
        )
        # Create a towplane issue
        towplane = Towplane.objects.create(
            n_number="N123TP", club_owned=True, is_active=True
        )
        MaintenanceIssue.objects.create(
            description="Towplane engine issue",
            towplane=towplane,
            resolved=False,
        )

        client.force_login(active_member)
        response = client.get(
            reverse("logsheet:maintenance_log"),
            {"type": "glider", "aircraft_id": glider_for_meister.pk},
        )

        issues = list(response.context["issues"])
        assert len(issues) == 1
        assert issues[0].description == "Glider wheel issue"

    def test_filter_by_towplane(self, client, active_member, glider_for_meister):
        """View should filter by towplane when aircraft_type=towplane."""
        # Create a glider issue
        MaintenanceIssue.objects.create(
            description="Glider wheel issue",
            glider=glider_for_meister,
            resolved=False,
        )
        # Create a towplane issue
        towplane = Towplane.objects.create(
            n_number="N123TP", club_owned=True, is_active=True
        )
        towplane_issue = MaintenanceIssue.objects.create(
            description="Towplane engine issue",
            towplane=towplane,
            resolved=False,
        )

        client.force_login(active_member)
        response = client.get(
            reverse("logsheet:maintenance_log"),
            {"type": "towplane", "aircraft_id": towplane.pk},
        )

        issues = list(response.context["issues"])
        assert len(issues) == 1
        assert issues[0].description == "Towplane engine issue"

    def test_statistics_counts_are_correct(
        self, client, active_member, glider_for_meister
    ):
        """View should correctly count total, open, resolved, and grounded issues."""
        # Create various issues
        MaintenanceIssue.objects.create(
            description="Open issue 1",
            glider=glider_for_meister,
            resolved=False,
            grounded=False,
        )
        MaintenanceIssue.objects.create(
            description="Open grounded issue",
            glider=glider_for_meister,
            resolved=False,
            grounded=True,
        )
        MaintenanceIssue.objects.create(
            description="Resolved issue",
            glider=glider_for_meister,
            resolved=True,
            grounded=False,
            resolution_notes="Fixed",
        )

        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_log"))

        assert response.context["total_issues"] == 3
        assert response.context["open_issues_count"] == 2
        assert response.context["resolved_issues_count"] == 1
        assert response.context["grounded_count"] == 1

    def test_issues_ordered_by_report_date_descending(
        self, client, active_member, glider_for_meister
    ):
        """Issues should be ordered with newest first."""
        from datetime import date, timedelta

        older_issue = MaintenanceIssue.objects.create(
            description="Older issue",
            glider=glider_for_meister,
            resolved=False,
        )
        older_issue.report_date = date.today() - timedelta(days=7)
        older_issue.save()

        MaintenanceIssue.objects.create(
            description="Newer issue",
            glider=glider_for_meister,
            resolved=False,
        )

        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_log"))

        issues = list(response.context["issues"])
        assert issues[0].description == "Newer issue"
        assert issues[1].description == "Older issue"

    def test_template_used(self, client, active_member):
        """View should use the correct template."""
        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_log"))
        assert "logsheet/maintenance_log.html" in [t.name for t in response.templates]

    def test_no_issues_displays_empty_state(self, client, active_member):
        """View should handle case with no maintenance issues."""
        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_log"))

        assert response.status_code == 200
        assert response.context["total_issues"] == 0
        assert b"No maintenance issues" in response.content

    def test_link_from_maintenance_list(self, client, active_member):
        """The maintenance list page should have a link to the full log."""
        client.force_login(active_member)
        response = client.get(reverse("logsheet:maintenance_issues"))

        assert response.status_code == 200
        assert b"maintenance/log" in response.content

    def test_invalid_aircraft_id_handling(
        self, client, active_member, glider_for_meister
    ):
        """View should handle invalid aircraft_id gracefully."""
        # Create a test issue
        MaintenanceIssue.objects.create(
            description="Test issue",
            glider=glider_for_meister,
            resolved=False,
        )

        client.force_login(active_member)

        # Test with non-numeric aircraft_id
        response = client.get(
            reverse("logsheet:maintenance_log"),
            {"type": "glider", "aircraft_id": "invalid"},
        )
        assert response.status_code == 200
        # Should show all issues since filter was ignored
        issues = list(response.context["issues"])
        assert len(issues) == 1

        # Test with empty aircraft_id
        response = client.get(
            reverse("logsheet:maintenance_log"),
            {"type": "glider", "aircraft_id": ""},
        )
        assert response.status_code == 200
        # Should show all issues since no filter applied
        issues = list(response.context["issues"])
        assert len(issues) == 1

    def test_invalid_aircraft_id_handling(
        self, client, active_member, glider_for_meister
    ):
        """View should handle invalid aircraft_id gracefully."""
        # Create a test issue
        MaintenanceIssue.objects.create(
            description="Test issue",
            glider=glider_for_meister,
            resolved=False,
        )

        client.force_login(active_member)

        # Test with non-numeric aircraft_id
        response = client.get(
            reverse("logsheet:maintenance_log"),
            {"type": "glider", "aircraft_id": "invalid"},
        )
        assert response.status_code == 200
        # Should show all issues since filter was ignored
        issues = list(response.context["issues"])
        assert len(issues) == 1

        # Test with empty aircraft_id
        response = client.get(
            reverse("logsheet:maintenance_log"),
            {"type": "glider", "aircraft_id": ""},
        )
        assert response.status_code == 200
        # Should show all issues since no filter applied
        issues = list(response.context["issues"])
        assert len(issues) == 1
