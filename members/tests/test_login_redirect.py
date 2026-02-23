"""
Unit tests for login redirect behavior in custom decorators (Issue #674).

Verifies that unauthenticated requests to protected views are redirected
to the login page with a ?next= parameter pointing to the original URL.

These are fast Django test client tests — no browser required.
"""

from django.test import Client, TestCase
from django.urls import reverse

from members.models import Member
from siteconfig.models import MembershipStatus


def make_member(username="member1", password="testpass", **kwargs):
    status, _ = MembershipStatus.objects.get_or_create(name="Full Member")
    return Member.objects.create_user(
        username=username,
        password=password,
        membership_status=status.name,
        **kwargs,
    )


class LoginRedirectDecoratorTest(TestCase):
    """Unauthenticated access to @active_member_required views should redirect with ?next=."""

    def setUp(self):
        self.client = Client()

    def test_unauthenticated_member_list_redirects_with_next(self):
        """GET /members/ without login → /login/?next=/members/"""
        response = self.client.get("/members/")
        self.assertRedirects(
            response,
            "/login/?next=/members/",
            fetch_redirect_response=False,
        )

    def test_unauthenticated_member_detail_redirects_with_next(self):
        """GET /members/<pk>/view/ without login → /login/?next=/members/<pk>/view/"""
        member = make_member(username="target")
        url = f"/members/{member.pk}/view/"
        response = self.client.get(url)
        self.assertRedirects(
            response,
            f"/login/?next=/members/{member.pk}/view/",
            fetch_redirect_response=False,
        )

    def test_authenticated_member_is_not_redirected(self):
        """A logged-in active member reaches /members/ directly."""
        make_member(username="active")
        self.client.login(username="active", password="testpass")
        response = self.client.get("/members/")
        self.assertEqual(response.status_code, 200)

    def test_login_then_next_redirects_to_original_url(self):
        """POST to /login/?next=/members/ with correct credentials → /members/"""
        make_member(username="postlogin")
        response = self.client.post(
            "/login/?next=/members/",
            {"username": "postlogin", "password": "testpass", "next": "/members/"},
        )
        self.assertRedirects(
            response,
            "/members/",
            fetch_redirect_response=False,
        )
