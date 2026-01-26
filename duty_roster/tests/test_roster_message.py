"""Tests for DutyRosterMessage feature (Issue #551).

This module tests the rich HTML roster message functionality that replaces
the plain-text duty_roster_announcement field in SiteConfiguration.
"""

import pytest
from django.urls import reverse

from duty_roster.forms import DutyRosterMessageForm
from duty_roster.models import DutyRosterMessage
from members.models import Member
from siteconfig.models import MembershipStatus, SiteConfiguration


@pytest.fixture
def membership_statuses(db):
    """Create necessary membership statuses."""
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True, "sort_order": 10}
    )


@pytest.fixture
def siteconfig(db):
    """Get or create SiteConfiguration for testing."""
    config, _ = SiteConfiguration.objects.get_or_create(
        defaults={
            "club_name": "Test Club",
            "domain_name": "test.org",
            "club_abbreviation": "TC",
        }
    )
    return config


@pytest.fixture
def rostermeister(db, membership_statuses, siteconfig):
    """Create a rostermeister user."""
    user = Member.objects.create_user(
        username="rostermeister",
        email="rostermeister@test.org",
        password="testpass123",
        first_name="Roster",
        last_name="Meister",
        membership_status="Full Member",
        rostermeister=True,
    )
    return user


@pytest.fixture
def regular_member(db, membership_statuses, siteconfig):
    """Create a regular member without rostermeister privileges."""
    user = Member.objects.create_user(
        username="regular",
        email="regular@test.org",
        password="testpass123",
        first_name="Regular",
        last_name="Member",
        membership_status="Full Member",
        rostermeister=False,
    )
    return user


@pytest.fixture
def staff_user(db, membership_statuses, siteconfig):
    """Create a staff user."""
    user = Member.objects.create_user(
        username="staff",
        email="staff@test.org",
        password="testpass123",
        first_name="Staff",
        last_name="User",
        membership_status="Full Member",
        is_staff=True,
    )
    return user


@pytest.fixture
def roster_message(db):
    """Create a DutyRosterMessage instance."""
    # Clear any existing messages first (singleton pattern)
    DutyRosterMessage.objects.all().delete()
    return DutyRosterMessage.objects.create(
        content="<p>Test announcement with <strong>HTML</strong> content.</p>",
        is_active=True,
    )


@pytest.mark.django_db
class TestDutyRosterMessageModel:
    """Tests for the DutyRosterMessage model."""

    def test_create_message(self, db):
        """Test creating a DutyRosterMessage instance."""
        DutyRosterMessage.objects.all().delete()
        message = DutyRosterMessage.objects.create(
            content="<p>Hello World</p>",
            is_active=True,
        )
        assert message.pk is not None
        assert message.content == "<p>Hello World</p>"
        assert message.is_active is True

    def test_singleton_pattern(self, db):
        """Test that only one DutyRosterMessage can exist (singleton)."""
        from django.core.exceptions import ValidationError

        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(content="<p>First</p>")

        # Trying to create a second instance should raise ValidationError
        with pytest.raises(ValidationError, match="Only one Duty Roster Message"):
            DutyRosterMessage.objects.create(content="<p>Second</p>")

        # Should still only have one instance
        assert DutyRosterMessage.objects.count() == 1
        # The first one should still exist
        message = DutyRosterMessage.objects.first()
        assert message is not None
        assert message.content == "<p>First</p>"

    def test_get_message_returns_active_message(self, roster_message):
        """Test get_message() returns the active message."""
        message = DutyRosterMessage.get_message()
        assert message is not None
        assert message.pk == roster_message.pk

    def test_get_message_returns_none_when_inactive(self, db):
        """Test get_message() returns None when message is inactive."""
        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(
            content="<p>Inactive message</p>",
            is_active=False,
        )
        assert DutyRosterMessage.get_message() is None

    def test_get_message_returns_none_when_empty(self, db):
        """Test get_message() returns None when content is empty."""
        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(
            content="",
            is_active=True,
        )
        assert DutyRosterMessage.get_message() is None

    def test_get_message_returns_none_when_whitespace_only(self, db):
        """Test get_message() returns None when content is whitespace only."""
        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(
            content="   \n\t  ",
            is_active=True,
        )
        assert DutyRosterMessage.get_message() is None

    def test_get_or_create_message_creates_if_not_exists(self, db):
        """Test get_or_create_message() creates a message if none exists."""
        DutyRosterMessage.objects.all().delete()
        assert DutyRosterMessage.objects.count() == 0

        message = DutyRosterMessage.get_or_create_message()
        assert message is not None
        assert DutyRosterMessage.objects.count() == 1

    def test_get_or_create_message_returns_existing(self, roster_message):
        """Test get_or_create_message() returns existing message."""
        message = DutyRosterMessage.get_or_create_message()
        assert message.pk == roster_message.pk

    def test_str_representation(self, roster_message):
        """Test string representation of DutyRosterMessage."""
        str_repr = str(roster_message)
        assert "Rostermeister Message" in str_repr

    def test_str_representation_empty(self, db):
        """Test string representation when content is empty."""
        DutyRosterMessage.objects.all().delete()
        message = DutyRosterMessage.objects.create(content="")
        assert "empty" in str(message).lower()

    def test_updated_by_tracking(self, roster_message, rostermeister):
        """Test that updated_by field can be set."""
        roster_message.updated_by = rostermeister
        roster_message.save()
        roster_message.refresh_from_db()
        assert roster_message.updated_by == rostermeister


@pytest.mark.django_db
class TestDutyRosterMessageForm:
    """Tests for the DutyRosterMessageForm."""

    def test_form_valid_with_content(self):
        """Test form is valid with content."""
        form = DutyRosterMessageForm(
            data={
                "content": "<p>Test message</p>",
                "is_active": True,
            }
        )
        assert form.is_valid()

    def test_form_valid_with_empty_content(self):
        """Test form is valid with empty content (to clear message)."""
        form = DutyRosterMessageForm(
            data={
                "content": "",
                "is_active": True,
            }
        )
        assert form.is_valid()

    def test_form_valid_when_inactive(self):
        """Test form is valid when is_active is False."""
        form = DutyRosterMessageForm(
            data={
                "content": "<p>Some content</p>",
                "is_active": False,
            }
        )
        assert form.is_valid()


@pytest.mark.django_db
class TestEditRosterMessageView:
    """Tests for the edit_roster_message view."""

    def test_view_requires_login(self, client):
        """Test that the view requires authentication."""
        url = reverse("duty_roster:edit_roster_message")
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_regular_member_denied(self, client, regular_member):
        """Test that regular members cannot access the view."""
        client.force_login(regular_member)
        url = reverse("duty_roster:edit_roster_message")
        response = client.get(url)
        assert response.status_code == 302  # Redirects to login

    def test_rostermeister_can_access(self, client, rostermeister):
        """Test that rostermeisters can access the view."""
        client.force_login(rostermeister)
        url = reverse("duty_roster:edit_roster_message")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Edit Roster Announcement" in response.content

    def test_view_displays_form(self, client, rostermeister):
        """Test that the view displays the form."""
        client.force_login(rostermeister)
        url = reverse("duty_roster:edit_roster_message")
        response = client.get(url)
        assert response.status_code == 200
        assert b"form" in response.content
        assert b"Save Message" in response.content

    def test_view_creates_message_on_first_access(self, client, rostermeister, db):
        """Test that accessing the view creates a message if none exists."""
        DutyRosterMessage.objects.all().delete()
        assert DutyRosterMessage.objects.count() == 0

        client.force_login(rostermeister)
        url = reverse("duty_roster:edit_roster_message")
        client.get(url)

        assert DutyRosterMessage.objects.count() == 1

    def test_save_message(self, client, rostermeister, db):
        """Test saving a message."""
        DutyRosterMessage.objects.all().delete()
        client.force_login(rostermeister)
        url = reverse("duty_roster:edit_roster_message")

        response = client.post(
            url,
            {
                "content": "<p>New announcement!</p>",
                "is_active": True,
            },
        )

        assert response.status_code == 302  # Redirects to calendar
        message = DutyRosterMessage.objects.first()
        assert message is not None
        assert "<p>New announcement!</p>" in message.content
        assert message.is_active is True
        assert message.updated_by == rostermeister

    def test_update_existing_message(self, client, rostermeister, roster_message):
        """Test updating an existing message."""
        client.force_login(rostermeister)
        url = reverse("duty_roster:edit_roster_message")

        response = client.post(
            url,
            {
                "content": "<p>Updated content!</p>",
                "is_active": False,
            },
        )

        assert response.status_code == 302
        roster_message.refresh_from_db()
        assert "<p>Updated content!</p>" in roster_message.content
        assert roster_message.is_active is False


@pytest.mark.django_db
class TestCalendarDisplaysRosterMessage:
    """Tests for calendar view displaying the roster message."""

    def test_calendar_displays_message(self, client, regular_member, roster_message):
        """Test that the calendar displays the active message."""
        client.force_login(regular_member)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)

        assert response.status_code == 200
        assert b"bi-megaphone" in response.content
        assert b"Roster Manager Announcement" in response.content
        assert b"HTML" in response.content  # From the <strong>HTML</strong> in fixture

    def test_calendar_no_message_when_inactive(self, client, regular_member, db):
        """Test that the calendar doesn't display inactive messages."""
        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(
            content="<p>Hidden message</p>",
            is_active=False,
        )

        client.force_login(regular_member)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)

        assert response.status_code == 200
        assert b"Hidden message" not in response.content

    def test_calendar_no_message_when_empty(self, client, regular_member, db):
        """Test that the calendar doesn't display empty messages."""
        DutyRosterMessage.objects.all().delete()

        client.force_login(regular_member)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)

        assert response.status_code == 200
        # Regular member shouldn't see the "Add Announcement" button
        assert b"Add Announcement" not in response.content

    def test_rostermeister_sees_edit_button(
        self, client, rostermeister, roster_message
    ):
        """Test that rostermeisters see the edit button."""
        client.force_login(rostermeister)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)

        assert response.status_code == 200
        assert b"bi-pencil" in response.content  # Edit icon
        assert (
            b"edit_roster_message" in response.content
            or b"message/edit" in response.content
        )

    def test_rostermeister_sees_add_button_when_no_message(
        self, client, rostermeister, db
    ):
        """Test that rostermeisters see 'Add Announcement' when no message exists."""
        DutyRosterMessage.objects.all().delete()

        client.force_login(rostermeister)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)

        assert response.status_code == 200
        assert b"Add Announcement" in response.content

    def test_regular_member_no_edit_button(
        self, client, regular_member, roster_message
    ):
        """Test that regular members don't see the edit button."""
        client.force_login(regular_member)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)

        assert response.status_code == 200
        assert b"bi-pencil" not in response.content


@pytest.mark.django_db
class TestTemplateTag:
    """Tests for the get_roster_message template tag."""

    def test_template_tag_returns_active_message(self, roster_message):
        """Test that the template tag returns the active message."""
        from duty_roster.templatetags.duty_extras import get_roster_message

        message = get_roster_message()
        assert message is not None
        assert message.pk == roster_message.pk

    def test_template_tag_returns_none_when_no_message(self, db):
        """Test that the template tag returns None when no message exists."""
        from duty_roster.templatetags.duty_extras import get_roster_message

        DutyRosterMessage.objects.all().delete()
        message = get_roster_message()
        assert message is None
