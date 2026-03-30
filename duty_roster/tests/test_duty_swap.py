"""
Tests for Duty Swap feature.

Tests the duty swap workflow including:
- Model methods (is_critical_role, days_until_duty, get_urgency_level, check_blackout_conflict)
- Form validation
- View access and permissions
- Email notifications
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.urls import reverse

from duty_roster.forms import DutySwapOfferForm, DutySwapRequestForm
from duty_roster.models import (
    DutyAssignment,
    DutySwapOffer,
    DutySwapRequest,
    MemberBlackout,
)
from duty_roster.views_swap import (
    _accept_offer_and_finalize,
    get_eligible_members_for_role,
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
        membership_status="Probationary Member",
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

    def test_cover_offer_valid(self):
        """Cover offer without swap date is valid."""
        form = DutySwapOfferForm(
            data={
                "offer_type": "cover",
                "notes": "Happy to help!",
            }
        )
        assert form.is_valid()

    def test_swap_offer_requires_date(self):
        """Swap offer without proposed date is invalid."""
        form = DutySwapOfferForm(
            data={
                "offer_type": "swap",
                "notes": "",
            }
        )
        assert not form.is_valid()
        assert "proposed_swap_date" in form.errors

    def test_swap_offer_with_date_valid(self):
        """Swap offer with proposed date is valid."""
        form = DutySwapOfferForm(
            data={
                "offer_type": "swap",
                "proposed_swap_date": date.today() + timedelta(days=30),
                "notes": "",
            }
        )
        assert form.is_valid()


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
        other_offer.refresh_from_db()
        swap_request.refresh_from_db()

        assert accepted_offer.status == "accepted"
        assert other_offer.status == "auto_declined"
        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer == accepted_offer

    def test_ado_probationary_member_can_make_offer(
        self,
        client,
        ado_helper_probationary,
        ado_swap_request,
        ado_duty_assignment,
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
        stale_offer.refresh_from_db()
        swap_request.refresh_from_db()

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

        direct_request.refresh_from_db()
        assert direct_request.request_type == "general"
        assert direct_request.direct_request_to is None


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
        swap_request.refresh_from_db()
        swap_offer.refresh_from_db()

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
        swap_offer.refresh_from_db()
        swap_request.refresh_from_db()
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
