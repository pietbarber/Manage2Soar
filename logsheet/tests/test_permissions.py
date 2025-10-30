"""
Tests for logsheet permission utilities

These tests verify that the correct users can unfinalize and edit logsheets
according to the business rules defined in Issue #198.
"""

import pytest
from django.contrib.auth.models import User
from django.test import TestCase

from logsheet.models import Logsheet, RevisionLog
from logsheet.utils.permissions import can_edit_logsheet, can_unfinalize_logsheet
from members.models import Member


@pytest.mark.django_db
class TestLogsheetPermissions(TestCase):
    def setUp(self):
        """Set up test data for permission tests"""
        # Create test airfield and other required objects
        from logsheet.models import Airfield
        self.airfield = Airfield.objects.create(
            identifier="TEST", name="Test Airfield", is_active=True
        )
        
        # Create different types of users
        self.superuser = Member.objects.create_user(
            username="superuser",
            email="super@test.com",
            is_superuser=True,
            membership_status="Full Member"
        )
        
        self.treasurer = Member.objects.create_user(
            username="treasurer", 
            email="treasurer@test.com",
            treasurer=True,
            membership_status="Full Member"
        )
        
        self.webmaster = Member.objects.create_user(
            username="webmaster",
            email="webmaster@test.com", 
            webmaster=True,
            membership_status="Full Member"
        )
        
        self.duty_officer = Member.objects.create_user(
            username="dutyofficer",
            email="do@test.com",
            duty_officer=True,
            membership_status="Full Member"
        )
        
        self.regular_member = Member.objects.create_user(
            username="regular",
            email="regular@test.com",
            membership_status="Full Member"
        )
        
        self.non_member = Member.objects.create_user(
            username="nonmember",
            email="nonmember@test.com",
            membership_status="Non-Member"
        )
        
        # Create test logsheet
        from datetime import date
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.duty_officer,
            finalized=False
        )

    def test_unauthenticated_user_cannot_unfinalize(self):
        """Test that None or unauthenticated user cannot unfinalize"""
        self.assertFalse(can_unfinalize_logsheet(None, self.logsheet))
        
        # Create an unauthenticated user mock
        class UnauthenticatedUser:
            is_authenticated = False
        
        unauth_user = UnauthenticatedUser()
        self.assertFalse(can_unfinalize_logsheet(unauth_user, self.logsheet))

    def test_superuser_can_unfinalize(self):
        """Test that superusers can always unfinalize logsheets"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        self.assertTrue(can_unfinalize_logsheet(self.superuser, self.logsheet))

    def test_treasurer_can_unfinalize(self):
        """Test that treasurers can unfinalize any logsheet"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        self.assertTrue(can_unfinalize_logsheet(self.treasurer, self.logsheet))

    def test_webmaster_can_unfinalize(self):
        """Test that webmasters can unfinalize any logsheet"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        self.assertTrue(can_unfinalize_logsheet(self.webmaster, self.logsheet))

    def test_original_finalizer_can_unfinalize(self):
        """Test that the person who finalized the logsheet can unfinalize it"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        # Create revision log entry showing duty_officer finalized it
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.duty_officer,
            note="Logsheet finalized"
        )
        
        self.assertTrue(can_unfinalize_logsheet(self.duty_officer, self.logsheet))

    def test_regular_member_cannot_unfinalize(self):
        """Test that regular members cannot unfinalize logsheets"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        # Even if they finalized it, regular members without special roles can't unfinalize
        # (This tests the case where someone used to be a DO but no longer is)
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.regular_member,
            note="Logsheet finalized"
        )
        
        self.assertFalse(can_unfinalize_logsheet(self.regular_member, self.logsheet))

    def test_non_member_cannot_unfinalize(self):
        """Test that non-members cannot unfinalize logsheets"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        self.assertFalse(can_unfinalize_logsheet(self.non_member, self.logsheet))

    def test_wrong_finalizer_cannot_unfinalize(self):
        """Test that users who didn't finalize the logsheet cannot unfinalize it"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        # Create revision log showing someone else finalized it
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.duty_officer,
            note="Logsheet finalized"
        )
        
        # Regular member who didn't finalize it cannot unfinalize
        self.assertFalse(can_unfinalize_logsheet(self.regular_member, self.logsheet))

    def test_multiple_finalization_revisions(self):
        """Test that only the most recent finalizer can unfinalize"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        # Create multiple revision entries (simulate re-finalization)
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.duty_officer,
            note="Logsheet finalized"
        )
        
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.regular_member,  
            note="Logsheet returned to revised state"
        )
        
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.superuser,
            note="Logsheet finalized"
        )
        
        # Only the most recent finalizer (superuser) should be able to unfinalize
        # (though superuser can anyway due to role)
        self.assertTrue(can_unfinalize_logsheet(self.superuser, self.logsheet))
        # The original finalizer (duty_officer) should not be able to unfinalize
        self.assertFalse(can_unfinalize_logsheet(self.duty_officer, self.logsheet))

    def test_can_edit_unfinalized_logsheet(self):
        """Test that anyone can edit an unfinalized logsheet"""
        self.logsheet.finalized = False
        self.logsheet.save()
        
        # All authenticated users should be able to edit unfinalized logsheets
        self.assertTrue(can_edit_logsheet(self.regular_member, self.logsheet))
        self.assertTrue(can_edit_logsheet(self.duty_officer, self.logsheet))
        self.assertTrue(can_edit_logsheet(self.treasurer, self.logsheet))
        self.assertTrue(can_edit_logsheet(self.webmaster, self.logsheet))
        self.assertTrue(can_edit_logsheet(self.superuser, self.logsheet))

    def test_can_edit_finalized_logsheet_with_permission(self):
        """Test that authorized users can edit finalized logsheets"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        # Create revision log showing duty_officer finalized it
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.duty_officer,
            note="Logsheet finalized"
        )
        
        # Authorized users should be able to edit finalized logsheets
        self.assertTrue(can_edit_logsheet(self.superuser, self.logsheet))
        self.assertTrue(can_edit_logsheet(self.treasurer, self.logsheet))
        self.assertTrue(can_edit_logsheet(self.webmaster, self.logsheet))
        self.assertTrue(can_edit_logsheet(self.duty_officer, self.logsheet))  # original finalizer

    def test_cannot_edit_finalized_logsheet_without_permission(self):
        """Test that unauthorized users cannot edit finalized logsheets"""
        self.logsheet.finalized = True
        self.logsheet.save()
        
        # Create revision log showing someone else finalized it
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.duty_officer,
            note="Logsheet finalized"
        )
        
        # Unauthorized users should not be able to edit finalized logsheets
        self.assertFalse(can_edit_logsheet(self.regular_member, self.logsheet))
        self.assertFalse(can_edit_logsheet(self.non_member, self.logsheet))

    def test_unauthenticated_cannot_edit(self):
        """Test that unauthenticated users cannot edit any logsheet"""
        # Test with unfinalized logsheet
        self.logsheet.finalized = False
        self.logsheet.save()
        self.assertFalse(can_edit_logsheet(None, self.logsheet))
        
        # Test with finalized logsheet
        self.logsheet.finalized = True
        self.logsheet.save()
        self.assertFalse(can_edit_logsheet(None, self.logsheet))

    def test_multiple_roles_still_work(self):
        """Test that users with multiple roles still work correctly"""
        # Create user with multiple roles
        multi_role_user = Member.objects.create_user(
            username="multirole",
            email="multi@test.com",
            treasurer=True,
            webmaster=True,
            duty_officer=True,
            membership_status="Full Member"
        )
        
        self.logsheet.finalized = True
        self.logsheet.save()
        
        # Should be able to unfinalize due to any of the roles
        self.assertTrue(can_unfinalize_logsheet(multi_role_user, self.logsheet))
        self.assertTrue(can_edit_logsheet(multi_role_user, self.logsheet))