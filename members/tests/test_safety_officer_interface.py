"""Tests for Safety Officer Interface.

Tests for Issue #585 - Safety Officer Interface for viewing safety reports.
"""

from unittest.mock import patch

import pytest
from django.urls import reverse

from members.models import Member, SafetyReport


@pytest.fixture
def safety_officer(db):
    """Create a safety officer member."""
    return Member.objects.create_user(
        username="safety_officer",
        email="safety@example.com",
        password="testpass123",
        first_name="Safety",
        last_name="Officer",
        safety_officer=True,
        membership_status="Full Member",
    )


@pytest.fixture
def regular_member(db):
    """Create a regular member who is not a safety officer."""
    return Member.objects.create_user(
        username="regular_member",
        email="regular@example.com",
        password="testpass123",
        first_name="Regular",
        last_name="Member",
        safety_officer=False,
        membership_status="Full Member",
    )


@pytest.fixture
def superuser(db):
    """Create a superuser."""
    return Member.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="testpass123",
        first_name="Admin",
        last_name="User",
    )


@pytest.fixture
def safety_report(db, regular_member):
    """Create a sample safety report."""
    return SafetyReport.objects.create(
        reporter=regular_member,
        is_anonymous=False,
        observation="<p>I noticed a safety concern near the runway.</p>",
        observation_date="2026-01-15",
        location="Runway approach",
        status="new",
    )


@pytest.fixture
def anonymous_report(db):
    """Create an anonymous safety report."""
    return SafetyReport.objects.create(
        reporter=None,
        is_anonymous=True,
        observation="<p>There was an unsafe condition observed.</p>",
        location="Tie-down area",
        status="new",
    )


class TestSafetyOfficerRequired:
    """Tests for the safety_officer_required decorator."""

    def test_unauthenticated_redirects_to_login(self, client, db):
        """Unauthenticated users should be redirected to login."""
        url = reverse("members:safety_report_list")
        response = client.get(url)
        assert response.status_code == 302
        assert "login" in response.url.lower() or response.url == reverse("login")

    def test_regular_member_gets_403(self, client, regular_member):
        """Regular members should get 403 Forbidden."""
        client.login(username="regular_member", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url)
        assert response.status_code == 403

    def test_safety_officer_has_access(self, client, safety_officer):
        """Safety officers should have access."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url)
        assert response.status_code == 200

    def test_superuser_has_access(self, client, superuser):
        """Superusers should have access."""
        client.login(username="admin", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url)
        assert response.status_code == 200

    def test_inactive_safety_officer_gets_403(self, client, db):
        """Safety officer with inactive membership status should get 403 Forbidden."""
        # Create safety officer with Full Member status
        inactive_officer = Member.objects.create_user(
            username="inactive_officer",
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
            safety_officer=True,
        )

        # Login
        client.force_login(inactive_officer)

        # Mock is_active_member to return False (simulating inactive membership)
        with patch("members.decorators.is_active_member", return_value=False):
            url = reverse("members:safety_report_list")
            response = client.get(url)
            assert response.status_code == 403


class TestSafetyReportListView:
    """Tests for the safety report list view."""

    def test_list_view_shows_reports(self, client, safety_officer, safety_report):
        """Safety officer can see reports in list view."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Safety Reports Dashboard" in response.content
        assert b"Runway approach" in response.content

    def test_list_view_shows_statistics(self, client, safety_officer, safety_report):
        """List view displays report statistics."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url)
        assert response.status_code == 200
        assert "stats" in response.context

    def test_filter_by_status(self, client, safety_officer, safety_report):
        """Can filter reports by status."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url, {"status": "new"})
        assert response.status_code == 200
        # Should contain the report (status is 'new')
        assert safety_report in response.context["page_obj"].object_list

    def test_filter_excludes_other_statuses(
        self, client, safety_officer, safety_report
    ):
        """Filtering excludes reports with other statuses."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url, {"status": "resolved"})
        assert response.status_code == 200
        # Should not contain the report (status is 'new')
        assert safety_report not in response.context["page_obj"].object_list

    def test_anonymous_report_shows_anonymous_badge(
        self, client, safety_officer, anonymous_report
    ):
        """Anonymous reports display 'Anonymous' badge."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_list")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Anonymous" in response.content


class TestSafetyReportDetailView:
    """Tests for the safety report detail view."""

    def test_detail_view_shows_report(self, client, safety_officer, safety_report):
        """Safety officer can view report details."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_detail", args=[safety_report.pk])
        response = client.get(url)
        assert response.status_code == 200
        assert b"safety concern near the runway" in response.content

    def test_detail_view_regular_member_403(
        self, client, regular_member, safety_report
    ):
        """Regular members cannot view report details."""
        client.login(username="regular_member", password="testpass123")
        url = reverse("members:safety_report_detail", args=[safety_report.pk])
        response = client.get(url)
        assert response.status_code == 403

    def test_can_update_status(self, client, safety_officer, safety_report):
        """Safety officer can update report status."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_detail", args=[safety_report.pk])
        response = client.post(
            url,
            {
                "status": "reviewed",
                "officer_notes": "Reviewed this report",
                "actions_taken": "",
            },
        )
        assert response.status_code == 302  # Redirect after success
        safety_report.refresh_from_db()
        assert safety_report.status == "reviewed"
        assert safety_report.reviewed_by == safety_officer

    def test_can_add_officer_notes(self, client, safety_officer, safety_report):
        """Safety officer can add internal notes."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_detail", args=[safety_report.pk])
        response = client.post(
            url,
            {
                "status": "in_progress",
                "officer_notes": "<p>Need to investigate further.</p>",
                "actions_taken": "",
            },
        )
        assert response.status_code == 302
        safety_report.refresh_from_db()
        assert "investigate further" in safety_report.officer_notes

    def test_anonymous_report_hides_reporter(
        self, client, safety_officer, anonymous_report
    ):
        """Anonymous reports don't show reporter identity."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_detail", args=[anonymous_report.pk])
        response = client.get(url)
        assert response.status_code == 200
        assert b"Anonymous" in response.content

    def test_nonexistent_report_404(self, client, safety_officer):
        """Requesting a nonexistent report returns 404."""
        client.login(username="safety_officer", password="testpass123")
        url = reverse("members:safety_report_detail", args=[99999])
        response = client.get(url)
        assert response.status_code == 404
