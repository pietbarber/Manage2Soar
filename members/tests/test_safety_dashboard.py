"""
Tests for the Safety Officer Dashboard view (Issue #622).
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from logsheet.models import Airfield, Logsheet, LogsheetCloseout
from members.models import SafetyReport
from members.views_safety_reports import _is_nothing_to_report

Member = get_user_model()


@pytest.fixture
def safety_officer(db):
    """Create a safety officer member."""
    return Member.objects.create_user(
        username="safetyofficer",
        email="safety@example.com",
        password="testpass123",
        first_name="Safety",
        last_name="Officer",
        membership_status="Full Member",
        is_active=True,
        safety_officer=True,
    )


@pytest.fixture
def regular_member(db):
    """Create a regular (non-safety-officer) member."""
    return Member.objects.create_user(
        username="regularmember",
        email="regular@example.com",
        password="testpass123",
        first_name="Regular",
        last_name="Member",
        membership_status="Full Member",
        is_active=True,
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
        membership_status="Full Member",
    )


@pytest.fixture
def airfield(db):
    """Create a test airfield."""
    return Airfield.objects.create(
        name="Test Airfield",
        identifier="TST",
    )


@pytest.fixture
def client():
    """Create a test client."""
    return Client()


def _create_logsheet_with_closeout(
    airfield, created_by, log_date, safety_issues, finalized=True
):
    """Helper to create a logsheet with closeout."""
    logsheet = Logsheet.objects.create(
        log_date=log_date,
        airfield=airfield,
        created_by=created_by,
        finalized=finalized,
    )
    closeout = LogsheetCloseout.objects.create(
        logsheet=logsheet,
        safety_issues=safety_issues,
    )
    return logsheet, closeout


class TestIsNothingToReport:
    """Tests for the _is_nothing_to_report helper function."""

    def test_empty_string(self):
        assert _is_nothing_to_report("") is True

    def test_none_value(self):
        assert _is_nothing_to_report(None) is True

    def test_whitespace_only(self):
        assert _is_nothing_to_report("   ") is True

    def test_none_text(self):
        assert _is_nothing_to_report("None") is True

    def test_na_text(self):
        assert _is_nothing_to_report("N/A") is True
        assert _is_nothing_to_report("n/a") is True
        assert _is_nothing_to_report("NA") is True

    def test_nothing_to_report(self):
        assert _is_nothing_to_report("Nothing to report") is True
        assert _is_nothing_to_report("nothing to report.") is True

    def test_no_safety_issues(self):
        assert _is_nothing_to_report("No safety issues") is True
        assert _is_nothing_to_report("No issues") is True
        assert _is_nothing_to_report("No safety concerns") is True

    def test_no_safety_issues_to_report(self):
        """Test that 'to report' suffix is handled (addresses Copilot review comment)."""
        assert _is_nothing_to_report("No safety issues to report") is True
        assert _is_nothing_to_report("No issues to report") is True
        assert _is_nothing_to_report("No safety concerns to report") is True
        assert _is_nothing_to_report("No problems to report") is True

    def test_html_wrapped_nothing(self):
        assert _is_nothing_to_report("<p>Nothing to report</p>") is True
        assert _is_nothing_to_report("<p>None</p>") is True
        assert _is_nothing_to_report("<p>N/A</p>") is True

    def test_substantive_content(self):
        assert _is_nothing_to_report("Rope break on tow") is False
        assert _is_nothing_to_report("<p>Wing runner tripped on stake</p>") is False
        assert (
            _is_nothing_to_report(
                "Low altitude turn back observed. Discussed with pilot."
            )
            is False
        )

    def test_all_good(self):
        assert _is_nothing_to_report("All good") is True
        assert _is_nothing_to_report("All clear") is True

    def test_no_incidents(self):
        assert _is_nothing_to_report("No incidents") is True


@pytest.mark.django_db
class TestSafetyDashboardAccess:
    """Tests for dashboard access control."""

    def test_anonymous_user_redirected(self, client):
        """Anonymous users should be redirected to login."""
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.status_code == 302
        assert "login" in response.url or "accounts" in response.url

    def test_regular_member_forbidden(self, client, regular_member):
        """Regular members should get 403."""
        client.login(username="regularmember", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.status_code == 403

    def test_safety_officer_can_access(self, client, safety_officer):
        """Safety officers should have access."""
        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.status_code == 200

    def test_superuser_can_access(self, client, superuser):
        """Superusers should have access."""
        client.login(username="admin", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.status_code == 200


@pytest.mark.django_db
class TestSafetyDashboardSuggestionBox:
    """Tests for the suggestion box reports section of the dashboard."""

    def test_displays_suggestion_reports(self, client, safety_officer, regular_member):
        """Dashboard shows suggestion box reports."""
        SafetyReport.objects.create(
            reporter=regular_member,
            is_anonymous=False,
            observation="<p>Test safety concern</p>",
            observation_date=date.today(),
            location="Runway 27",
        )
        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.status_code == 200
        # The report row should be visible via its location field
        assert b"Runway 27" in response.content

    def test_displays_suggestion_stats(self, client, safety_officer, regular_member):
        """Dashboard shows correct stats for suggestion box reports."""
        SafetyReport.objects.create(
            reporter=regular_member,
            observation="<p>New report</p>",
            status="new",
        )
        SafetyReport.objects.create(
            reporter=regular_member,
            observation="<p>In progress report</p>",
            status="in_progress",
        )
        SafetyReport.objects.create(
            reporter=regular_member,
            observation="<p>Resolved report</p>",
            status="resolved",
        )

        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        # Stats should reflect 3 total, 1 new, 1 in_progress, 1 resolved
        assert response.context["suggestion_stats"]["total"] == 3
        assert response.context["suggestion_stats"]["new"] == 1
        assert response.context["suggestion_stats"]["in_progress"] == 1
        assert response.context["suggestion_stats"]["resolved"] == 1

    def test_empty_suggestion_box(self, client, safety_officer):
        """Dashboard handles empty suggestion box gracefully."""
        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.status_code == 200
        assert b"No safety suggestion box reports found" in response.content


@pytest.mark.django_db
class TestSafetyDashboardOpsReports:
    """Tests for the ops report safety sections of the dashboard."""

    def test_displays_ops_safety_entries(self, client, safety_officer, airfield):
        """Dashboard shows ops report safety sections."""
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=7),
            safety_issues="<p>Rope break on third tow</p>",
        )
        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Rope break on third tow" in response.content

    def test_filters_nothing_to_report(self, client, safety_officer, airfield):
        """Dashboard filters out 'nothing to report' entries by default."""
        # Substantive entry
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=7),
            safety_issues="<p>Rope break on third tow</p>",
        )
        # Nothing to report entries
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=14),
            safety_issues="<p>Nothing to report</p>",
        )
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=21),
            safety_issues="None",
        )

        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.context["ops_substantive_count"] == 1
        assert response.context["ops_total_count"] == 3
        # Only the substantive entry should be in the page
        assert b"Rope break on third tow" in response.content

    def test_show_all_ops_includes_nothing_to_report(
        self, client, safety_officer, airfield
    ):
        """With show_all_ops=1, 'nothing to report' entries are included."""
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=7),
            safety_issues="<p>Rope break</p>",
        )
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=14),
            safety_issues="<p>Nothing to report</p>",
        )

        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard") + "?show_all_ops=1"
        response = client.get(url)
        assert response.context["show_all_ops"] is True
        # Both entries should be present
        assert b"Rope break" in response.content
        assert b"Nothing to report" in response.content

    def test_excludes_old_entries(self, client, safety_officer, airfield):
        """Entries older than 12 months should not appear."""
        # Entry from 400 days ago
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=400),
            safety_issues="<p>Old safety concern</p>",
        )
        # Recent entry
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=30),
            safety_issues="<p>Recent safety concern</p>",
        )

        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert b"Recent safety concern" in response.content
        assert b"Old safety concern" not in response.content

    def test_excludes_unfinalized_logsheets(self, client, safety_officer, airfield):
        """Unfinalized logsheets should not appear in ops safety sections."""
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=7),
            safety_issues="<p>Draft safety note</p>",
            finalized=False,
        )
        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert b"Draft safety note" not in response.content

    def test_excludes_empty_safety_issues(self, client, safety_officer, airfield):
        """Closeouts with empty safety_issues should not appear."""
        _create_logsheet_with_closeout(
            airfield=airfield,
            created_by=safety_officer,
            log_date=date.today() - timedelta(days=7),
            safety_issues="",
        )
        client.login(username="safetyofficer", password="testpass123")
        url = reverse("members:safety_officer_dashboard")
        response = client.get(url)
        assert response.context["ops_total_count"] == 0


@pytest.mark.django_db
class TestSafetyDashboardURL:
    """Tests for dashboard URL resolution."""

    def test_url_resolves(self):
        """The safety_officer_dashboard URL name should resolve."""
        url = reverse("members:safety_officer_dashboard")
        assert url == "/members/safety-dashboard/"
