from django.test import TestCase
from django.urls import reverse

from members.forms import SetPasswordForm
from members.models import Biography, Member
from siteconfig.models import MembershipStatus


class MemberModelTests(TestCase):
    def test_full_display_name_prefers_nickname(self):
        m = Member(first_name="Brett", last_name="Gilbert", nickname="Sam")
        self.assertEqual(m.full_display_name, "Sam Gilbert")

    def test_full_display_name_falls_back_to_first_name(self):
        m = Member(first_name="Brett", last_name="Gilbert", nickname="")
        self.assertEqual(m.full_display_name, "Brett Gilbert")

    def test_is_active_member_defaults_false(self):
        m = Member(membership_status="Inactive")
        self.assertFalse(m.is_active_member())

    def test_is_active_member_true_for_student(self):
        m = Member(membership_status="Student Member")
        self.assertTrue(m.is_active_member())


class SetPasswordFormTests(TestCase):
    def test_passwords_must_match(self):
        form = SetPasswordForm(
            data={"new_password1": "abc123", "new_password2": "xyz123"}
        )
        self.assertFalse(form.is_valid())

    def test_valid_passwords_are_accepted(self):
        form = SetPasswordForm(
            data={"new_password1": "securepass123", "new_password2": "securepass123"}
        )
        self.assertTrue(form.is_valid())


class BiographyModelTests(TestCase):
    def test_biography_str_repr(self):
        member = Member.objects.create(
            username="jdoe", first_name="John", last_name="Doe"
        )
        bio = Biography(member=member)
        bio.content = "<p>Hello!</p>"  # ✅ use 'content' instead of 'body'
        self.assertEqual(str(bio), "Biography of John Doe")


class MemberViewsTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_biography_view_handles_missing_user(self):
        response = self.client.get("/members/nonexistentuser/biography/")
        self.assertEqual(response.status_code, 404)


class MembershipStatusIntegrationTests(TestCase):
    """Test integration between Member model and MembershipStatus model."""

    def setUp(self):
        """Create test membership statuses."""
        self.active_status = MembershipStatus.objects.create(
            name="Test Active Member",
            is_active=True,
            sort_order=10
        )
        self.inactive_status = MembershipStatus.objects.create(
            name="Test Inactive Member",
            is_active=False,
            sort_order=20
        )

    def test_is_active_member_with_dynamic_status(self):
        """Test that Member.is_active_member() works with dynamic MembershipStatus."""
        # Create member with active status
        active_member = Member(
            username="active_user",
            membership_status="Test Active Member"
        )
        self.assertTrue(active_member.is_active_member())

        # Create member with inactive status
        inactive_member = Member(
            username="inactive_user",
            membership_status="Test Inactive Member"
        )
        self.assertFalse(inactive_member.is_active_member())

    def test_is_active_member_with_nonexistent_status(self):
        """Test Member.is_active_member() with a status not in database."""
        member = Member(
            username="test_user",
            membership_status="Nonexistent Status"
        )
        # Should return False for unknown status
        self.assertFalse(member.is_active_member())

    def test_get_membership_status_choices(self):
        """Test that Member.get_membership_status_choices() returns dynamic choices."""
        choices = Member.get_membership_status_choices()

        # Should include our test statuses in order
        choice_names = [choice[0] for choice in choices]
        self.assertIn("Test Active Member", choice_names)
        self.assertIn("Test Inactive Member", choice_names)

        # Should be ordered by sort_order
        active_index = choice_names.index("Test Active Member")
        inactive_index = choice_names.index("Test Inactive Member")
        self.assertLess(active_index, inactive_index)

    def test_member_with_updated_status_activity(self):
        """Test that changing a MembershipStatus affects Member.is_active_member()."""
        member = Member(
            username="test_user",
            membership_status="Test Active Member"
        )

        # Initially active
        self.assertTrue(member.is_active_member())

        # Change the status to inactive
        self.active_status.is_active = False
        self.active_status.save()

        # Member should now be inactive
        self.assertFalse(member.is_active_member())
