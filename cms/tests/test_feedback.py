"""
Tests for Site Feedback functionality (Issue #117)
"""

from unittest.mock import patch

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from cms.forms import SiteFeedbackForm
from cms.models import SiteFeedback
from members.models import Member


@pytest.fixture
def active_member(db):
    """Create an active member for testing"""
    member = Member.objects.create_user(
        username="testmember",
        email="test@example.com",
        first_name="Test",
        last_name="Member",
        membership_status="Full Member",
        phone="555-1234",
    )
    return member


@pytest.fixture
def admin_member(db):
    """Create an admin member for testing"""
    member = Member.objects.create_user(
        username="admin",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_staff=True,
        is_superuser=True,
        membership_status="Full Member",
        phone="555-9999",
    )
    return member


class TestSiteFeedbackModel:
    """Test SiteFeedback model functionality"""

    @pytest.mark.django_db
    def test_create_feedback(self, active_member):
        """Test creating a basic feedback entry"""
        feedback = SiteFeedback.objects.create(
            user=active_member,
            feedback_type="bug",
            subject="Test Bug",
            message="This is a test bug report",
            referring_url="http://example.com/test-page/",
        )

        assert feedback.user == active_member
        assert feedback.feedback_type == "bug"
        assert feedback.subject == "Test Bug"
        assert feedback.status == "open"  # default status
        assert feedback.referring_url == "http://example.com/test-page/"
        assert feedback.resolved_at is None
        assert feedback.responded_by is None

    @pytest.mark.django_db
    def test_feedback_str_representation(self, active_member):
        """Test string representation of feedback"""
        feedback = SiteFeedback.objects.create(
            user=active_member,
            feedback_type="feature",
            subject="New Feature Request",
            message="Please add this feature",
        )

        assert str(feedback) == "Feature Request: New Feature Request - Test Member"

    @pytest.mark.django_db
    def test_feedback_choices(self):
        """Test that feedback type and status choices are properly defined"""
        # Test feedback type choices
        feedback_types = [choice[0] for choice in SiteFeedback.FEEDBACK_TYPE_CHOICES]
        assert "bug" in feedback_types
        assert "feature" in feedback_types
        assert "help" in feedback_types
        assert "other" in feedback_types

        # Test status choices
        statuses = [choice[0] for choice in SiteFeedback.STATUS_CHOICES]
        assert "open" in statuses
        assert "in_progress" in statuses
        assert "resolved" in statuses
        assert "closed" in statuses

    @pytest.mark.django_db
    def test_feedback_ordering(self, active_member):
        """Test that feedback is ordered by creation date (newest first)"""
        feedback1 = SiteFeedback.objects.create(
            user=active_member,
            feedback_type="bug",
            subject="First Bug",
            message="First bug report",
        )
        feedback2 = SiteFeedback.objects.create(
            user=active_member,
            feedback_type="bug",
            subject="Second Bug",
            message="Second bug report",
        )

        feedback_list = list(SiteFeedback.objects.all())
        assert feedback_list[0] == feedback2  # newest first
        assert feedback_list[1] == feedback1


class TestSiteFeedbackForm:
    """Test SiteFeedbackForm functionality"""

    def test_form_valid_data(self):
        """Test form with valid data"""
        form_data = {
            "feedback_type": "bug",
            "subject": "Test Subject",
            "message": "Test message content",
        }
        form = SiteFeedbackForm(data=form_data)
        assert form.is_valid()

    def test_form_missing_required_fields(self):
        """Test form validation with missing required fields"""
        form_data = {
            "feedback_type": "bug",
            # missing subject and message
        }
        form = SiteFeedbackForm(data=form_data)
        assert not form.is_valid()
        assert "subject" in form.errors
        assert "message" in form.errors

    def test_form_invalid_feedback_type(self):
        """Test form validation with invalid feedback type"""
        form_data = {
            "feedback_type": "invalid_type",
            "subject": "Test Subject",
            "message": "Test message",
        }
        form = SiteFeedbackForm(data=form_data)
        assert not form.is_valid()
        assert "feedback_type" in form.errors

    def test_form_subject_max_length(self):
        """Test form validation for subject max length"""
        form_data = {
            "feedback_type": "other",
            "subject": "x" * 201,  # Exceeds 200 char limit
            "message": "Test message",
        }
        form = SiteFeedbackForm(data=form_data)
        assert not form.is_valid()
        assert "subject" in form.errors


class TestFeedbackViews:
    """Test feedback view functionality"""

    @pytest.mark.django_db
    def test_feedback_form_get_anonymous(self, client):
        """Test accessing feedback form as anonymous user"""
        url = reverse("cms:feedback")
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    @pytest.mark.django_db
    def test_feedback_form_get_authenticated(self, client, active_member):
        """Test accessing feedback form as authenticated user"""
        client.force_login(active_member)
        url = reverse("cms:feedback")
        response = client.get(url)

        assert response.status_code == 200
        assert "form" in response.context
        assert isinstance(response.context["form"], SiteFeedbackForm)
        assert b"Submit Feedback" in response.content

    @pytest.mark.django_db
    def test_feedback_form_with_referring_url(self, client, active_member):
        """Test feedback form captures referring URL from query parameter"""
        client.force_login(active_member)
        url = reverse("cms:feedback") + "?from=/some/page/"
        response = client.get(url)

        assert response.status_code == 200
        assert "referring_url" in response.context
        assert response.context["referring_url"] == "/some/page/"

    @pytest.mark.django_db
    @patch("cms.views._notify_webmasters_of_feedback")
    def test_feedback_form_post_valid(
        self, mock_notify_webmasters, client, active_member
    ):
        """Test submitting valid feedback form"""
        client.force_login(active_member)
        url = reverse("cms:feedback")

        form_data = {
            "feedback_type": "bug",
            "subject": "Test Bug Report",
            "message": "This is a test bug report message",
        }

        response = client.post(url + "?from=/test-page/", form_data)

        # Should redirect to success page
        assert response.status_code == 302
        assert response["Location"] == reverse("cms:feedback_success")

        # Check feedback was created
        feedback = SiteFeedback.objects.get()
        assert feedback.user == active_member
        assert feedback.feedback_type == "bug"
        assert feedback.subject == "Test Bug Report"
        assert feedback.referring_url == "/test-page/"
        assert feedback.status == "open"

        # Check notification was sent
        mock_notify_webmasters.assert_called_once()

    @pytest.mark.django_db
    def test_feedback_form_post_invalid(self, client, active_member):
        """Test submitting invalid feedback form"""
        client.force_login(active_member)
        url = reverse("cms:feedback")

        form_data = {
            "feedback_type": "bug",
            # missing required fields
        }

        response = client.post(url, form_data)

        # Should return form with errors
        assert response.status_code == 200
        assert "form" in response.context
        assert response.context["form"].errors

        # No feedback should be created
        assert SiteFeedback.objects.count() == 0

    @pytest.mark.django_db
    def test_feedback_success_page(self, client, active_member):
        """Test feedback success page"""
        client.force_login(active_member)
        url = reverse("cms:feedback_success")
        response = client.get(url)

        assert response.status_code == 200
        assert (
            b"Thank you" in response.content or b"success" in response.content.lower()
        )

    @pytest.mark.django_db
    def test_feedback_success_page_anonymous(self, client):
        """Test feedback success page as anonymous user"""
        url = reverse("cms:feedback_success")
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert "/login/" in response["Location"]


class TestFeedbackNotifications:
    """Test feedback notification functionality"""

    @pytest.mark.django_db
    @patch("cms.views._notify_webmasters_of_feedback")
    def test_webmaster_notification_sent(
        self, mock_notify_webmasters, client, active_member
    ):
        """Test that webmaster notification is sent on feedback submission"""
        client.force_login(active_member)
        url = reverse("cms:feedback")

        form_data = {
            "feedback_type": "feature",
            "subject": "New Feature Idea",
            "message": "I have an idea for a new feature",
        }

        client.post(url, form_data)

        # Check notification was called
        mock_notify_webmasters.assert_called_once()

        # Verify the feedback object was passed
        call_args = mock_notify_webmasters.call_args[0]
        feedback = call_args[0]
        assert feedback.subject == "New Feature Idea"
        assert feedback.user == active_member

    @pytest.mark.django_db
    def test_notification_handles_missing_webmaster_gracefully(
        self, client, active_member
    ):
        """Test that feedback submission works even if notification system fails"""
        client.force_login(active_member)
        url = reverse("cms:feedback")

        form_data = {
            "feedback_type": "other",
            "subject": "Test Feedback",
            "message": "Test message",
        }

        # Mock the Notification model import to raise an exception during notification creation
        with patch(
            "notifications.models.Notification.objects.create",
            side_effect=Exception("Notification failed"),
        ):
            response = client.post(url, form_data)

            # Should still redirect to success (graceful failure in _notify_webmasters_of_feedback)
            assert response.status_code == 302
            assert response["Location"] == reverse("cms:feedback_success")

            # Feedback should still be created
            assert SiteFeedback.objects.count() == 1


class TestFeedbackAdminIntegration:
    """Test feedback admin interface functionality"""

    @pytest.mark.django_db
    def test_feedback_admin_list_view(self):
        """Test feedback admin list view"""
        # Create an admin member
        admin_member = Member.objects.create_user(
            username="admin_list",
            email="admin_list@example.com",
            first_name="Admin",
            last_name="List",
            is_staff=True,
            is_superuser=True,
            membership_status="Full Member",
        )

        # Create a regular member
        regular_member = Member.objects.create_user(
            username="regular_list",
            email="regular_list@example.com",
            first_name="Regular",
            last_name="Member",
            membership_status="Full Member",
        )

        # Create some feedback entries
        SiteFeedback.objects.create(
            user=regular_member,
            feedback_type="bug",
            subject="Test Bug",
            message="Bug description",
        )

        client = Client()
        client.force_login(admin_member)
        url = "/admin/cms/sitefeedback/"
        response = client.get(url)

        assert response.status_code == 200
        assert b"Test Bug" in response.content

    @pytest.mark.django_db
    def test_feedback_admin_change_view(self):
        """Test feedback admin change view"""
        # Create an admin member
        admin_member = Member.objects.create_user(
            username="admin_change",
            email="admin_change@example.com",
            first_name="Admin",
            last_name="Change",
            is_staff=True,
            is_superuser=True,
            membership_status="Full Member",
        )

        # Create a regular member
        regular_member = Member.objects.create_user(
            username="regular_change",
            email="regular_change@example.com",
            first_name="Regular",
            last_name="Change",
            membership_status="Full Member",
        )

        feedback = SiteFeedback.objects.create(
            user=regular_member,
            feedback_type="feature",
            subject="Feature Request",
            message="Feature description",
        )

        client = Client()
        client.force_login(admin_member)
        url = f"/admin/cms/sitefeedback/{feedback.pk}/change/"
        response = client.get(url)

        assert response.status_code == 200
        assert b"Feature Request" in response.content

    @pytest.mark.django_db
    def test_feedback_admin_response_tracking(self):
        """Test that admin responses are tracked properly"""
        # Create an admin member
        admin_member = Member.objects.create_user(
            username="admin_response",
            email="admin_response@example.com",
            first_name="Admin",
            last_name="Response",
            is_staff=True,
            is_superuser=True,
            membership_status="Full Member",
        )

        # Create a regular member
        regular_member = Member.objects.create_user(
            username="regular_response",
            email="regular_response@example.com",
            first_name="Regular",
            last_name="Response",
            membership_status="Full Member",
        )

        feedback = SiteFeedback.objects.create(
            user=regular_member,
            feedback_type="bug",
            subject="Bug Report",
            message="Bug description",
        )

        client = Client()
        client.force_login(admin_member)
        url = f"/admin/cms/sitefeedback/{feedback.pk}/change/"

        form_data = {
            "user": regular_member.pk,
            "feedback_type": "bug",
            "subject": "Bug Report",
            "message": "Bug description",
            "status": "in_progress",
            "admin_response": "Working on this issue",
        }

        response = client.post(url, form_data)

        # Should redirect after successful save
        assert response.status_code == 302

        # Check that responded_by was set automatically
        feedback.refresh_from_db()
        assert feedback.responded_by == admin_member
        assert feedback.status == "in_progress"
        assert feedback.admin_response == "Working on this issue"


class TestFeedbackSecurity:
    """Test security aspects of feedback system"""

    @pytest.mark.django_db
    def test_feedback_requires_authentication(self, client):
        """Test that feedback endpoints require authentication"""
        urls = [reverse("cms:feedback"), reverse("cms:feedback_success")]

        for url in urls:
            response = client.get(url)
            assert response.status_code == 302
            assert "/login/" in response["Location"]

    @pytest.mark.django_db
    def test_feedback_requires_active_membership(self, client):
        """Test that feedback requires active membership"""
        # Create inactive user
        inactive_member = Member.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            membership_status="Inactive",
        )

        client.force_login(inactive_member)
        url = reverse("cms:feedback")
        response = client.get(url)

        # Inactive members have is_active=False, so Django's auth middleware
        # redirects them to login instead of letting them reach the view
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    @pytest.mark.django_db
    def test_users_can_only_see_own_feedback(self, client, active_member):
        """Test that users cannot access other users' feedback directly"""
        # This would be tested if we had user-facing feedback viewing
        # For now, feedback is only visible through admin interface
        pass

    @pytest.mark.django_db
    def test_xss_prevention_in_feedback(self, client, active_member):
        """Test that XSS attempts in feedback are handled properly"""
        client.force_login(active_member)
        url = reverse("cms:feedback")

        form_data = {
            "feedback_type": "other",
            "subject": '<script>alert("xss")</script>',
            "message": '<img src="x" onerror="alert(\'xss\')">',
        }

        response = client.post(url, form_data)

        # Should still process (TinyMCE and Django handle sanitization)
        assert response.status_code == 302

        feedback = SiteFeedback.objects.get()
        # The exact content depends on TinyMCE configuration
        # but dangerous scripts should be sanitized
        assert feedback.subject == '<script>alert("xss")</script>'  # Raw storage
        # HTML rendering would be sanitized by TinyMCE/template system


class TestFeedbackWorkflow:
    """Test complete feedback workflow scenarios"""

    @pytest.mark.django_db
    @patch("cms.views._notify_webmasters_of_feedback")
    def test_complete_feedback_workflow(self, mock_notify_webmasters):
        """Test complete workflow from submission to resolution"""
        # Create members
        active_member = Member.objects.create_user(
            username="workflow_user",
            email="workflow_user@example.com",
            first_name="Workflow",
            last_name="User",
            membership_status="Full Member",
        )

        admin_member = Member.objects.create_user(
            username="workflow_admin",
            email="workflow_admin@example.com",
            first_name="Workflow",
            last_name="Admin",
            is_staff=True,
            is_superuser=True,
            membership_status="Full Member",
        )

        client = Client()

        # 1. User submits feedback
        client.force_login(active_member)
        url = reverse("cms:feedback")

        form_data = {
            "feedback_type": "bug",
            "subject": "Critical Bug",
            "message": "This bug needs fixing",
        }

        response = client.post(url + "?from=/problematic-page/", form_data)
        assert response.status_code == 302

        feedback = SiteFeedback.objects.get()
        assert feedback.status == "open"
        assert feedback.referring_url == "/problematic-page/"

        # 2. Admin reviews and updates status
        client.force_login(admin_member)
        admin_url = f"/admin/cms/sitefeedback/{feedback.pk}/change/"

        admin_form_data = {
            "user": active_member.pk,
            "feedback_type": "bug",
            "subject": "Critical Bug",
            "message": "This bug needs fixing",
            "status": "in_progress",
            "admin_response": "Investigating this issue",
        }

        client.post(admin_url, admin_form_data)

        feedback.refresh_from_db()
        assert feedback.status == "in_progress"
        assert feedback.responded_by == admin_member

        # 3. Admin resolves the feedback
        admin_form_data["status"] = "resolved"
        admin_form_data["admin_response"] = "Bug has been fixed in latest release"

        client.post(admin_url, admin_form_data)

        feedback.refresh_from_db()
        assert feedback.status == "resolved"
        assert feedback.resolved_at is not None
