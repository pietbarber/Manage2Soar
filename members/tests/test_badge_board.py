"""Tests for Badge Board leg suppression feature (Issue #560).

This module tests the badge board view and the Badge model's parent_badge
functionality which allows legs (component badges) to be suppressed when
a member has earned the parent badge.
"""

import pytest
from django.urls import reverse

from members.models import Badge, Member, MemberBadge
from siteconfig.models import MembershipStatus


@pytest.fixture
def active_membership_status(db):
    """Create an active membership status for testing."""
    status, _ = MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    return status


@pytest.fixture
def active_member(db, active_membership_status):
    """Create an active member for testing."""
    return Member.objects.create_user(
        username="testpilot",
        password="password123",
        first_name="Test",
        last_name="Pilot",
        membership_status=active_membership_status.name,
    )


@pytest.fixture
def second_active_member(db, active_membership_status):
    """Create a second active member for testing."""
    return Member.objects.create_user(
        username="testpilot2",
        password="password123",
        first_name="Another",
        last_name="Pilot",
        membership_status=active_membership_status.name,
    )


# =============================================================================
# Badge Model Tests
# =============================================================================


class TestBadgeModel:
    """Tests for Badge model parent_badge functionality."""

    @pytest.mark.django_db
    def test_badge_parent_badge_default_is_none(self):
        """A new badge should have no parent badge by default."""
        badge = Badge.objects.create(name="Test Badge", order=1)
        assert badge.parent_badge is None

    @pytest.mark.django_db
    def test_badge_is_leg_false_when_no_parent(self):
        """is_leg should be False when badge has no parent_badge."""
        badge = Badge.objects.create(name="FAI Silver", order=1)
        assert badge.is_leg is False

    @pytest.mark.django_db
    def test_badge_is_leg_true_when_has_parent(self):
        """is_leg should be True when badge has a parent_badge."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)
        assert leg.is_leg is True

    @pytest.mark.django_db
    def test_parent_badge_legs_related_name(self):
        """Parent badge should access legs via 'legs' related name."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg1 = Badge.objects.create(
            name="Silver Duration", order=2, parent_badge=parent
        )
        leg2 = Badge.objects.create(
            name="Silver Altitude", order=3, parent_badge=parent
        )
        leg3 = Badge.objects.create(
            name="Silver Distance", order=4, parent_badge=parent
        )

        legs = list(parent.legs.all())
        assert len(legs) == 3
        assert leg1 in legs
        assert leg2 in legs
        assert leg3 in legs

    @pytest.mark.django_db
    def test_parent_badge_on_delete_set_null(self):
        """Deleting parent badge should set legs' parent_badge to NULL."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)

        parent.delete()
        leg.refresh_from_db()

        assert leg.parent_badge is None
        assert leg.is_leg is False


# =============================================================================
# Badge Board View Tests
# =============================================================================


class TestBadgeBoardView:
    """Tests for badge_board view leg suppression logic."""

    @pytest.mark.django_db
    def test_badge_board_requires_authentication(self, client):
        """Badge board should redirect unauthenticated users."""
        url = reverse("members:badge_board")
        response = client.get(url)
        assert response.status_code == 302  # Redirect to login

    @pytest.mark.django_db
    def test_badge_board_accessible_to_active_members(self, client, active_member):
        """Active members should be able to access the badge board."""
        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_badge_board_shows_badges(self, client, active_member):
        """Badge board should show badges in template context."""
        Badge.objects.create(name="A Badge", order=1)
        Badge.objects.create(name="B Badge", order=2)

        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)

        assert response.status_code == 200
        assert "badges" in response.context
        badge_names = [b.name for b in response.context["badges"]]
        assert "A Badge" in badge_names
        assert "B Badge" in badge_names

    @pytest.mark.django_db
    def test_member_shown_on_leg_when_no_parent_badge_earned(
        self, client, active_member, active_membership_status
    ):
        """Member should appear on leg badge if they haven't earned parent."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)

        # Award only the leg, not the parent
        MemberBadge.objects.create(
            member=active_member, badge=leg, date_awarded="2024-01-01"
        )

        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)

        # Find the leg badge in context and check member is shown
        badges = list(response.context["badges"])
        leg_badge = next(b for b in badges if b.name == "Silver Duration")
        member_ids = [mb.member_id for mb in leg_badge.filtered_memberbadges]
        assert active_member.id in member_ids

    @pytest.mark.django_db
    def test_member_hidden_on_leg_when_parent_badge_earned(
        self, client, active_member, active_membership_status
    ):
        """Member should NOT appear on leg badge if they have parent badge."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)

        # Award both the leg and the parent
        MemberBadge.objects.create(
            member=active_member, badge=parent, date_awarded="2024-06-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=leg, date_awarded="2024-01-01"
        )

        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)

        # Find the leg badge in context and check member is NOT shown
        badges = list(response.context["badges"])
        leg_badge = next(b for b in badges if b.name == "Silver Duration")
        member_ids = [mb.member_id for mb in leg_badge.filtered_memberbadges]
        assert active_member.id not in member_ids

    @pytest.mark.django_db
    def test_member_shown_on_parent_badge_when_earned(
        self, client, active_member, active_membership_status
    ):
        """Member should appear on parent badge when they've earned it."""
        parent = Badge.objects.create(name="FAI Silver", order=1)

        MemberBadge.objects.create(
            member=active_member, badge=parent, date_awarded="2024-06-01"
        )

        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)

        badges = list(response.context["badges"])
        parent_badge = next(b for b in badges if b.name == "FAI Silver")
        member_ids = [mb.member_id for mb in parent_badge.filtered_memberbadges]
        assert active_member.id in member_ids

    @pytest.mark.django_db
    def test_leg_suppression_only_affects_member_with_parent(
        self, client, active_member, second_active_member, active_membership_status
    ):
        """Leg suppression should only affect members who earned the parent."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)

        # First member has both parent and leg
        MemberBadge.objects.create(
            member=active_member, badge=parent, date_awarded="2024-06-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=leg, date_awarded="2024-01-01"
        )

        # Second member has only the leg
        MemberBadge.objects.create(
            member=second_active_member, badge=leg, date_awarded="2024-02-01"
        )

        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)

        badges = list(response.context["badges"])
        leg_badge = next(b for b in badges if b.name == "Silver Duration")
        member_ids = [mb.member_id for mb in leg_badge.filtered_memberbadges]

        # First member (has parent) should NOT appear on leg
        assert active_member.id not in member_ids
        # Second member (no parent) SHOULD appear on leg
        assert second_active_member.id in member_ids

    @pytest.mark.django_db
    def test_multiple_legs_suppressed_for_member_with_parent(
        self, client, active_member, active_membership_status
    ):
        """All legs should be suppressed when member has parent badge."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg1 = Badge.objects.create(
            name="Silver Duration", order=2, parent_badge=parent
        )
        leg2 = Badge.objects.create(
            name="Silver Altitude", order=3, parent_badge=parent
        )
        leg3 = Badge.objects.create(
            name="Silver Distance", order=4, parent_badge=parent
        )

        # Award parent and all legs
        MemberBadge.objects.create(
            member=active_member, badge=parent, date_awarded="2024-06-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=leg1, date_awarded="2024-01-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=leg2, date_awarded="2024-02-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=leg3, date_awarded="2024-03-01"
        )

        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)

        badges = list(response.context["badges"])

        # Check all three legs - member should NOT appear on any
        for leg_name in ["Silver Duration", "Silver Altitude", "Silver Distance"]:
            leg_badge = next(b for b in badges if b.name == leg_name)
            member_ids = [mb.member_id for mb in leg_badge.filtered_memberbadges]
            assert active_member.id not in member_ids, f"Member shown on {leg_name}"

    @pytest.mark.django_db
    def test_non_leg_badges_unaffected_by_suppression(
        self, client, active_member, active_membership_status
    ):
        """Regular badges (not legs) should not be affected by suppression logic."""
        standalone1 = Badge.objects.create(name="A Badge", order=1)
        standalone2 = Badge.objects.create(name="B Badge", order=2)

        MemberBadge.objects.create(
            member=active_member, badge=standalone1, date_awarded="2024-01-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=standalone2, date_awarded="2024-02-01"
        )

        client.force_login(active_member)
        url = reverse("members:badge_board")
        response = client.get(url)

        badges = list(response.context["badges"])

        for badge_name in ["A Badge", "B Badge"]:
            badge = next(b for b in badges if b.name == badge_name)
            member_ids = [mb.member_id for mb in badge.filtered_memberbadges]
            assert active_member.id in member_ids, f"Member not shown on {badge_name}"
