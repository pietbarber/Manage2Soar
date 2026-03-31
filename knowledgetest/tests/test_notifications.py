"""
Tests for knowledgetest signals and notifications.

Tests the implementation of issue #212 - notification system for test bank updates.
"""

from typing import TYPE_CHECKING

import pytest
from django.test import TestCase
from django.utils import timezone

from knowledgetest.models import Question, QuestionCategory
from members.models import Member

try:
    from notifications.models import Notification
except ImportError:
    Notification = None

# Type checking imports (for Pylance compatibility)
if TYPE_CHECKING and Notification is not None:
    pass  # Type checking satisfied by Notification import above


@pytest.mark.skipif(Notification is None, reason="Notifications app not available")
class TestQuestionUpdateNotifications(TestCase):
    """Test that instructors are notified when test questions are updated."""

    def setUp(self):
        """Set up test data."""
        # Create a question category
        self.category = QuestionCategory.objects.create(
            code="TEST", description="Test Category"
        )

        # Create some test users - instructors and non-instructors
        self.instructor1 = Member.objects.create_user(
            username="instructor1",
            email="instructor1@example.com",
            first_name="John",
            last_name="Instructor",
            membership_status="Full Member",
        )
        self.instructor1.instructor = True
        self.instructor1.save()

        self.instructor2 = Member.objects.create_user(
            username="instructor2",
            email="instructor2@example.com",
            first_name="Jane",
            last_name="Teacher",
            membership_status="Full Member",
        )
        self.instructor2.instructor = True
        self.instructor2.save()

        self.regular_member = Member.objects.create_user(
            username="student",
            email="student@example.com",
            first_name="Bob",
            last_name="Student",
            membership_status="Student Member",
        )
        # regular_member.instructor defaults to False

        # Create a test question
        self.question = Question.objects.create(
            qnum=1001,
            category=self.category,
            question_text="What is the test question?",
            option_a="Option A",
            option_b="Option B",
            option_c="Option C",
            option_d="Option D",
            correct_answer="A",
            explanation="This is a test explanation.",
            updated_by=self.instructor1,
            last_updated=timezone.now().date(),
        )

    def test_instructors_notified_on_question_update(self):
        """Test that instructors receive notifications when a question is updated."""
        assert Notification is not None  # Type guard for Pylance

        # Clear any existing notifications
        Notification.objects.all().delete()

        # Update the question
        self.question.question_text = "What is the updated test question?"
        self.question.updated_by = self.instructor2
        self.question.save()

        # Check that notifications were created for instructors
        notifications = Notification.objects.filter(dismissed=False)

        # Should have notifications for both instructors
        self.assertEqual(notifications.count(), 2)

        # Check that the notifications are for the right users
        notified_users = set(notif.user for notif in notifications)
        expected_users = {self.instructor1, self.instructor2}
        self.assertEqual(notified_users, expected_users)

        # Check that the regular member was not notified
        student_notifications = notifications.filter(user=self.regular_member)
        self.assertEqual(student_notifications.count(), 0)

    def test_notification_message_content(self):
        """Test that the notification message contains expected content."""
        assert Notification is not None  # Type guard for Pylance

        # Clear any existing notifications
        Notification.objects.all().delete()

        # Update the question
        self.question.question_text = "Testing message content"
        self.question.updated_by = self.instructor1
        self.question.save()

        # Check notification message content
        notification = Notification.objects.filter(dismissed=False).first()
        self.assertIsNotNone(notification)
        assert notification is not None  # Type guard for notification

        message = notification.message
        self.assertIn("Q1001", message)  # Question number
        self.assertIn("John Instructor", message)  # Updater name
        self.assertIn("Knowledge test question updated", message)  # Base message

    def test_no_notification_on_question_creation(self):
        """Test that creating a new question doesn't trigger notifications (to avoid spam)."""
        assert Notification is not None  # Type guard for Pylance

        # Clear any existing notifications
        Notification.objects.all().delete()

        # Create a new question (not update)
        Question.objects.create(
            qnum=1002,
            category=self.category,
            question_text="What is the new question?",
            option_a="Option A",
            option_b="Option B",
            option_c="Option C",
            option_d="Option D",
            correct_answer="B",
            explanation="This is another test explanation.",
        )

        # No notifications should be created for new questions
        notification = Notification.objects.filter(dismissed=False).first()
        self.assertIsNone(notification)

    def test_multiple_updates_create_separate_notifications(self):
        """Test that multiple updates create separate notifications with unique dedup keys."""
        assert Notification is not None  # Type guard for Pylance
        # Clear any existing notifications
        Notification.objects.all().delete()

        # Update the question
        self.question.question_text = "First update"
        self.question.updated_by = self.instructor1
        self.question.save()

        # Count notifications after first update
        first_count = Notification.objects.filter(dismissed=False).count()

        # Add a small delay to ensure different timestamps
        import time

        time.sleep(1)

        # Update again - this should create new notifications since dedup key is different
        self.question.question_text = "Second update"
        self.question.save()

        # Should have notifications for both updates (different dedup keys)
        second_count = Notification.objects.filter(dismissed=False).count()

        self.assertEqual(first_count, 2)  # 2 instructors notified for first update
        self.assertEqual(second_count, 4)  # 2 instructors × 2 updates = 4 total

    def test_inactive_instructors_not_notified(self):
        """Test that inactive instructors do not receive notifications."""
        assert Notification is not None  # Type guard for Pylance

        # Clear any existing notifications
        Notification.objects.all().delete()

        # Make instructor2 inactive by changing membership status
        self.instructor2.membership_status = "Inactive"
        self.instructor2.save()

        # Update the question
        self.question.question_text = "Updated for inactive test"
        self.question.updated_by = self.instructor1
        self.question.save()

        # Should only notify active instructors (instructor1)
        notifications = Notification.objects.filter(dismissed=False)
        self.assertEqual(notifications.count(), 1)
        notification = notifications.first()
        assert notification is not None  # Type guard for notification
        self.assertEqual(notification.user, self.instructor1)

    def test_notification_url_points_to_admin(self):
        """Test that notification URL points to the question admin page."""
        assert Notification is not None  # Type guard for Pylance

        # Clear any existing notifications
        Notification.objects.all().delete()

        # Update the question
        self.question.question_text = "Testing admin URL"
        self.question.updated_by = self.instructor1
        self.question.save()

        # Check notification URL
        notification = Notification.objects.filter(dismissed=False).first()
        self.assertIsNotNone(notification)
        assert notification is not None  # Type guard for notification

        # URL should point to admin page
        if notification.url:
            self.assertIn("admin", notification.url)
            self.assertIn("knowledgetest", notification.url)
            self.assertIn("question", notification.url)
            self.assertIn("1001", notification.url)  # Question number
