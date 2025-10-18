from django.test import TestCase
from django.urls import reverse

from members.forms import SetPasswordForm
from members.models import Biography, Member


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
