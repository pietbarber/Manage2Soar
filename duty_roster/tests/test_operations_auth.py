"""Tests for operations proposal authentication requirements (Issue #191)."""

import pytest
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from members.models import Member
from logsheet.models import Airfield


User = get_user_model()


class TestOperationsAuthentication(TestCase):
    """Test authentication requirements for proposing operations."""

    def setUp(self):
        self.client = Client()
        self.tomorrow = date.today() + timedelta(days=1)

        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        # Create member profile
        self.member = Member.objects.create(
            user=self.user,
            first_name='Test',
            last_name='User',
            email='test@example.com',
            membership_status='Full Member'
        )

        # Create required airfield
        self.airfield = Airfield.objects.create(
            identifier='KFRR',
            name='Test Airfield'
        )

    def test_ad_hoc_start_requires_authentication(self):
        """Test that calendar_ad_hoc_start shows login required message for unauthenticated users."""
        url = reverse('duty_roster:calendar_ad_hoc_start', args=[
            self.tomorrow.year, self.tomorrow.month, self.tomorrow.day
        ])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "You must be signed in to propose and edit operations")
        self.assertContains(response, "Sign In Required")

    def test_ad_hoc_start_works_for_authenticated_users(self):
        """Test that calendar_ad_hoc_start works normally for authenticated users."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('duty_roster:calendar_ad_hoc_start', args=[
            self.tomorrow.year, self.tomorrow.month, self.tomorrow.day
        ])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Propose Operations for")
        self.assertContains(response, "request ad-hoc operations")

    def test_ad_hoc_confirm_requires_authentication(self):
        """Test that calendar_ad_hoc_confirm returns 403 for unauthenticated users."""
        url = reverse('duty_roster:calendar_ad_hoc_confirm', args=[
            self.tomorrow.year, self.tomorrow.month, self.tomorrow.day
        ])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)
        self.assertIn("You must be signed in to propose and edit operations",
                      response.content.decode())

    def test_ad_hoc_confirm_works_for_authenticated_users(self):
        """Test that calendar_ad_hoc_confirm works normally for authenticated users."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('duty_roster:calendar_ad_hoc_confirm', args=[
            self.tomorrow.year, self.tomorrow.month, self.tomorrow.day
        ])

        response = self.client.post(url)

        # Should redirect/refresh calendar after creating assignment
        self.assertEqual(response.status_code, 200)

    def test_past_dates_rejected(self):
        """Test that both views reject past dates regardless of authentication."""
        yesterday = date.today() - timedelta(days=1)

        # Test unauthenticated
        start_url = reverse('duty_roster:calendar_ad_hoc_start', args=[
            yesterday.year, yesterday.month, yesterday.day
        ])
        confirm_url = reverse('duty_roster:calendar_ad_hoc_confirm', args=[
            yesterday.year, yesterday.month, yesterday.day
        ])

        self.assertEqual(self.client.get(start_url).status_code, 400)
        self.assertEqual(self.client.post(confirm_url).status_code, 400)

        # Test authenticated
        self.client.login(username='testuser', password='testpass123')

        self.assertEqual(self.client.get(start_url).status_code, 400)
        self.assertEqual(self.client.post(confirm_url).status_code, 400)
