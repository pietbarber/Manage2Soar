"""Tests for member profile badge leg suppression feature (Issue #560).

This module tests the member_view function to ensure that badge legs
(component badges) are suppressed on the member profile page when
the parent badge has been earned.
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
def viewer_member(db, active_membership_status):
    """Create a viewer member for testing (who views other profiles)."""
    return Member.objects.create_user(
        username="viewer",
        password="password123",
        first_name="Viewer",
        last_name="Member",
        membership_status=active_membership_status.name,
    )


# =============================================================================
# Member Profile View Badge Suppression Tests
# =============================================================================


class TestMemberProfileBadgeSuppression:
    """Tests for badge leg suppression on member profile page."""

    @pytest.mark.django_db
    def test_member_profile_shows_leg_when_parent_not_earned(
        self, client, active_member, viewer_member
    ):
        """Member profile should show leg badge if parent badge not earned."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)

        # Award only the leg, not the parent
        MemberBadge.objects.create(
            member=active_member, badge=leg, date_awarded="2024-01-01"
        )

        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        assert "member_badges" in response.context
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]
        assert "Silver Duration" in badge_names

    @pytest.mark.django_db
    def test_member_profile_hides_leg_when_parent_earned(
        self, client, active_member, viewer_member
    ):
        """Member profile should NOT show leg badge if parent badge earned."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)

        # Award both the leg and the parent
        MemberBadge.objects.create(
            member=active_member, badge=parent, date_awarded="2024-06-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=leg, date_awarded="2024-01-01"
        )

        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        assert "member_badges" in response.context
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]
        # Leg should NOT appear
        assert "Silver Duration" not in badge_names
        # Parent SHOULD appear
        assert "FAI Silver" in badge_names

    @pytest.mark.django_db
    def test_member_profile_shows_parent_badge_when_earned(
        self, client, active_member, viewer_member
    ):
        """Member profile should show parent badge when earned."""
        parent = Badge.objects.create(name="FAI Silver", order=1)

        MemberBadge.objects.create(
            member=active_member, badge=parent, date_awarded="2024-06-01"
        )

        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]
        assert "FAI Silver" in badge_names

    @pytest.mark.django_db
    def test_member_profile_hides_multiple_legs_when_parent_earned(
        self, client, active_member, viewer_member
    ):
        """All leg badges should be suppressed when parent badge earned."""
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

        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]

        # Check all three legs are NOT shown
        assert "Silver Duration" not in badge_names
        assert "Silver Altitude" not in badge_names
        assert "Silver Distance" not in badge_names
        # Parent SHOULD be shown
        assert "FAI Silver" in badge_names

    @pytest.mark.django_db
    def test_member_profile_standalone_badges_unaffected(
        self, client, active_member, viewer_member
    ):
        """Standalone badges (not legs) should not be affected by suppression."""
        standalone1 = Badge.objects.create(name="A Badge", order=1)
        standalone2 = Badge.objects.create(name="B Badge", order=2)

        MemberBadge.objects.create(
            member=active_member, badge=standalone1, date_awarded="2024-01-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=standalone2, date_awarded="2024-02-01"
        )

        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]
        assert "A Badge" in badge_names
        assert "B Badge" in badge_names

    @pytest.mark.django_db
    def test_member_profile_no_badges(self, client, active_member, viewer_member):
        """Member profile should handle members with no badges."""
        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        assert "member_badges" in response.context
        assert len(response.context["member_badges"]) == 0

    @pytest.mark.django_db
    def test_member_profile_self_view_shows_filtered_badges(
        self, client, active_member
    ):
        """Member viewing own profile should see filtered badges."""
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg = Badge.objects.create(name="Silver Duration", order=2, parent_badge=parent)

        # Award both parent and leg
        MemberBadge.objects.create(
            member=active_member, badge=parent, date_awarded="2024-06-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=leg, date_awarded="2024-01-01"
        )

        # Member views their own profile
        client.force_login(active_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]
        # Leg should NOT appear even in self-view
        assert "Silver Duration" not in badge_names
        # Parent SHOULD appear
        assert "FAI Silver" in badge_names

    @pytest.mark.django_db
    def test_member_profile_badge_ordering_preserved(
        self, client, active_member, viewer_member
    ):
        """Badges should be ordered by badge.order field."""
        badge3 = Badge.objects.create(name="Third Badge", order=3)
        badge1 = Badge.objects.create(name="First Badge", order=1)
        badge2 = Badge.objects.create(name="Second Badge", order=2)

        # Award in random order
        MemberBadge.objects.create(
            member=active_member, badge=badge3, date_awarded="2024-01-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=badge1, date_awarded="2024-02-01"
        )
        MemberBadge.objects.create(
            member=active_member, badge=badge2, date_awarded="2024-03-01"
        )

        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]
        # Should be ordered by badge.order field
        assert badge_names == ["First Badge", "Second Badge", "Third Badge"]

    @pytest.mark.django_db
    def test_member_profile_mixed_legs_and_standalones(
        self, client, active_member, viewer_member
    ):
        """Member profile should handle mix of legs and standalone badges."""
        # Create parent with legs
        parent = Badge.objects.create(name="FAI Silver", order=1)
        leg1 = Badge.objects.create(
            name="Silver Duration", order=2, parent_badge=parent
        )
        leg2 = Badge.objects.create(
            name="Silver Altitude", order=3, parent_badge=parent
        )
        # Create standalone badges
        standalone = Badge.objects.create(name="1000km Badge", order=4)

        # Award parent (suppresses legs) and standalone
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
            member=active_member, badge=standalone, date_awarded="2024-03-01"
        )

        client.force_login(viewer_member)
        url = reverse("members:member_view", args=[active_member.id])
        response = client.get(url)

        assert response.status_code == 200
        badge_names = [mb.badge.name for mb in response.context["member_badges"]]

        # Should show parent and standalone, but NOT legs
        assert "FAI Silver" in badge_names
        assert "1000km Badge" in badge_names
        assert "Silver Duration" not in badge_names
        assert "Silver Altitude" not in badge_names
