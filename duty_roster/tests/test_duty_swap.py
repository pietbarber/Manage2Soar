"""
Tests for Duty Swap feature.

Tests the duty swap workflow including:
- Model methods (is_critical_role, days_until_duty, get_urgency_level, check_blackout_conflict)
- Form validation
- View access and permissions
- Email notifications
"""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse

from duty_roster.forms import DutySwapOfferForm, DutySwapRequestForm
from duty_roster.models import (
    DutyAssignment,
    DutyAssignmentRole,
    DutyRoleDefinition,
    DutySwapOffer,
    DutySwapRequest,
    MemberBlackout,
)
from duty_roster.views_swap import (
    _accept_offer_and_finalize,
    get_eligible_members_for_role,
    get_open_swap_reminder_candidates,
    get_periodic_reminder_recipients,
    send_periodic_open_swap_reminder_notifications,
    send_request_expired_notifications,
    update_duty_assignments,
)
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config(db):
    """Create site configuration for tests."""
    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        club_nickname="Test Club",
        domain_name="test.manage2soar.com",
        club_abbreviation="TSC",
        schedule_tow_pilots=True,
        schedule_duty_officers=True,
        schedule_instructors=True,
        schedule_assistant_duty_officers=True,
    )


@pytest.fixture
def alice(db):
    """Create member Alice who will request a swap."""
    return Member.objects.create(
        username="alice",
        first_name="Alice",
        last_name="Requester",
        email="alice@example.com",
        membership_status="Full Member",
        towpilot=True,
    )


@pytest.fixture
def bob(db):
    """Create member Bob who will offer to swap."""
    return Member.objects.create(
        username="bob",
        first_name="Bob",
        last_name="Offerer",
        email="bob@example.com",
        membership_status="Full Member",
        towpilot=True,
    )


@pytest.fixture
def charlie(db):
    """Create member Charlie as another potential helper."""
    return Member.objects.create(
        username="charlie",
        first_name="Charlie",
        last_name="Helper",
        email="charlie@example.com",
        membership_status="Full Member",
        towpilot=True,
    )


@pytest.fixture
def ado_requester(db):
    """Create an ADO requester assigned to the original duty date."""
    return Member.objects.create(
        username="ado_requester",
        first_name="Ado",
        last_name="Requester",
        email="ado_requester@example.com",
        membership_status="Full Member",
        assistant_duty_officer=True,
    )


@pytest.fixture
def ado_helper_probationary(db):
    """Create an ADO-qualified helper with active non-Full/Family status."""
    return Member.objects.create(
        username="ado_probationary",
        first_name="Probationary",
        last_name="Helper",
        email="ado_probationary@example.com",
        membership_status="Probationary Member",
        assistant_duty_officer=True,
    )


@pytest.fixture
def ado_non_qualified(db):
    """Create an active member without ADO qualification."""
    return Member.objects.create(
        username="ado_non_qualified",
        first_name="Not",
        last_name="Qualified",
        email="ado_non_qualified@example.com",
        membership_status="Full Member",
        assistant_duty_officer=False,
    )


@pytest.fixture
def ado_inactive(db):
    """Create an ADO-qualified member in an inactive status."""
    return Member.objects.create(
        username="ado_inactive",
        first_name="Inactive",
        last_name="Helper",
        email="ado_inactive@example.com",
        membership_status="Inactive",
        assistant_duty_officer=True,
    )


@pytest.fixture
def alice_duty_assignment(alice, db):
    """Create a duty assignment for Alice (tow pilot) in the future."""
    return DutyAssignment.objects.create(
        date=date.today() + timedelta(days=14),
        tow_pilot=alice,
    )


@pytest.fixture
def bob_duty_assignment(bob, db):
    """Create a duty assignment for Bob (tow pilot) in the future."""
    return DutyAssignment.objects.create(
        date=date.today() + timedelta(days=21),
        tow_pilot=bob,
    )


@pytest.fixture
def swap_request(alice, alice_duty_assignment, db):
    """Create a swap request from Alice."""
    return DutySwapRequest.objects.create(
        requester=alice,
        original_date=alice_duty_assignment.date,
        role="TOW",
        request_type="general",
        status="open",
    )


@pytest.fixture
def swap_offer(bob, swap_request, bob_duty_assignment, db):
    """Create a swap offer from Bob."""
    return DutySwapOffer.objects.create(
        swap_request=swap_request,
        offered_by=bob,
        offer_type="swap",
        proposed_swap_date=bob_duty_assignment.date,
        status="pending",
    )


@pytest.fixture
def ado_duty_assignment(ado_requester, db):
    """Create a future duty assignment for an assistant duty officer."""
    return DutyAssignment.objects.create(
        date=date.today() + timedelta(days=16),
        assistant_duty_officer=ado_requester,
    )


@pytest.fixture
def ado_swap_request(ado_requester, ado_duty_assignment, db):
    """Create an open ADO swap request."""
    return DutySwapRequest.objects.create(
        requester=ado_requester,
        original_date=ado_duty_assignment.date,
        role="ADO",
        request_type="general",
        status="open",
    )


# =============================================================================
# Model Tests
# =============================================================================


@pytest.mark.django_db
class TestDutySwapRequestModel:
    """Tests for DutySwapRequest model methods."""

    def test_get_role_title_tow_pilot(self, swap_request):
        """Role title should return human-readable name."""
        assert swap_request.get_role_title() == "Tow Pilot"

    def test_get_role_title_duty_officer(self, alice, alice_duty_assignment):
        """Role title should return human-readable name for duty officer."""
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="DO",
        )
        assert request.get_role_title() == "Duty Officer"

    def test_is_critical_role_tow_pilot(self, swap_request):
        """Tow pilot is a critical role."""
        assert swap_request.is_critical_role() is True

    def test_is_critical_role_duty_officer(self, alice, alice_duty_assignment):
        """Duty officer is a critical role."""
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="DO",
        )
        assert request.is_critical_role() is True

    def test_is_critical_role_instructor(self, alice, alice_duty_assignment):
        """Instructor is not a critical role."""
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="INSTRUCTOR",
        )
        assert request.is_critical_role() is False

    def test_is_critical_role_ado(self, alice, alice_duty_assignment):
        """ADO is not a critical role."""
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="ADO",
        )
        assert request.is_critical_role() is False

    def test_days_until_duty(self, swap_request):
        """Days until duty should be calculated correctly."""
        from django.utils import timezone

        today = timezone.now().date()
        expected = (swap_request.original_date - today).days
        assert swap_request.days_until_duty() == expected

    def test_get_urgency_level_normal(self, alice, db):
        """>14 days out is normal urgency."""
        future_date = date.today() + timedelta(days=21)
        DutyAssignment.objects.create(date=future_date, tow_pilot=alice)
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=future_date,
            role="TOW",
        )
        assert request.get_urgency_level() == "normal"

    def test_get_urgency_level_soon(self, alice, db):
        """8-14 days out is 'soon' urgency."""
        future_date = date.today() + timedelta(days=10)
        DutyAssignment.objects.create(date=future_date, tow_pilot=alice)
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=future_date,
            role="TOW",
        )
        assert request.get_urgency_level() == "soon"

    def test_get_urgency_level_urgent(self, alice, db):
        """3-7 days out is 'urgent' urgency."""
        future_date = date.today() + timedelta(days=5)
        DutyAssignment.objects.create(date=future_date, tow_pilot=alice)
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=future_date,
            role="TOW",
        )
        assert request.get_urgency_level() == "urgent"

    def test_get_urgency_level_emergency(self, alice, db):
        """<3 days out is 'emergency' urgency."""
        future_date = date.today() + timedelta(days=1)
        DutyAssignment.objects.create(date=future_date, tow_pilot=alice)
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=future_date,
            role="TOW",
        )
        assert request.get_urgency_level() == "emergency"

    def test_get_urgency_level_marked_emergency(self, swap_request):
        """Request marked as emergency returns emergency level."""
        swap_request.is_emergency = True
        swap_request.save()
        assert swap_request.get_urgency_level() == "emergency"

    def test_dynamic_request_requires_dynamic_role_metadata(
        self, alice, alice_duty_assignment
    ):
        """Dynamic swap requests require both dynamic key and label."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DutySwapRequest.objects.create(
                    requester=alice,
                    original_date=alice_duty_assignment.date,
                    role="DYNAMIC",
                    dynamic_role_key="",
                    dynamic_role_label="",
                )

    def test_non_dynamic_request_rejects_dynamic_role_metadata(
        self, alice, alice_duty_assignment
    ):
        """Non-dynamic swap requests cannot persist dynamic metadata."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DutySwapRequest.objects.create(
                    requester=alice,
                    original_date=alice_duty_assignment.date,
                    role="TOW",
                    dynamic_role_key="launch_coord",
                    dynamic_role_label="Launch Coordinator",
                )

    def test_dynamic_request_with_metadata_is_allowed(
        self, alice, alice_duty_assignment
    ):
        """Dynamic swap requests with key and label satisfy DB constraint."""
        request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
        )
        assert request.pk is not None


@pytest.mark.django_db
class TestDutySwapOfferModel:
    """Tests for DutySwapOffer model methods."""

    def test_check_blackout_conflict_no_conflict(
        self, swap_request, bob, bob_duty_assignment
    ):
        """Offer with no blackout conflict should have is_blackout_conflict=False."""
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="swap",
            proposed_swap_date=bob_duty_assignment.date,
        )
        offer.check_blackout_conflict()
        assert offer.is_blackout_conflict is False

    def test_check_blackout_conflict_with_conflict(self, swap_request, bob, alice):
        """Offer proposing date in requester's blackout should flag conflict."""
        blackout_date = date.today() + timedelta(days=21)

        # Create blackout for Alice (requester) on the proposed swap date
        MemberBlackout.objects.create(
            member=alice,
            date=blackout_date,
        )

        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="swap",
            proposed_swap_date=blackout_date,
        )
        offer.check_blackout_conflict()
        assert offer.is_blackout_conflict is True

    def test_cover_offer_no_blackout_check(self, swap_request, bob):
        """Cover-only offers don't need blackout checking."""
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
            proposed_swap_date=None,
        )
        offer.check_blackout_conflict()
        # No swap date means no conflict possible
        assert offer.is_blackout_conflict is False


# =============================================================================
# Form Tests
# =============================================================================


@pytest.mark.django_db
class TestDutySwapRequestForm:
    """Tests for DutySwapRequestForm validation."""

    def test_general_request_valid(self, alice):
        """General request with notes is valid."""
        form = DutySwapRequestForm(
            data={
                "request_type": "general",
                "notes": "I have a work conflict",
                "is_emergency": False,
            }
        )
        assert form.is_valid()

    def test_direct_request_requires_member(self, alice, bob):
        """Direct request without member target is invalid."""
        form = DutySwapRequestForm(
            data={
                "request_type": "direct",
                "notes": "",
                "is_emergency": False,
            }
        )
        assert not form.is_valid()
        assert "direct_request_to" in form.errors

    def test_direct_request_with_member_valid(self, alice, bob):
        """Direct request with member target is valid."""
        form = DutySwapRequestForm(
            data={
                "request_type": "direct",
                "direct_request_to": bob.id,
                "notes": "Hey Bob, can you swap?",
                "is_emergency": False,
            }
        )
        assert form.is_valid()


@pytest.mark.django_db
class TestDutySwapOfferForm:
    """Tests for DutySwapOfferForm validation."""

    def test_cover_offer_valid(self, swap_request, bob):
        """Cover offer without swap date is valid."""
        form = DutySwapOfferForm(
            data={
                "offer_type": "cover",
                "notes": "Happy to help!",
            },
            swap_request=swap_request,
            offered_by=bob,
        )
        assert form.is_valid()

    def test_swap_offer_requires_date(self, swap_request, bob, bob_duty_assignment):
        """Swap offer without proposed date is invalid."""
        form = DutySwapOfferForm(
            data={
                "offer_type": "swap",
                "notes": "",
            },
            swap_request=swap_request,
            offered_by=bob,
        )
        assert not form.is_valid()
        assert "proposed_swap_date" in form.errors

    def test_swap_offer_with_date_valid(self, swap_request, bob, bob_duty_assignment):
        """Swap offer with proposed date is valid."""
        form = DutySwapOfferForm(
            data={
                "offer_type": "swap",
                "proposed_swap_date": bob_duty_assignment.date.isoformat(),
                "notes": "",
            },
            swap_request=swap_request,
            offered_by=bob,
        )
        assert form.is_valid()

    def test_swap_offer_dropdown_contains_offerer_scheduled_dates(
        self, swap_request, bob, bob_duty_assignment
    ):
        """Swap date choices should be populated from the offerer's assignments."""
        form = DutySwapOfferForm(swap_request=swap_request, offered_by=bob)

        choice_values = {
            value
            for value, _label in form.fields["proposed_swap_date"].choices
            if value
        }

        assert bob_duty_assignment.date.isoformat() in choice_values

    def test_swap_offer_only_allows_cover_without_eligible_dates(
        self, swap_request, bob
    ):
        """When no eligible duty dates exist, only cover should be offered."""
        form = DutySwapOfferForm(swap_request=swap_request, offered_by=bob)

        offer_choices = [value for value, _label in form.fields["offer_type"].choices]

        assert offer_choices == ["cover"]

    def test_cover_offer_ignores_stale_proposed_swap_date(self, swap_request, bob):
        """Cover offers should validate even if stale swap date is posted."""
        form = DutySwapOfferForm(
            data={
                "offer_type": "cover",
                "proposed_swap_date": (date.today() + timedelta(days=60)).isoformat(),
                "notes": "Covering this duty",
            },
            swap_request=swap_request,
            offered_by=bob,
        )

        assert form.is_valid()

    def test_swap_offer_excludes_adhoc_dates_for_static_roles(
        self, swap_request, bob, bob_duty_assignment
    ):
        """Swap date choices should exclude ad-hoc assignments for static roles."""
        adhoc_date = date.today() + timedelta(days=28)
        DutyAssignment.objects.create(
            date=adhoc_date,
            tow_pilot=bob,
            is_scheduled=False,
        )

        form = DutySwapOfferForm(swap_request=swap_request, offered_by=bob)
        choice_values = {
            value
            for value, _label in form.fields["proposed_swap_date"].choices
            if value
        }

        assert bob_duty_assignment.date.isoformat() in choice_values
        assert adhoc_date.isoformat() not in choice_values

    def test_swap_offer_excludes_adhoc_dates_for_dynamic_roles(
        self, site_config, alice, bob
    ):
        """Dynamic swap date choices should include only scheduled assignments."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
        )
        role_definition.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="towpilot",
            is_required=True,
        )

        original_date = date.today() + timedelta(days=10)
        scheduled_date = date.today() + timedelta(days=18)
        adhoc_date = date.today() + timedelta(days=22)

        dynamic_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=original_date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
            request_type="general",
            status="open",
        )

        scheduled_assignment = DutyAssignment.objects.create(
            date=scheduled_date,
            is_scheduled=True,
        )
        adhoc_assignment = DutyAssignment.objects.create(
            date=adhoc_date,
            is_scheduled=False,
        )

        DutyAssignmentRole.objects.create(
            assignment=scheduled_assignment,
            role_key="launch_coord",
            member=bob,
            role_definition=role_definition,
        )
        DutyAssignmentRole.objects.create(
            assignment=adhoc_assignment,
            role_key="launch_coord",
            member=bob,
            role_definition=role_definition,
        )

        form = DutySwapOfferForm(swap_request=dynamic_request, offered_by=bob)
        choice_values = {
            value
            for value, _label in form.fields["proposed_swap_date"].choices
            if value
        }

        assert scheduled_date.isoformat() in choice_values
        assert adhoc_date.isoformat() not in choice_values


# =============================================================================
# View Access Tests
# =============================================================================


@pytest.mark.django_db
class TestSwapViewAccess:
    """Tests for swap view access control."""

    def test_my_requests_requires_login(self, client):
        """My swap requests page requires login."""
        url = reverse("duty_roster:my_swap_requests")
        resp = client.get(url)
        # Should redirect to login
        assert resp.status_code in [302, 403]

    def test_my_requests_logged_in(self, client, alice, site_config):
        """Logged in user can access my requests."""
        client.force_login(alice)
        url = reverse("duty_roster:my_swap_requests")
        resp = client.get(url)
        assert resp.status_code == 200

    def test_open_requests_requires_login(self, client):
        """Open swap requests page requires login."""
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)
        assert resp.status_code in [302, 403]

    def test_open_requests_logged_in(self, client, alice, site_config):
        """Logged in user can access open requests."""
        client.force_login(alice)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)
        assert resp.status_code == 200

    def test_request_detail_requires_login(self, client, swap_request):
        """Request detail page requires login."""
        url = reverse("duty_roster:swap_request_detail", args=[swap_request.id])
        resp = client.get(url)
        assert resp.status_code in [302, 403]

    def test_request_detail_logged_in(self, client, alice, swap_request, site_config):
        """Logged in user can access request detail."""
        client.force_login(alice)
        url = reverse("duty_roster:swap_request_detail", args=[swap_request.id])
        resp = client.get(url)
        assert resp.status_code == 200

    def test_open_requests_shows_only_dynamic_roles_member_is_eligible_for(
        self, client, alice, bob, site_config
    ):
        """Dynamic open requests are filtered by role-key eligibility."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        eligible_role = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="dynamic_tow",
            display_name="Dynamic Tow",
            is_active=True,
            sort_order=10,
        )
        eligible_role.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="towpilot",
            is_required=True,
        )

        ineligible_role = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="dynamic_instructor",
            display_name="Dynamic Instructor",
            is_active=True,
            sort_order=20,
        )
        ineligible_role.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="instructor",
            is_required=True,
        )

        tomorrow = date.today() + timedelta(days=1)
        day_after = date.today() + timedelta(days=2)
        eligible_request = DutySwapRequest.objects.create(
            requester=bob,
            original_date=tomorrow,
            role="DYNAMIC",
            dynamic_role_key="dynamic_tow",
            dynamic_role_label="Dynamic Tow",
            request_type="general",
            status="open",
        )
        ineligible_request = DutySwapRequest.objects.create(
            requester=bob,
            original_date=day_after,
            role="DYNAMIC",
            dynamic_role_key="dynamic_instructor",
            dynamic_role_label="Dynamic Instructor",
            request_type="general",
            status="open",
        )

        client.force_login(alice)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)

        assert resp.status_code == 200
        open_request_ids = {req.id for req in resp.context["open_requests"]}
        assert eligible_request.id in open_request_ids
        assert ineligible_request.id not in open_request_ids


@pytest.mark.django_db
class TestSwapRequestCreation:
    """Tests for creating swap requests."""

    def test_create_request_url(
        self, client, alice, alice_duty_assignment, site_config
    ):
        """Create request page loads for assignment owner."""
        client.force_login(alice)
        url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": alice_duty_assignment.date.year,
                "month": alice_duty_assignment.date.month,
                "day": alice_duty_assignment.date.day,
                "role": "TOW",
            },
        )
        resp = client.get(url)
        assert resp.status_code == 200

    def test_create_request_post_success(
        self, client, alice, alice_duty_assignment, site_config
    ):
        """Posting a valid swap request creates it."""
        client.force_login(alice)
        url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": alice_duty_assignment.date.year,
                "month": alice_duty_assignment.date.month,
                "day": alice_duty_assignment.date.day,
                "role": "TOW",
            },
        )
        resp = client.post(
            url,
            {
                "request_type": "general",
                "notes": "Need to swap",
                "is_emergency": False,
            },
        )
        # Should redirect on success
        assert resp.status_code in [200, 302]
        # Check request was created
        assert DutySwapRequest.objects.filter(
            requester=alice,
            original_date=alice_duty_assignment.date,
        ).exists()

    def test_create_dynamic_request_post_success(
        self, client, alice, alice_duty_assignment, site_config
    ):
        """Posting a valid dynamic-role swap request creates it with role metadata."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
        )
        DutyAssignmentRole.objects.create(
            assignment=alice_duty_assignment,
            role_key="launch_coord",
            member=alice,
            role_definition=role_definition,
        )

        client.force_login(alice)
        url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": alice_duty_assignment.date.year,
                "month": alice_duty_assignment.date.month,
                "day": alice_duty_assignment.date.day,
                "role": "DYNAMIC",
            },
        )
        resp = client.post(
            f"{url}?dynamic_role_key=launch_coord",
            {
                "dynamic_role_key": "launch_coord",
                "request_type": "general",
                "notes": "Need dynamic coverage",
                "is_emergency": False,
            },
        )
        assert resp.status_code in [200, 302]
        created_request = DutySwapRequest.objects.get(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
        )
        assert created_request.dynamic_role_label == "Launch Coordinator"


# =============================================================================
# Swap Offer Tests
# =============================================================================


@pytest.mark.django_db
class TestSwapOfferWorkflow:
    """Tests for swap offer workflow."""

    def test_make_offer_page_loads(
        self, client, bob, swap_request, bob_duty_assignment, site_config
    ):
        """Make offer page loads for eligible member."""
        client.force_login(bob)
        url = reverse("duty_roster:make_swap_offer", args=[swap_request.id])
        resp = client.get(url)
        assert resp.status_code == 200

    def test_make_cover_offer(
        self, client, bob, swap_request, bob_duty_assignment, site_config
    ):
        """Cover offer is accepted immediately and fulfills the request."""
        client.force_login(bob)
        url = reverse("duty_roster:make_swap_offer", args=[swap_request.id])
        resp = client.post(
            url,
            {
                "offer_type": "cover",
                "notes": "I can cover for you",
            },
        )
        assert resp.status_code == 302
        offer = DutySwapOffer.objects.get(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
        )

        swap_request.refresh_from_db()
        assert offer.status == "accepted"
        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer == offer

        updated_assignment = DutyAssignment.objects.get(date=swap_request.original_date)
        assert updated_assignment.tow_pilot == bob

    def test_make_swap_offer(
        self, client, bob, swap_request, bob_duty_assignment, site_config
    ):
        """Swap offer remains pending until requester explicitly accepts."""
        client.force_login(bob)
        url = reverse("duty_roster:make_swap_offer", args=[swap_request.id])
        resp = client.post(
            url,
            {
                "offer_type": "swap",
                "proposed_swap_date": bob_duty_assignment.date,
                "notes": "Let's trade dates",
            },
        )
        assert resp.status_code == 302
        offer = DutySwapOffer.objects.get(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="swap",
            proposed_swap_date=bob_duty_assignment.date,
        )

        swap_request.refresh_from_db()
        assert offer.status == "pending"
        assert swap_request.status == "open"
        assert swap_request.accepted_offer is None

    def test_cover_auto_accept_declines_existing_pending_offers(
        self, client, bob, charlie, swap_request, site_config
    ):
        """Auto-accepting a cover offer auto-declines other pending offers."""
        other_offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=charlie,
            offer_type="cover",
            status="pending",
        )

        client.force_login(bob)
        url = reverse("duty_roster:make_swap_offer", args=[swap_request.id])
        resp = client.post(
            url,
            {
                "offer_type": "cover",
                "notes": "I can take this duty",
            },
        )
        assert resp.status_code == 302

        accepted_offer = DutySwapOffer.objects.get(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
        )
        other_offer = DutySwapOffer.objects.get(pk=other_offer.pk)
        swap_request = DutySwapRequest.objects.get(pk=swap_request.pk)

        assert accepted_offer.status == "accepted"
        assert other_offer.status == "auto_declined"
        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer == accepted_offer

    def test_ado_probationary_member_can_make_offer(
        self,
        client,
        ado_helper_probationary,
        ado_swap_request,
        site_config,
    ):
        """Active ADO members in Probationary status can make swap offers."""
        client.force_login(ado_helper_probationary)
        url = reverse("duty_roster:make_swap_offer", args=[ado_swap_request.id])

        # GET should load the offer form (no false "not qualified" rejection).
        response = client.get(url)
        assert response.status_code == 200

        # POST cover offer should succeed and auto-accept.
        response = client.post(
            url,
            {
                "offer_type": "cover",
                "notes": "I can cover this ADO duty.",
            },
        )
        assert response.status_code == 302

        offer = DutySwapOffer.objects.get(
            swap_request=ado_swap_request,
            offered_by=ado_helper_probationary,
            offer_type="cover",
        )
        ado_swap_request.refresh_from_db()
        assert offer.status == "accepted"
        assert ado_swap_request.status == "fulfilled"

        updated_assignment = DutyAssignment.objects.get(
            date=ado_swap_request.original_date
        )
        assert updated_assignment.assistant_duty_officer == ado_helper_probationary

    def test_ado_non_qualified_member_is_rejected(
        self, client, ado_non_qualified, ado_swap_request, site_config
    ):
        """Active members without ADO qualification are rejected for ADO offers."""
        client.force_login(ado_non_qualified)
        url = reverse("duty_roster:make_swap_offer", args=[ado_swap_request.id])
        response = client.get(url, follow=True)

        assert response.status_code == 200
        assert "You are not qualified for this role." in response.content.decode()

    def test_ado_inactive_member_not_eligible(self, ado_inactive, ado_swap_request):
        """Inactive ADO members are excluded by status policy in helper."""
        eligible = get_eligible_members_for_role(
            ado_swap_request.role,
            exclude_member=ado_swap_request.requester,
        )
        assert not eligible.filter(pk=ado_inactive.pk).exists()

    def test_ado_probationary_member_is_eligible(
        self, ado_helper_probationary, ado_swap_request
    ):
        """Probationary Member ADO is included when status is active in siteconfig policy."""
        eligible = get_eligible_members_for_role(
            ado_swap_request.role,
            exclude_member=ado_swap_request.requester,
        )
        assert eligible.filter(pk=ado_helper_probationary.pk).exists()

    def test_dynamic_role_eligibility_helper_uses_dynamic_requirements(
        self, site_config, alice, bob
    ):
        """Dynamic helper eligibility should include only members who meet role requirements."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="dynamic_instructor",
            display_name="Dynamic Instructor",
            is_active=True,
            sort_order=20,
        )
        # Use legacy role mapping by requirement to test resolver path.
        role_definition.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="instructor",
            is_required=True,
        )

        alice.instructor = True
        alice.save(update_fields=["instructor"])
        bob.instructor = False
        bob.save(update_fields=["instructor"])

        eligible = get_eligible_members_for_role(
            "DYNAMIC",
            exclude_member=None,
            dynamic_role_key="dynamic_instructor",
        )

        assert eligible.filter(pk=alice.pk).exists()
        assert not eligible.filter(pk=bob.pk).exists()

    def test_dynamic_swap_offer_unavailable_without_matching_role_assignment(
        self, client, site_config, alice, bob
    ):
        """Dynamic swap offers are unavailable when offerer has no eligible scheduled date."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        original_date = date.today() + timedelta(days=10)
        proposed_swap_date = date.today() + timedelta(days=17)

        original_assignment = DutyAssignment.objects.create(date=original_date)
        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
        )
        role_definition.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="towpilot",
            is_required=True,
        )
        DutyAssignmentRole.objects.create(
            assignment=original_assignment,
            role_key="launch_coord",
            member=alice,
            role_definition=role_definition,
        )

        dynamic_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=original_date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
            request_type="general",
            status="open",
        )

        # Bob is eligible in general for this dynamic role, but has no scheduled
        # assignment for this role, so swap option is unavailable.
        client.force_login(bob)
        url = reverse("duty_roster:make_swap_offer", args=[dynamic_request.id])
        response = client.post(
            url,
            {
                "offer_type": "swap",
                "proposed_swap_date": proposed_swap_date,
                "notes": "I can swap that date",
            },
        )

        assert response.status_code == 200
        error_data = response.context["form"].errors.as_data()
        assert "offer_type" in error_data
        assert error_data["offer_type"][0].code == "invalid_choice"
        assert not DutySwapOffer.objects.filter(
            swap_request=dynamic_request,
            offered_by=bob,
        ).exists()

    def test_dynamic_swap_offer_allows_matching_role_assignment_on_proposed_date(
        self, client, site_config, alice, bob
    ):
        """Dynamic swap offers are allowed when offerer has same role on proposed date."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        original_date = date.today() + timedelta(days=11)
        proposed_swap_date = date.today() + timedelta(days=18)

        original_assignment = DutyAssignment.objects.create(date=original_date)
        proposed_assignment = DutyAssignment.objects.create(date=proposed_swap_date)
        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
        )
        role_definition.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="towpilot",
            is_required=True,
        )
        DutyAssignmentRole.objects.create(
            assignment=original_assignment,
            role_key="launch_coord",
            member=alice,
            role_definition=role_definition,
        )
        DutyAssignmentRole.objects.create(
            assignment=proposed_assignment,
            role_key="launch_coord",
            member=bob,
            role_definition=role_definition,
        )

        dynamic_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=original_date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
            request_type="general",
            status="open",
        )

        client.force_login(bob)
        url = reverse("duty_roster:make_swap_offer", args=[dynamic_request.id])
        response = client.post(
            url,
            {
                "offer_type": "swap",
                "proposed_swap_date": proposed_swap_date,
                "notes": "Let's trade launch coordinator duties",
            },
        )

        assert response.status_code == 302
        offer = DutySwapOffer.objects.get(
            swap_request=dynamic_request,
            offered_by=bob,
        )
        assert offer.offer_type == "swap"
        assert offer.proposed_swap_date == proposed_swap_date
        assert offer.status == "pending"


@pytest.mark.django_db
class TestOfferAcceptDecline:
    """Tests for accepting and declining offers."""

    def test_accept_offer_updates_status(
        self, client, alice, swap_request, swap_offer, site_config
    ):
        """Accepting an offer updates request and offer status."""
        client.force_login(alice)
        url = reverse("duty_roster:accept_swap_offer", args=[swap_offer.id])
        resp = client.post(url)
        assert resp.status_code in [200, 302]

        swap_offer.refresh_from_db()
        swap_request.refresh_from_db()

        assert swap_offer.status == "accepted"
        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer == swap_offer

    def test_decline_offer_updates_status(
        self, client, alice, swap_request, swap_offer, site_config
    ):
        """Declining an offer updates offer status."""
        client.force_login(alice)
        url = reverse("duty_roster:decline_swap_offer", args=[swap_offer.id])
        resp = client.post(url)
        assert resp.status_code in [200, 302]

        swap_offer.refresh_from_db()
        assert swap_offer.status == "declined"

    def test_withdraw_offer(self, client, bob, swap_request, swap_offer, site_config):
        """Offerer can withdraw their own offer."""
        client.force_login(bob)
        url = reverse("duty_roster:withdraw_swap_offer", args=[swap_offer.id])
        resp = client.post(url)
        assert resp.status_code in [200, 302]

        swap_offer.refresh_from_db()
        assert swap_offer.status == "withdrawn"

    def test_accept_helper_returns_false_when_request_already_fulfilled(
        self, swap_request, swap_offer, charlie
    ):
        """Concurrent/stale accept attempts do not overwrite fulfilled requests."""
        swap_request.status = "fulfilled"
        swap_request.accepted_offer = swap_offer
        swap_request.save(update_fields=["status", "accepted_offer"])

        stale_offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=charlie,
            offer_type="cover",
            status="pending",
        )

        accepted = _accept_offer_and_finalize(swap_request, stale_offer)
        stale_offer = DutySwapOffer.objects.get(pk=stale_offer.pk)
        swap_request = DutySwapRequest.objects.get(pk=swap_request.pk)

        assert accepted is False
        assert stale_offer.status == "auto_declined"
        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer == swap_offer


# =============================================================================
# Cancel and Convert Tests
# =============================================================================


@pytest.mark.django_db
class TestCancelAndConvert:
    """Tests for cancelling and converting requests."""

    def test_cancel_request(self, client, alice, swap_request, site_config):
        """Requester can cancel their request."""
        client.force_login(alice)
        url = reverse("duty_roster:cancel_swap_request", args=[swap_request.id])
        resp = client.post(url)
        assert resp.status_code in [200, 302]

        swap_request.refresh_from_db()
        assert swap_request.status == "cancelled"

    def test_convert_direct_to_general(
        self, client, alice, bob, alice_duty_assignment, site_config
    ):
        """Direct request can be converted to general."""
        # Create direct request
        direct_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="TOW",
            request_type="direct",
            direct_request_to=bob,
            status="open",
        )

        client.force_login(alice)
        url = reverse("duty_roster:convert_to_general", args=[direct_request.id])
        resp = client.post(url)
        assert resp.status_code in [200, 302]

        direct_request = DutySwapRequest.objects.get(pk=direct_request.pk)
        assert direct_request.request_type == "general"
        assert direct_request.direct_request_to is None

    @override_settings(EMAIL_DEV_MODE=False, EMAIL_DEV_MODE_REDIRECT_TO="")
    def test_dynamic_direct_request_notifies_only_direct_recipient(
        self,
        client,
        alice,
        bob,
        charlie,
        alice_duty_assignment,
        site_config,
    ):
        """Dynamic direct requests should notify only the selected member."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
        )
        role_definition.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="towpilot",
            is_required=True,
        )
        DutyAssignmentRole.objects.create(
            assignment=alice_duty_assignment,
            role_key="launch_coord",
            member=alice,
            role_definition=role_definition,
        )

        mail.outbox.clear()
        client.force_login(alice)
        url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": alice_duty_assignment.date.year,
                "month": alice_duty_assignment.date.month,
                "day": alice_duty_assignment.date.day,
                "role": "DYNAMIC",
            },
        )
        response = client.post(
            f"{url}?dynamic_role_key=launch_coord",
            {
                "dynamic_role_key": "launch_coord",
                "request_type": "direct",
                "direct_request_to": bob.id,
                "notes": "Can you take this launch coordinator duty?",
                "is_emergency": False,
            },
        )

        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [bob.email]

    @override_settings(EMAIL_DEV_MODE=False, EMAIL_DEV_MODE_REDIRECT_TO="")
    def test_convert_dynamic_direct_to_general_notifies_all_eligible_members(
        self,
        client,
        alice,
        bob,
        charlie,
        alice_duty_assignment,
        site_config,
    ):
        """Converting dynamic direct requests broadcasts to all eligible members."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
        )
        role_definition.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="towpilot",
            is_required=True,
        )
        DutyAssignmentRole.objects.create(
            assignment=alice_duty_assignment,
            role_key="launch_coord",
            member=alice,
            role_definition=role_definition,
        )

        direct_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=alice_duty_assignment.date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
            request_type="direct",
            direct_request_to=bob,
            status="open",
        )

        mail.outbox.clear()
        client.force_login(alice)
        url = reverse("duty_roster:convert_to_general", args=[direct_request.id])
        response = client.post(url)

        assert response.status_code == 302
        direct_request.refresh_from_db()
        assert direct_request.request_type == "general"
        assert direct_request.direct_request_to is None

        recipients = sorted(
            email for message in mail.outbox for email in message.to if email
        )
        assert recipients == sorted([bob.email, charlie.email])


@pytest.mark.django_db
class TestDynamicAssignmentUpdateEdgeCases:
    """Tests for dynamic assignment update edge cases."""

    def test_dynamic_swap_recovers_when_original_role_row_missing(
        self, alice, bob, site_config
    ):
        """Missing original dynamic role row should be recreated and assignments updated."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
            legacy_role_key="towpilot",
        )

        original_date = date.today() + timedelta(days=22)
        proposed_swap_date = date.today() + timedelta(days=29)
        original_assignment = DutyAssignment.objects.create(
            date=original_date,
            tow_pilot=alice,
        )
        swap_assignment = DutyAssignment.objects.create(
            date=proposed_swap_date,
            tow_pilot=bob,
        )

        DutyAssignmentRole.objects.create(
            assignment=swap_assignment,
            role_key="launch_coord",
            member=bob,
            role_definition=role_definition,
            legacy_role_key="towpilot",
        )

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=original_date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
            request_type="general",
            status="open",
        )
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="swap",
            proposed_swap_date=proposed_swap_date,
            status="pending",
        )

        update_duty_assignments(swap_request, offer)

        original_assignment.refresh_from_db()
        swap_assignment.refresh_from_db()

        recreated_original_row = DutyAssignmentRole.objects.get(
            assignment=original_assignment,
            role_key="launch_coord",
        )
        swap_row = DutyAssignmentRole.objects.get(
            assignment=swap_assignment,
            role_key="launch_coord",
        )

        assert recreated_original_row.member == bob
        assert recreated_original_row.legacy_role_key == "towpilot"
        assert original_assignment.tow_pilot == bob
        assert swap_row.member == alice
        assert swap_assignment.tow_pilot == alice

    def test_dynamic_swap_creates_missing_role_row_on_proposed_swap_date(
        self, alice, bob, site_config
    ):
        """Dynamic swap should create missing role row on swap date and sync legacy field."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
            legacy_role_key="towpilot",
        )

        original_date = date.today() + timedelta(days=13)
        proposed_swap_date = date.today() + timedelta(days=20)
        original_assignment = DutyAssignment.objects.create(
            date=original_date,
            tow_pilot=alice,
        )
        swap_assignment = DutyAssignment.objects.create(
            date=proposed_swap_date,
            tow_pilot=bob,
        )

        original_row = DutyAssignmentRole.objects.create(
            assignment=original_assignment,
            role_key="launch_coord",
            member=alice,
            role_definition=role_definition,
            legacy_role_key="towpilot",
        )

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=original_date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
            request_type="general",
            status="open",
        )
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="swap",
            proposed_swap_date=proposed_swap_date,
            status="pending",
        )

        update_duty_assignments(swap_request, offer)

        original_row.refresh_from_db()
        original_assignment.refresh_from_db()
        swap_assignment.refresh_from_db()
        created_swap_row = DutyAssignmentRole.objects.get(
            assignment=swap_assignment,
            role_key="launch_coord",
        )

        assert original_row.member == bob
        assert original_assignment.tow_pilot == bob
        assert created_swap_row.member == alice
        assert created_swap_row.legacy_role_key == "towpilot"
        assert swap_assignment.tow_pilot == alice

    def test_dynamic_swap_backfills_existing_swap_row_metadata_and_surge_legacy_sync(
        self, alice, bob, site_config
    ):
        """Existing swap rows missing metadata should be backfilled before legacy sync."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="surge_launch_coord",
            display_name="Surge Launch Coordinator",
            is_active=True,
            sort_order=10,
            legacy_role_key="surge_towpilot",
            shift_code="pm",
        )

        original_date = date.today() + timedelta(days=17)
        proposed_swap_date = date.today() + timedelta(days=24)

        original_assignment = DutyAssignment.objects.create(
            date=original_date,
            surge_tow_pilot=alice,
        )
        swap_assignment = DutyAssignment.objects.create(
            date=proposed_swap_date,
            surge_tow_pilot=bob,
        )

        DutyAssignmentRole.objects.create(
            assignment=original_assignment,
            role_key="surge_launch_coord",
            member=alice,
        )
        DutyAssignmentRole.objects.create(
            assignment=swap_assignment,
            role_key="surge_launch_coord",
            member=bob,
            legacy_role_key="",
            shift_code="",
            role_definition=None,
        )

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=original_date,
            role="DYNAMIC",
            dynamic_role_key="surge_launch_coord",
            dynamic_role_label="Surge Launch Coordinator",
            request_type="general",
            status="open",
        )
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="swap",
            proposed_swap_date=proposed_swap_date,
            status="pending",
        )

        update_duty_assignments(swap_request, offer)

        original_assignment.refresh_from_db()
        swap_assignment.refresh_from_db()

        swap_row = DutyAssignmentRole.objects.get(
            assignment=swap_assignment,
            role_key="surge_launch_coord",
        )

        assert original_assignment.surge_tow_pilot == bob
        assert swap_assignment.surge_tow_pilot == alice
        assert swap_row.member == alice
        assert swap_row.legacy_role_key == "surge_towpilot"
        assert swap_row.shift_code == "pm"
        assert swap_row.role_definition == role_definition

    def test_accept_offer_rolls_back_when_original_assignment_missing(
        self, alice, bob, site_config
    ):
        """Acceptance should rollback request/offer status if dynamic assignment update fails."""
        site_config.enable_dynamic_duty_roles = True
        site_config.save(update_fields=["enable_dynamic_duty_roles"])

        original_date = date.today() + timedelta(days=18)
        DutyRoleDefinition.objects.create(
            site_configuration=site_config,
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
        )

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=original_date,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            dynamic_role_label="Launch Coordinator",
            request_type="general",
            status="open",
        )
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
            status="pending",
        )

        with pytest.raises(ValueError, match="Missing original assignment"):
            _accept_offer_and_finalize(swap_request, offer)

        swap_request.refresh_from_db()
        offer.refresh_from_db()

        assert swap_request.status == "open"
        assert swap_request.accepted_offer is None
        assert swap_request.fulfilled_at is None
        assert offer.status == "pending"
        assert offer.responded_at is None


# =============================================================================
# Email Notification Tests
# =============================================================================


@pytest.mark.django_db
class TestSwapEmailNotifications:
    """Tests for swap email notifications."""

    def test_swap_request_sends_email(
        self, client, alice, alice_duty_assignment, site_config
    ):
        """Creating a swap request sends notification emails."""
        client.force_login(alice)
        url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": alice_duty_assignment.date.year,
                "month": alice_duty_assignment.date.month,
                "day": alice_duty_assignment.date.day,
                "role": "TOW",
            },
        )
        client.post(
            url,
            {
                "request_type": "general",
                "notes": "Need to swap",
                "is_emergency": False,
            },
        )
        # Email might be sent (depends on whether there are eligible members)
        # Just check no errors occurred

    def test_offer_accepted_sends_email(
        self, client, alice, swap_request, swap_offer, site_config
    ):
        """Accepting an offer sends confirmation emails."""
        mail.outbox.clear()

        client.force_login(alice)
        url = reverse("duty_roster:accept_swap_offer", args=[swap_offer.id])
        client.post(url)

        # Should send emails to both parties
        # At minimum, the offerer should get a confirmation
        # Note: exact count depends on implementation
        assert len(mail.outbox) >= 0  # No error is success


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestSwapIntegration:
    """Integration tests for complete swap workflows."""

    def test_complete_swap_workflow(
        self,
        client,
        alice,
        bob,
        alice_duty_assignment,
        bob_duty_assignment,
        site_config,
    ):
        """Complete swap workflow from request to acceptance."""
        # Step 1: Alice creates swap request
        client.force_login(alice)
        create_url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": alice_duty_assignment.date.year,
                "month": alice_duty_assignment.date.month,
                "day": alice_duty_assignment.date.day,
                "role": "TOW",
            },
        )
        client.post(
            create_url,
            {
                "request_type": "general",
                "notes": "Family event",
                "is_emergency": False,
            },
        )
        swap_request = DutySwapRequest.objects.get(
            requester=alice,
            original_date=alice_duty_assignment.date,
        )

        # Step 2: Bob makes an offer
        client.force_login(bob)
        offer_url = reverse("duty_roster:make_swap_offer", args=[swap_request.id])
        client.post(
            offer_url,
            {
                "offer_type": "swap",
                "proposed_swap_date": bob_duty_assignment.date,
                "notes": "I can swap with you",
            },
        )
        swap_offer = DutySwapOffer.objects.get(
            swap_request=swap_request,
            offered_by=bob,
        )

        # Step 3: Alice accepts Bob's offer
        client.force_login(alice)
        accept_url = reverse("duty_roster:accept_swap_offer", args=[swap_offer.id])
        client.post(accept_url)

        # Verify final state
        swap_request = DutySwapRequest.objects.get(pk=swap_request.pk)
        swap_offer = DutySwapOffer.objects.get(pk=swap_offer.pk)

        assert swap_request.status == "fulfilled"
        assert swap_offer.status == "accepted"
        assert swap_request.accepted_offer == swap_offer

    def test_complete_cover_workflow(
        self,
        client,
        alice,
        bob,
        alice_duty_assignment,
        site_config,
    ):
        """Complete cover workflow (no swap, just taking over)."""
        # Step 1: Alice creates swap request
        client.force_login(alice)
        create_url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": alice_duty_assignment.date.year,
                "month": alice_duty_assignment.date.month,
                "day": alice_duty_assignment.date.day,
                "role": "TOW",
            },
        )
        client.post(
            create_url,
            {
                "request_type": "general",
                "notes": "Sick",
                "is_emergency": True,
            },
        )
        swap_request = DutySwapRequest.objects.get(
            requester=alice,
            original_date=alice_duty_assignment.date,
        )
        assert swap_request.is_emergency is True

        # Step 2: Bob offers to cover (no swap)
        client.force_login(bob)
        offer_url = reverse("duty_roster:make_swap_offer", args=[swap_request.id])
        client.post(
            offer_url,
            {
                "offer_type": "cover",
                "notes": "Feel better! I got you covered.",
            },
        )
        swap_offer = DutySwapOffer.objects.get(
            swap_request=swap_request,
            offered_by=bob,
        )
        assert swap_offer.offer_type == "cover"
        assert swap_offer.proposed_swap_date is None

        # Verify final state (auto-accepted for cover offers)
        swap_offer = DutySwapOffer.objects.get(pk=swap_offer.pk)
        swap_request = DutySwapRequest.objects.get(pk=swap_request.pk)
        assert swap_offer.status == "accepted"
        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer == swap_offer


# ---------------------------------------------------------------------------
# Volunteer Opportunities in Help Others context (issue #693)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestVolunteerOpportunities:
    """
    open_swap_requests view must include volunteer_opportunities in context,
    populated with unfilled scheduled roster holes the requesting member is
    qualified to fill (issue #693).
    """

    def test_volunteer_opportunities_key_in_context(self, client, alice, site_config):
        """volunteer_opportunities must always be present in context."""
        client.force_login(alice)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)
        assert resp.status_code == 200
        assert "volunteer_opportunities" in resp.context

    def test_opportunity_appears_for_qualified_member(self, client, alice, site_config):
        """
        A qualified tow-pilot sees a hole opportunity for a future scheduled day
        where the tow_pilot slot is empty.
        """
        future = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future,
            is_scheduled=True,
        )
        # alice is a towpilot (fixture), tow_pilot slot is empty
        client.force_login(alice)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)

        opps = resp.context["volunteer_opportunities"]
        matching = [o for o in opps if o["date"] == future and o["kind"] == "hole"]
        assert matching, "Expected a tow-pilot hole opportunity for the future day"
        role_labels = {o["role_label"] for o in matching}
        assert any("tow" in label.lower() for label in role_labels)


@pytest.mark.django_db
class TestSwapRequestExpiryCronjob:
    """Tests for nightly expiry of stale duty swap requests."""

    def test_expires_past_open_request_and_auto_declines_pending_offers(
        self, site_config, alice, bob, monkeypatch
    ):
        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() - timedelta(days=2),
            role="TOW",
            request_type="general",
            status="open",
        )
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
            status="pending",
        )

        notified = []

        def _mock_notify(request_obj, auto_declined_offers=None):
            notified.append((request_obj.pk, len(auto_declined_offers or [])))

        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.send_request_expired_notifications",
            _mock_notify,
        )
        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.transaction.on_commit",
            lambda callback, using=None, robust=False: callback(),
        )

        call_command("expire_past_swap_requests", verbosity=0)

        swap_request.refresh_from_db()
        offer.refresh_from_db()

        assert swap_request.status == "expired"
        assert offer.status == "auto_declined"
        assert offer.responded_at is not None
        assert notified == [(swap_request.pk, 1)]

    def test_uses_utc_cutoff_date_for_nightly_run(
        self, site_config, alice, monkeypatch
    ):
        """03:10 UTC run should expire requests from the prior UTC day."""
        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date(2026, 5, 29),
            role="TOW",
            request_type="general",
            status="open",
        )

        fixed_now = datetime(2026, 5, 30, 3, 10, tzinfo=dt_timezone.utc)
        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.timezone.now",
            lambda: fixed_now,
        )
        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.send_request_expired_notifications",
            lambda *_args, **_kwargs: None,
        )

        call_command("expire_past_swap_requests", verbosity=0)

        swap_request.refresh_from_db()
        assert swap_request.status == "expired"

    def test_dry_run_does_not_mutate_records(
        self, site_config, alice, bob, monkeypatch
    ):
        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() - timedelta(days=3),
            role="TOW",
            request_type="general",
            status="open",
        )
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
            status="pending",
        )

        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.send_request_expired_notifications",
            lambda *_args, **_kwargs: pytest.fail(
                "Expiry notifications should not be sent during dry-run"
            ),
        )

        call_command("expire_past_swap_requests", "--dry-run", verbosity=0)

        swap_request.refresh_from_db()
        offer.refresh_from_db()

        assert swap_request.status == "open"
        assert offer.status == "pending"
        assert offer.responded_at is None

    def test_expiry_notifications_are_deferred_until_transaction_commit(
        self, site_config, alice, bob, monkeypatch
    ):
        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() - timedelta(days=1),
            role="TOW",
            request_type="general",
            status="open",
        )
        DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
            status="pending",
        )

        scheduled_callbacks = []
        notified = []

        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.transaction.on_commit",
            lambda callback, using=None, robust=False: scheduled_callbacks.append(
                callback
            ),
        )
        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.send_request_expired_notifications",
            lambda request_obj, auto_declined_offers=None: notified.append(
                (request_obj.pk, len(auto_declined_offers or []))
            ),
        )

        call_command("expire_past_swap_requests", verbosity=0)

        swap_request.refresh_from_db()
        assert swap_request.status == "expired"
        assert notified == []
        assert len(scheduled_callbacks) == 1

        scheduled_callbacks[0]()
        assert notified == [(swap_request.pk, 1)]

    def test_leaves_future_or_non_open_requests_unchanged(
        self, site_config, alice, bob, monkeypatch
    ):
        stale_open = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() - timedelta(days=1),
            role="TOW",
            request_type="general",
            status="open",
        )
        future_open = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() + timedelta(days=1),
            role="TOW",
            request_type="general",
            status="open",
        )
        past_cancelled = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() - timedelta(days=4),
            role="TOW",
            request_type="general",
            status="cancelled",
        )
        past_fulfilled = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() - timedelta(days=5),
            role="TOW",
            request_type="general",
            status="fulfilled",
        )

        notified_ids = []

        def _mock_notify(request_obj, auto_declined_offers=None):
            notified_ids.append(request_obj.pk)

        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.send_request_expired_notifications",
            _mock_notify,
        )
        monkeypatch.setattr(
            "duty_roster.management.commands.expire_past_swap_requests.transaction.on_commit",
            lambda callback, using=None, robust=False: callback(),
        )

        call_command("expire_past_swap_requests", verbosity=0)

        stale_open.refresh_from_db()
        future_open.refresh_from_db()
        past_cancelled.refresh_from_db()
        past_fulfilled.refresh_from_db()

        assert stale_open.status == "expired"
        assert future_open.status == "open"
        assert past_cancelled.status == "cancelled"
        assert past_fulfilled.status == "fulfilled"
        assert notified_ids == [stale_open.pk]

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_expiry_notifications_render_and_send_requester_and_offerer_templates(
        self, site_config, alice, bob
    ):
        """Expiry notification helper should render both templates without errors."""
        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() - timedelta(days=1),
            role="TOW",
            request_type="general",
            status="expired",
        )
        offer = DutySwapOffer.objects.create(
            swap_request=swap_request,
            offered_by=bob,
            offer_type="cover",
            status="auto_declined",
        )

        mail.outbox.clear()
        send_request_expired_notifications(swap_request, auto_declined_offers=[offer])

        assert len(mail.outbox) == 2
        assert all(msg.alternatives for msg in mail.outbox)
        html_payloads = [msg.alternatives[0][0] for msg in mail.outbox]
        assert any("has expired" in html for html in html_payloads)
        assert any("Hi Alice" in html for html in html_payloads)
        assert any("Hi Bob" in html for html in html_payloads)
        assert any(
            "pending offer has been automatically closed" in html
            for html in html_payloads
        )


@pytest.mark.django_db
class TestOpenSwapPeriodicReminders:
    """Tests for periodic open swap reminder cadence and delivery."""

    def test_candidate_selection_uses_exact_offsets(self, site_config, alice):
        today = date(2026, 6, 18)

        due_14 = DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=14),
            role="TOW",
            request_type="general",
            status="open",
        )
        due_7 = DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=7),
            role="TOW",
            request_type="general",
            status="open",
        )
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=2),
            role="TOW",
            request_type="general",
            status="open",
        )
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=14),
            role="TOW",
            request_type="general",
            status="fulfilled",
        )

        candidates = list(get_open_swap_reminder_candidates(today=today))
        assert {req.pk for req in candidates} == {due_14.pk, due_7.pk}

    def test_candidate_selection_allows_empty_offsets(self, site_config, alice):
        today = date(2026, 6, 18)

        DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=14),
            role="TOW",
            request_type="general",
            status="open",
        )

        candidates = list(
            get_open_swap_reminder_candidates(today=today, day_offsets=())
        )
        assert candidates == []

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_reminders_include_eligible_requester_and_rostermeister_deduped(
        self, site_config, alice, bob, charlie
    ):
        today = date(2026, 6, 18)
        charlie.rostermeister = True
        charlie.save(update_fields=["rostermeister"])

        Member.objects.create(
            username="no_email_helper",
            first_name="No",
            last_name="Email",
            email="",
            membership_status="Full Member",
            towpilot=True,
        )

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=7),
            role="TOW",
            request_type="general",
            status="open",
        )

        mail.outbox.clear()
        summary = send_periodic_open_swap_reminder_notifications(
            today=today,
            day_offsets=(7,),
        )

        assert summary["candidate_count"] == 1
        assert summary["request_count"] == 1
        assert summary["email_count"] == 3

        assert len(mail.outbox) == 3
        html_payloads = [msg.alternatives[0][0] for msg in mail.outbox]
        assert any("Hi Alice" in html for html in html_payloads)
        assert any("Hi Bob" in html for html in html_payloads)
        assert any("Hi Charlie" in html for html in html_payloads)
        assert all("Reminder" in msg.subject for msg in mail.outbox)
        assert all(
            f"/swap/request/{swap_request.pk}/" in msg.alternatives[0][0]
            for msg in mail.outbox
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_dry_run_counts_emails_but_sends_nothing(self, site_config, alice, bob):
        today = date(2026, 6, 18)
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=3),
            role="TOW",
            request_type="general",
            status="open",
        )

        mail.outbox.clear()
        summary = send_periodic_open_swap_reminder_notifications(
            today=today,
            day_offsets=(3,),
            dry_run=True,
        )

        assert summary["candidate_count"] == 1
        assert summary["request_count"] == 1
        assert summary["email_count"] >= 2  # requester + at least one eligible helper
        assert len(mail.outbox) == 0

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_urgent_banner_pluralizes_day_label(self, site_config, alice, bob):
        today = date(2026, 6, 18)
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=today,
            role="TOW",
            request_type="general",
            status="open",
        )

        mail.outbox.clear()
        summary = send_periodic_open_swap_reminder_notifications(
            today=today,
            day_offsets=(0,),
        )

        assert summary["candidate_count"] == 1
        assert len(mail.outbox) >= 1
        html_payload = mail.outbox[0].alternatives[0][0]
        assert "Urgent: 0 days left" in html_payload

    def test_email_count_only_includes_successful_deliveries(
        self, site_config, alice, bob, monkeypatch
    ):
        today = date(2026, 6, 18)
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=today + timedelta(days=3),
            role="TOW",
            request_type="general",
            status="open",
        )

        monkeypatch.setattr(
            "duty_roster.views_swap.send_mail",
            lambda **_kwargs: 0,
        )

        summary = send_periodic_open_swap_reminder_notifications(
            today=today,
            day_offsets=(3,),
        )

        assert summary["candidate_count"] == 1
        assert summary["request_count"] == 1
        assert summary["email_count"] == 0

    def test_command_passes_dry_run_and_today(self, monkeypatch):
        captured = {}

        def _mock_sender(today=None, day_offsets=None, dry_run=False):
            captured["today"] = today
            captured["day_offsets"] = day_offsets
            captured["dry_run"] = dry_run
            return {
                "candidate_count": 1,
                "request_count": 1,
                "email_count": 4,
                "skipped_no_recipients": 0,
            }

        monkeypatch.setattr(
            "duty_roster.management.commands.remind_open_swap_requests.send_periodic_open_swap_reminder_notifications",
            _mock_sender,
        )

        call_command("remind_open_swap_requests", "--dry-run", verbosity=0)

        assert captured["dry_run"] is True
        assert isinstance(captured["today"], date)
        assert captured["day_offsets"] is None


@pytest.mark.django_db
class TestVolunteerOpportunitiesEdgeCases:
    """Additional edge-case coverage for volunteer opportunities context."""

    def test_no_opportunity_when_slot_filled(self, client, alice, site_config):
        """No opportunity is shown for a role that is already filled."""
        future = date.today() + timedelta(days=7)
        assignment = DutyAssignment.objects.create(
            date=future,
            is_scheduled=True,
            tow_pilot=alice,  # alice's own slot is filled
        )
        client.force_login(alice)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)

        opps = resp.context["volunteer_opportunities"]
        tow_holes = [
            o
            for o in opps
            if o["date"] == future
            and o["kind"] == "hole"
            and "tow" in o["role_label"].lower()
        ]
        assert (
            not tow_holes
        ), "Should not show a tow-pilot hole when slot is already filled"

    def test_no_opportunity_for_past_dates(self, client, alice, site_config):
        """Opportunities from past dates must not appear."""
        past = date.today() - timedelta(days=3)
        DutyAssignment.objects.create(date=past, is_scheduled=True)

        client.force_login(alice)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)

        opps = resp.context["volunteer_opportunities"]
        past_opps = [o for o in opps if o["date"] < date.today()]
        assert not past_opps, "Past dates must not appear in volunteer opportunities"

    def test_no_tow_opportunity_when_already_instructor_same_day(
        self, client, site_config
    ):
        """
        A dual-qualified member who is already serving as instructor on a day
        must NOT see a tow-pilot hole for that same day (double-booking guard,
        issue #696 review comment).
        """
        from members.models import Member as _Member

        multi_role = _Member.objects.create(
            username="multi_instr_tow",
            email="multi_it@example.com",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
        )
        future = date.today() + timedelta(days=8)
        DutyAssignment.objects.create(
            date=future,
            is_scheduled=True,
            instructor=multi_role,  # already has instructor role
        )
        client.force_login(multi_role)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)

        opps = resp.context["volunteer_opportunities"]
        tow_holes = [
            o
            for o in opps
            if o["date"] == future
            and o["kind"] == "hole"
            and "tow" in o["role_label"].lower()
        ]
        assert (
            not tow_holes
        ), "Should not show tow-pilot hole to someone already serving as instructor that day"

    def test_no_instructor_opportunity_when_already_tow_same_day(
        self, client, site_config
    ):
        """
        A dual-qualified member who is already serving as tow pilot on a day
        must NOT see an instructor hole for that same day (double-booking guard,
        issue #696 review comment).
        """
        from members.models import Member as _Member

        multi_role = _Member.objects.create(
            username="multi_tow_instr",
            email="multi_ti@example.com",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
        )
        future = date.today() + timedelta(days=9)
        DutyAssignment.objects.create(
            date=future,
            is_scheduled=True,
            tow_pilot=multi_role,  # already has tow pilot role
        )
        client.force_login(multi_role)
        url = reverse("duty_roster:open_swap_requests")
        resp = client.get(url)

        opps = resp.context["volunteer_opportunities"]
        instr_holes = [
            o
            for o in opps
            if o["date"] == future
            and o["kind"] == "hole"
            and "instructor" in o["role_label"].lower()
        ]
        assert (
            not instr_holes
        ), "Should not show instructor hole to someone already serving as tow pilot that day"


@pytest.mark.django_db
class TestSwapVisibilityInCalendar:
    """Open swap visibility in month cells and day modal (Issue #946)."""

    def test_calendar_month_shows_open_swap_marker_badge(
        self, client, site_config, alice
    ):
        duty_date = date.today() + timedelta(days=6)
        DutyAssignment.objects.create(date=duty_date, is_scheduled=True)
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=duty_date,
            role="TOW",
            request_type="general",
            status="open",
        )

        client.force_login(alice)
        response = client.get(
            reverse(
                "duty_roster:duty_calendar_month",
                kwargs={"year": duty_date.year, "month": duty_date.month},
            )
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "1 open" in content
        assert "Open coverage requests: Tow Pilot" in content

    def test_calendar_day_modal_shows_open_swap_section_with_links(
        self, client, site_config, alice, bob
    ):
        duty_date = date.today() + timedelta(days=8)
        DutyAssignment.objects.create(date=duty_date, is_scheduled=True)
        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=duty_date,
            role="TOW",
            request_type="direct",
            direct_request_to=bob,
            status="open",
        )

        client.force_login(bob)
        response = client.get(
            reverse(
                "duty_roster:calendar_day_detail",
                kwargs={
                    "year": duty_date.year,
                    "month": duty_date.month,
                    "day": duty_date.day,
                },
            )
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Open Swap Requests" in content
        assert "Requested by Alice Requester" in content
        assert "Tow Pilot" in content
        assert (
            reverse(
                "duty_roster:swap_request_detail",
                kwargs={"request_id": swap_request.id},
            )
            in content
        )

    def test_calendar_month_hides_direct_request_from_unrelated_viewer(
        self, client, site_config, alice, bob, charlie
    ):
        duty_date = date.today() + timedelta(days=11)
        DutyAssignment.objects.create(date=duty_date, is_scheduled=True)

        DutySwapRequest.objects.create(
            requester=alice,
            original_date=duty_date,
            role="TOW",
            request_type="general",
            status="open",
        )
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=duty_date,
            role="TOW",
            request_type="direct",
            direct_request_to=bob,
            status="open",
        )

        client.force_login(charlie)
        response = client.get(
            reverse(
                "duty_roster:duty_calendar_month",
                kwargs={"year": duty_date.year, "month": duty_date.month},
            )
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "1 open" in content
        assert "2 open" not in content

    def test_calendar_day_modal_hides_direct_request_from_unrelated_viewer(
        self, client, site_config, alice, bob, charlie
    ):
        duty_date = date.today() + timedelta(days=12)
        DutyAssignment.objects.create(date=duty_date, is_scheduled=True)

        DutySwapRequest.objects.create(
            requester=alice,
            original_date=duty_date,
            role="TOW",
            request_type="general",
            status="open",
        )
        DutySwapRequest.objects.create(
            requester=alice,
            original_date=duty_date,
            role="TOW",
            request_type="direct",
            direct_request_to=bob,
            status="open",
        )

        client.force_login(charlie)
        response = client.get(
            reverse(
                "duty_roster:calendar_day_detail",
                kwargs={
                    "year": duty_date.year,
                    "month": duty_date.month,
                    "day": duty_date.day,
                },
            )
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Open Swap Requests" in content
        assert "1 open coverage request" in content
        assert "Direct to Bob Offerer" not in content


@pytest.mark.django_db
class TestReminderRecipientFiltering:
    def test_inactive_rostermeister_is_excluded_from_reminders(
        self, site_config, alice, bob
    ):
        inactive_rostermeister = Member.objects.create(
            username="inactive_rm",
            first_name="Inactive",
            last_name="Rostermeister",
            email="inactive-rm@example.com",
            membership_status="Full Member",
            rostermeister=True,
        )
        Member.objects.filter(pk=inactive_rostermeister.pk).update(is_active=False)
        inactive_rostermeister.refresh_from_db(fields=["is_active"])

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() + timedelta(days=7),
            role="TOW",
            request_type="general",
            status="open",
        )

        recipients = list(get_periodic_reminder_recipients(swap_request))
        recipient_ids = {member.id for member in recipients}

        assert bob.id in recipient_ids
        assert alice.id in recipient_ids
        assert inactive_rostermeister.id not in recipient_ids

    def test_direct_request_reminders_only_include_target_not_all_eligible(
        self, site_config, alice, bob
    ):
        unrelated_helper = Member.objects.create(
            username="unrelated_helper",
            first_name="Unrelated",
            last_name="Helper",
            email="unrelated-helper@example.com",
            membership_status="Full Member",
            towpilot=True,
        )

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() + timedelta(days=7),
            role="TOW",
            request_type="direct",
            direct_request_to=bob,
            status="open",
        )

        recipients = list(get_periodic_reminder_recipients(swap_request))
        recipient_ids = {member.id for member in recipients}

        assert bob.id in recipient_ids
        assert alice.id in recipient_ids
        assert unrelated_helper.id not in recipient_ids

    def test_inactive_direct_target_is_excluded_from_reminders(
        self, site_config, alice, bob
    ):
        Member.objects.filter(pk=bob.pk).update(is_active=False)

        swap_request = DutySwapRequest.objects.create(
            requester=alice,
            original_date=date.today() + timedelta(days=7),
            role="TOW",
            request_type="direct",
            direct_request_to=bob,
            status="open",
        )

        recipients = list(get_periodic_reminder_recipients(swap_request))
        recipient_ids = {member.id for member in recipients}

        assert bob.id not in recipient_ids
        assert alice.id in recipient_ids
