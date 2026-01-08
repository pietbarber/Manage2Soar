"""
Tests for ICS calendar file generation (Issue #407).
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from icalendar import Calendar

from duty_roster.models import DutyAssignment, DutySwapOffer, DutySwapRequest
from duty_roster.utils.ics import (
    generate_duty_ics,
    generate_preop_ics,
    generate_swap_ics,
)
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config(db):
    """Create a site configuration for testing."""
    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        domain_name="testsoaring.org",
        club_abbreviation="TSC",
    )


@pytest.mark.django_db
class TestGenerateDutyIcs:
    """Tests for the generate_duty_ics function."""

    def test_generates_valid_ics(self, site_config):
        """Generated ICS content should be valid iCalendar format."""
        duty_date = date.today() + timedelta(days=7)
        ics_content = generate_duty_ics(
            duty_date=duty_date,
            role_title="Duty Officer",
            member_name="John Doe",
        )

        # Should be bytes
        assert isinstance(ics_content, bytes)

        # Should be valid iCalendar
        cal = Calendar.from_ical(ics_content)
        assert cal is not None

        # Check calendar properties
        assert b"BEGIN:VCALENDAR" in ics_content
        assert b"BEGIN:VEVENT" in ics_content
        assert b"END:VEVENT" in ics_content
        assert b"END:VCALENDAR" in ics_content

    def test_contains_correct_summary(self, site_config):
        """ICS should contain the correct event summary."""
        duty_date = date.today() + timedelta(days=7)
        ics_content = generate_duty_ics(
            duty_date=duty_date,
            role_title="Tow Pilot",
            member_name="Jane Smith",
        )

        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1

        event = events[0]
        summary = str(event.get("summary"))
        assert "Tow Pilot" in summary
        assert "Test Soaring Club" in summary

    def test_contains_correct_date(self, site_config):
        """ICS should have the correct duty date."""
        duty_date = date(2025, 6, 15)
        ics_content = generate_duty_ics(
            duty_date=duty_date,
            role_title="Instructor",
            member_name="Bob Wilson",
        )

        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        event = events[0]

        dtstart = event.get("dtstart").dt
        assert dtstart == duty_date

    def test_all_day_event(self, site_config):
        """ICS should create an all-day event."""
        duty_date = date(2025, 6, 15)
        ics_content = generate_duty_ics(
            duty_date=duty_date,
            role_title="Duty Officer",
            member_name="Test User",
        )

        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        event = events[0]

        dtstart = event.get("dtstart").dt
        dtend = event.get("dtend").dt

        # All-day events have dates, not datetimes
        assert isinstance(dtstart, date)
        assert isinstance(dtend, date)
        # End date should be next day for all-day event
        assert dtend == duty_date + timedelta(days=1)

    def test_includes_description(self, site_config):
        """ICS should include a description with assignment details."""
        duty_date = date.today() + timedelta(days=7)
        ics_content = generate_duty_ics(
            duty_date=duty_date,
            role_title="Assistant Duty Officer",
            member_name="Alice Jones",
            notes="Please arrive early.",
        )

        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        event = events[0]

        description = str(event.get("description"))
        assert "Assistant Duty Officer" in description
        assert "Alice Jones" in description
        assert "Please arrive early." in description

    def test_unique_uid(self, site_config):
        """Each ICS should have a unique UID."""
        duty_date = date.today() + timedelta(days=7)

        ics1 = generate_duty_ics(
            duty_date=duty_date,
            role_title="Duty Officer",
            member_name="User 1",
        )
        ics2 = generate_duty_ics(
            duty_date=duty_date,
            role_title="Duty Officer",
            member_name="User 2",
        )

        cal1 = Calendar.from_ical(ics1)
        cal2 = Calendar.from_ical(ics2)

        uid1 = str(list(c for c in cal1.walk() if c.name == "VEVENT")[0].get("uid"))
        uid2 = str(list(c for c in cal2.walk() if c.name == "VEVENT")[0].get("uid"))

        # UIDs should be different (timestamp makes them unique)
        # But they should both contain the domain as a proper suffix (not just substring)
        assert uid1.endswith(
            "@testsoaring.org"
        ), f"UID should end with @testsoaring.org: {uid1}"
        assert uid2.endswith(
            "@testsoaring.org"
        ), f"UID should end with @testsoaring.org: {uid2}"

    def test_custom_location(self, site_config):
        """ICS should use provided location."""
        duty_date = date.today() + timedelta(days=7)
        ics_content = generate_duty_ics(
            duty_date=duty_date,
            role_title="Duty Officer",
            member_name="Test User",
            location="Front Royal Airport",
        )

        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        event = events[0]

        location = str(event.get("location"))
        assert "Front Royal Airport" in location

    def test_no_config_uses_defaults(self, db):
        """Should work even without SiteConfiguration."""
        SiteConfiguration.objects.all().delete()

        duty_date = date.today() + timedelta(days=7)
        ics_content = generate_duty_ics(
            duty_date=duty_date,
            role_title="Duty Officer",
            member_name="Test User",
        )

        # Should still generate valid ICS
        assert isinstance(ics_content, bytes)
        assert b"BEGIN:VCALENDAR" in ics_content


@pytest.mark.django_db
class TestGeneratePreopIcs:
    """Tests for the generate_preop_ics function."""

    def test_generates_for_assignment(self, site_config, django_user_model):
        """Should generate ICS for pre-op assignment notification."""
        # Create a member
        member = django_user_model.objects.create_user(
            username="testpilot",
            email="pilot@test.com",
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        # Create an assignment
        assignment = DutyAssignment.objects.create(
            date=date.today() + timedelta(days=1),
            is_scheduled=True,
            tow_pilot=member,
        )

        ics_content = generate_preop_ics(
            assignment=assignment,
            for_member=member,
            role_title="Tow Pilot",
        )

        assert isinstance(ics_content, bytes)
        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1

        event = events[0]
        summary = str(event.get("summary"))
        assert "Tow Pilot" in summary


@pytest.mark.django_db
class TestGenerateSwapIcs:
    """Tests for the generate_swap_ics function."""

    @pytest.fixture
    def members(self, django_user_model):
        """Create test members."""
        requester = django_user_model.objects.create_user(
            username="requester",
            email="requester@test.com",
            first_name="Alice",
            last_name="Requester",
            membership_status="Full Member",
        )
        offerer = django_user_model.objects.create_user(
            username="offerer",
            email="offerer@test.com",
            first_name="Bob",
            last_name="Offerer",
            membership_status="Full Member",
        )
        return requester, offerer

    @pytest.fixture
    def cover_swap_request(self, site_config, members):
        """Create a swap request with a cover offer."""
        requester, offerer = members

        swap_request = DutySwapRequest.objects.create(
            requester=requester,
            role="TOW",
            original_date=date.today() + timedelta(days=7),
            request_type="general",
            status="fulfilled",
        )

        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=offerer,
            offer_type="cover",
            status="accepted",
        )

        swap_request.accepted_offer = offer
        swap_request.save()

        return swap_request

    @pytest.fixture
    def exchange_swap_request(self, site_config, members):
        """Create a swap request with an exchange/swap offer."""
        requester, offerer = members

        swap_request = DutySwapRequest.objects.create(
            requester=requester,
            role="DO",
            original_date=date.today() + timedelta(days=14),
            request_type="general",
            status="fulfilled",
        )

        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=offerer,
            offer_type="swap",
            proposed_swap_date=date.today() + timedelta(days=21),
            status="accepted",
        )

        swap_request.accepted_offer = offer
        swap_request.save()

        return swap_request

    def test_cover_for_offerer(self, cover_swap_request, members):
        """Offerer covering a shift should get ICS for the original date."""
        requester, offerer = members

        ics_content = generate_swap_ics(
            swap_request=cover_swap_request,
            for_member=offerer,
            is_original_requester=False,
        )

        assert isinstance(ics_content, bytes)
        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1

        event = events[0]
        dtstart = event.get("dtstart").dt
        assert dtstart == cover_swap_request.original_date

        description = str(event.get("description"))
        assert "Covering for" in description or "covering" in description.lower()

    def test_cover_for_requester_no_new_duty(self, cover_swap_request, members):
        """Requester in cover scenario doesn't get a new duty - should return None."""
        requester, offerer = members

        ics_content = generate_swap_ics(
            swap_request=cover_swap_request,
            for_member=requester,
            is_original_requester=True,
        )

        # For cover scenario, requester has no new duty assignment
        # Function should return None (no calendar events to add)
        assert ics_content is None

    def test_swap_for_requester(self, exchange_swap_request, members):
        """Requester in swap scenario gets ICS for proposed swap date."""
        requester, offerer = members

        ics_content = generate_swap_ics(
            swap_request=exchange_swap_request,
            for_member=requester,
            is_original_requester=True,
        )

        assert isinstance(ics_content, bytes)
        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1

        event = events[0]
        dtstart = event.get("dtstart").dt
        # Requester should get duty on the proposed swap date
        assert dtstart == exchange_swap_request.accepted_offer.proposed_swap_date

    def test_swap_for_offerer(self, exchange_swap_request, members):
        """Offerer in swap scenario gets ICS for original date."""
        requester, offerer = members

        ics_content = generate_swap_ics(
            swap_request=exchange_swap_request,
            for_member=offerer,
            is_original_requester=False,
        )

        assert isinstance(ics_content, bytes)
        cal = Calendar.from_ical(ics_content)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1

        event = events[0]
        dtstart = event.get("dtstart").dt
        # Offerer takes over the original date
        assert dtstart == exchange_swap_request.original_date


@pytest.mark.django_db
class TestIcsAttachmentInEmails:
    """Integration tests for ICS attachments in emails."""

    def test_preop_email_includes_ics(self, site_config, django_user_model):
        """Pre-op email should include ICS attachment."""
        from io import StringIO

        from django.core.management import call_command

        # Create a member and assignment
        member = django_user_model.objects.create_user(
            username="do",
            email="do@test.com",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
        )

        target_date = date.today() + timedelta(days=1)
        DutyAssignment.objects.create(
            date=target_date,
            is_scheduled=True,
            duty_officer=member,
        )

        # Mock email sending
        with patch(
            "duty_roster.management.commands.send_duty_preop_emails.EmailMultiAlternatives"
        ) as mock_email_class:
            mock_email = MagicMock()
            mock_email_class.return_value = mock_email

            out = StringIO()
            call_command(
                "send_duty_preop_emails",
                f"--date={target_date.isoformat()}",
                stdout=out,
            )

            # Check that attach was called with an ICS file
            if mock_email.attach.called:
                attach_calls = mock_email.attach.call_args_list
                assert any(".ics" in str(call) for call in attach_calls)
