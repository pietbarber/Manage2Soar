"""
Tests for safety reports functionality (Issue #554).
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from members.forms import SafetyReportForm
from members.models import SafetyReport

Member = get_user_model()


@pytest.fixture
def active_member(db):
    """Create an active member for testing."""
    return Member.objects.create_user(
        username="testmember",
        email="test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="Member",
        membership_status="Full Member",
        is_active=True,
    )


@pytest.fixture
def safety_officer(db):
    """Create a safety officer for testing."""
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
def client():
    """Create a test client."""
    return Client()


class TestSafetyReportModel:
    """Tests for the SafetyReport model."""

    def test_create_safety_report_with_reporter(self, db, active_member):
        """Test creating a non-anonymous safety report."""
        report = SafetyReport.objects.create(
            reporter=active_member,
            is_anonymous=False,
            observation="Test safety observation",
            observation_date=date.today(),
            location="Main runway",
        )
        assert report.reporter == active_member
        assert report.is_anonymous is False
        assert report.status == "new"
        assert report.get_reporter_display() == "Test Member"

    def test_create_anonymous_safety_report(self, db):
        """Test creating an anonymous safety report (no reporter recorded)."""
        report = SafetyReport.objects.create(
            reporter=None,  # Truly anonymous - no reporter recorded
            is_anonymous=True,
            observation="Anonymous safety observation",
        )
        assert report.reporter is None
        assert report.is_anonymous is True
        assert report.get_reporter_display() == "Anonymous"

    def test_status_workflow(self, db, active_member, safety_officer):
        """Test the status workflow for safety reports."""
        report = SafetyReport.objects.create(
            reporter=active_member,
            is_anonymous=False,
            observation="Test observation",
        )
        assert report.status == "new"

        # Simulate review
        report.status = "reviewed"
        report.reviewed_by = safety_officer
        report.save()
        assert report.status == "reviewed"
        assert report.reviewed_by == safety_officer

        # Move through workflow
        for status in ["in_progress", "resolved", "closed"]:
            report.status = status
            report.save()
            assert report.status == status


class TestSafetyReportForm:
    """Tests for the SafetyReportForm."""

    def test_valid_form(self, db):
        """Test form with valid data."""
        form_data = {
            "observation": "<p>Test observation content</p>",
            "observation_date": date.today(),
            "location": "Test location",
            "is_anonymous": False,
        }
        form = SafetyReportForm(data=form_data)
        assert form.is_valid(), form.errors

    def test_form_requires_observation(self, db):
        """Test that observation is required."""
        form_data = {
            "observation": "",
            "is_anonymous": False,
        }
        form = SafetyReportForm(data=form_data)
        assert not form.is_valid()
        assert "observation" in form.errors

    def test_form_anonymous_flag_optional(self, db):
        """Test form without anonymous flag (defaults to False)."""
        form_data = {
            "observation": "<p>Test observation</p>",
        }
        form = SafetyReportForm(data=form_data)
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestSafetyReportViews:
    """Tests for safety report views."""

    def test_submit_form_requires_login(self, client):
        """Test that the submit form requires authentication."""
        url = reverse("members:safety_report_submit")
        response = client.get(url)
        # Should redirect to login
        assert response.status_code == 302
        assert "login" in response.url or "accounts" in response.url

    def test_submit_form_accessible_to_member(self, client, active_member):
        """Test that authenticated members can access the submit form."""
        client.login(username="testmember", password="testpass123")
        url = reverse("members:safety_report_submit")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Safety Suggestion Box" in response.content

    def test_submit_non_anonymous_report(self, client, active_member):
        """Test submitting a non-anonymous safety report."""
        client.login(username="testmember", password="testpass123")
        url = reverse("members:safety_report_submit")
        form_data = {
            "observation": "<p>I observed a potential safety issue.</p>",
            "observation_date": date.today().isoformat(),
            "location": "Runway 27",
            "is_anonymous": False,
        }
        response = client.post(url, form_data)

        # Should redirect after successful submission
        assert response.status_code == 302

        # Verify the report was created with the reporter
        report = SafetyReport.objects.first()
        assert report is not None
        assert report.reporter == active_member
        assert report.is_anonymous is False
        assert "safety issue" in report.observation

    def test_submit_anonymous_report(self, client, active_member):
        """Test submitting an anonymous safety report - reporter should NOT be recorded."""
        client.login(username="testmember", password="testpass123")
        url = reverse("members:safety_report_submit")
        form_data = {
            "observation": "<p>Anonymous safety concern.</p>",
            "is_anonymous": True,  # This is the key - anonymity should be honored
        }
        response = client.post(url, form_data)

        # Should redirect after successful submission
        assert response.status_code == 302

        # Verify the report was created WITHOUT the reporter (truly anonymous)
        report = SafetyReport.objects.first()
        assert report is not None
        assert report.reporter is None  # Critical: reporter should NOT be recorded
        assert report.is_anonymous is True
        assert report.get_reporter_display() == "Anonymous"


class TestSafetyOfficerField(TestCase):
    """Tests for the safety_officer field on Member model."""

    def test_member_safety_officer_field_default_false(self):
        """Test that safety_officer defaults to False."""
        member = Member.objects.create_user(
            username="newmember",
            email="new@example.com",
            password="testpass123",
        )
        assert member.safety_officer is False

    def test_member_can_be_safety_officer(self):
        """Test that a member can be designated as a safety officer."""
        member = Member.objects.create_user(
            username="safetytest",
            email="safetytest@example.com",
            password="testpass123",
            safety_officer=True,
        )
        assert member.safety_officer is True

    def test_filter_safety_officers(self):
        """Test filtering members by safety_officer flag."""
        # Create regular member
        Member.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123",
            safety_officer=False,
        )
        # Create safety officer
        Member.objects.create_user(
            username="officer",
            email="officer@example.com",
            password="testpass123",
            safety_officer=True,
        )

        safety_officers = Member.objects.filter(safety_officer=True)
        assert safety_officers.count() == 1
        officer = safety_officers.first()
        assert officer is not None
        assert officer.username == "officer"
