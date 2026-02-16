"""
Tests for bulk qualification assignment (Issue #339).

Covers the BulkQualificationAssignForm and bulk_assign_qualification view,
including permission checks, form validation, and creation of
MemberQualification records.
"""

import pytest
from django.test import TestCase
from django.urls import reverse

from instructors.forms import BulkQualificationAssignForm
from instructors.models import ClubQualificationType, MemberQualification
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
class TestBulkQualificationAssignForm(TestCase):
    """Tests for the BulkQualificationAssignForm."""

    @classmethod
    def setUpTestData(cls):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        MembershipStatus.objects.get_or_create(
            name="Inactive", defaults={"is_active": False}
        )

        cls.qual = ClubQualificationType.objects.create(
            code="SM2026",
            name="Safety Meeting 2026",
            applies_to="both",
        )
        cls.obsolete_qual = ClubQualificationType.objects.create(
            code="OBSOLETE",
            name="Obsolete Qualification",
            applies_to="both",
            is_obsolete=True,
        )

        cls.member1 = Member.objects.create_user(
            username="member1",
            first_name="Alice",
            last_name="Aaronson",
            email="alice@example.com",
            password="testpass123",
            membership_status="Full Member",
        )
        cls.member2 = Member.objects.create_user(
            username="member2",
            first_name="Bob",
            last_name="Baker",
            email="bob@example.com",
            password="testpass123",
            membership_status="Full Member",
        )
        cls.inactive_member = Member.objects.create_user(
            username="inactive",
            first_name="Charlie",
            last_name="Clark",
            email="charlie@example.com",
            password="testpass123",
            membership_status="Inactive",
        )
        cls.instructor = Member.objects.create_user(
            username="instructor",
            first_name="Instructor",
            last_name="Smith",
            email="instr@example.com",
            password="testpass123",
            membership_status="Full Member",
            instructor=True,
        )

    def test_form_valid_with_members_selected(self):
        """Form is valid when qualification and at least one member selected."""
        form = BulkQualificationAssignForm(
            data={
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk, self.member2.pk],
            }
        )
        assert form.is_valid(), form.errors

    def test_form_invalid_without_members(self):
        """Form is invalid when no members are selected."""
        form = BulkQualificationAssignForm(
            data={
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [],
            }
        )
        assert not form.is_valid()
        assert "members" in form.errors

    def test_form_invalid_without_qualification(self):
        """Form is invalid when no qualification is selected."""
        form = BulkQualificationAssignForm(
            data={
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk],
            }
        )
        assert not form.is_valid()
        assert "qualification" in form.errors

    def test_form_excludes_obsolete_qualifications(self):
        """Obsolete qualifications should not appear in the dropdown."""
        form = BulkQualificationAssignForm()
        qual_qs = form.fields["qualification"].queryset
        assert self.qual in qual_qs
        assert self.obsolete_qual not in qual_qs

    def test_form_excludes_inactive_members(self):
        """Inactive members should not appear in the member checklist."""
        form = BulkQualificationAssignForm()
        member_qs = form.fields["members"].queryset
        assert self.member1 in member_qs
        assert self.member2 in member_qs
        assert self.inactive_member not in member_qs

    def test_form_save_creates_qualifications(self):
        """Saving creates MemberQualification records for selected members."""
        form = BulkQualificationAssignForm(
            data={
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk, self.member2.pk],
            }
        )
        assert form.is_valid()
        created, updated = form.save(instructor=self.instructor)
        assert created == 2
        assert updated == 0
        assert MemberQualification.objects.filter(qualification=self.qual).count() == 2

    def test_form_save_updates_existing_qualifications(self):
        """Saving updates existing records rather than creating duplicates."""
        MemberQualification.objects.create(
            member=self.member1,
            qualification=self.qual,
            is_qualified=True,
            date_awarded="2025-01-01",
            notes="Old note",
        )
        form = BulkQualificationAssignForm(
            data={
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "notes": "New note",
                "members": [self.member1.pk, self.member2.pk],
            }
        )
        assert form.is_valid()
        created, updated = form.save(instructor=self.instructor)
        assert created == 1
        assert updated == 1
        # Verify the existing record was updated
        mq = MemberQualification.objects.get(
            member=self.member1, qualification=self.qual
        )
        assert mq.notes == "New note"
        assert str(mq.date_awarded) == "2026-02-15"

    def test_form_save_sets_instructor(self):
        """The instructor field is set on all created records."""
        form = BulkQualificationAssignForm(
            data={
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk],
            }
        )
        assert form.is_valid()
        form.save(instructor=self.instructor)
        mq = MemberQualification.objects.get(
            member=self.member1, qualification=self.qual
        )
        assert mq.instructor == self.instructor

    def test_form_save_with_expiration_date(self):
        """Expiration date is saved when provided."""
        form = BulkQualificationAssignForm(
            data={
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "expiration_date": "2027-02-15",
                "members": [self.member1.pk],
            }
        )
        assert form.is_valid()
        form.save(instructor=self.instructor)
        mq = MemberQualification.objects.get(
            member=self.member1, qualification=self.qual
        )
        assert str(mq.expiration_date) == "2027-02-15"

    def test_form_save_without_expiration_date(self):
        """Expiration date is None when not provided."""
        form = BulkQualificationAssignForm(
            data={
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk],
            }
        )
        assert form.is_valid()
        form.save(instructor=self.instructor)
        mq = MemberQualification.objects.get(
            member=self.member1, qualification=self.qual
        )
        assert mq.expiration_date is None


@pytest.mark.django_db
class TestBulkAssignQualificationView(TestCase):
    """Tests for the bulk_assign_qualification view."""

    @classmethod
    def setUpTestData(cls):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )

        cls.qual = ClubQualificationType.objects.create(
            code="SM2026",
            name="Safety Meeting 2026",
            applies_to="both",
        )

        cls.instructor = Member.objects.create_user(
            username="instructor",
            first_name="Test",
            last_name="Instructor",
            email="instr@example.com",
            password="testpass123",
            membership_status="Full Member",
            instructor=True,
        )
        cls.safety_officer = Member.objects.create_user(
            username="safety_officer",
            first_name="Safety",
            last_name="Officer",
            email="safety@example.com",
            password="testpass123",
            membership_status="Full Member",
            safety_officer=True,
        )
        cls.regular_member = Member.objects.create_user(
            username="regular",
            first_name="Regular",
            last_name="Member",
            email="regular@example.com",
            password="testpass123",
            membership_status="Full Member",
        )
        cls.superuser = Member.objects.create_superuser(
            username="admin",
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            password="testpass123",
            membership_status="Full Member",
        )
        cls.member1 = Member.objects.create_user(
            username="member1",
            first_name="Alice",
            last_name="Aaronson",
            email="alice@example.com",
            password="testpass123",
            membership_status="Full Member",
        )
        cls.member2 = Member.objects.create_user(
            username="member2",
            first_name="Bob",
            last_name="Baker",
            email="bob@example.com",
            password="testpass123",
            membership_status="Full Member",
        )

        cls.url = reverse("instructors:bulk_assign_qualification")

    def test_instructor_can_access(self):
        """Instructors can access the bulk assignment page."""
        self.client.force_login(self.instructor)
        response = self.client.get(self.url)
        assert response.status_code == 200

    def test_safety_officer_can_access(self):
        """Safety officers can access the bulk assignment page."""
        self.client.force_login(self.safety_officer)
        response = self.client.get(self.url)
        assert response.status_code == 200

    def test_superuser_can_access(self):
        """Superusers can access the bulk assignment page."""
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        assert response.status_code == 200

    def test_regular_member_denied(self):
        """Regular members without instructor/safety officer role get 403."""
        self.client.force_login(self.regular_member)
        response = self.client.get(self.url)
        assert response.status_code == 403

    def test_anonymous_user_redirected(self):
        """Anonymous users are redirected to login."""
        response = self.client.get(self.url)
        assert response.status_code == 302

    def test_get_renders_form(self):
        """GET request renders the form with member checklist."""
        self.client.force_login(self.instructor)
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert "form" in response.context
        assert b"Bulk Assign Qualification" in response.content

    def test_post_creates_qualifications(self):
        """POST with valid data creates qualification records."""
        self.client.force_login(self.instructor)
        response = self.client.post(
            self.url,
            {
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk, self.instructor.pk],
            },
        )
        assert response.status_code == 302  # redirect on success
        assert MemberQualification.objects.filter(qualification=self.qual).count() == 2

    def test_post_invalid_shows_errors(self):
        """POST with missing members re-renders form with errors."""
        self.client.force_login(self.instructor)
        response = self.client.post(
            self.url,
            {
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [],
            },
        )
        assert response.status_code == 200  # re-render, not redirect
        assert "form" in response.context
        assert response.context["form"].errors

    def test_success_message_created(self):
        """Success message reflects how many records were created."""
        self.client.force_login(self.instructor)
        response = self.client.post(
            self.url,
            {
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk],
            },
            follow=True,
        )
        assert response.status_code == 200
        messages_list = list(response.context["messages"])
        assert len(messages_list) == 1
        assert "1 member assigned" in str(messages_list[0])

    def test_success_message_updated(self):
        """Success message reflects updated records when re-assigning."""
        MemberQualification.objects.create(
            member=self.member1,
            qualification=self.qual,
            is_qualified=True,
            date_awarded="2025-01-01",
        )
        self.client.force_login(self.instructor)
        response = self.client.post(
            self.url,
            {
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk],
            },
            follow=True,
        )
        messages_list = list(response.context["messages"])
        assert "1 existing record updated" in str(messages_list[0])

    def test_success_message_mixed_create_and_update(self):
        """Success message shows both created and updated when processing both."""
        # Create a qualification for member1 beforehand
        MemberQualification.objects.create(
            member=self.member1,
            qualification=self.qual,
            is_qualified=True,
            date_awarded="2025-01-01",
        )
        # Submit for both member1 (existing) and member2 (new)
        self.client.force_login(self.instructor)
        response = self.client.post(
            self.url,
            {
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk, self.member2.pk],
            },
            follow=True,
        )
        messages_list = list(response.context["messages"])
        assert len(messages_list) == 1
        message_text = str(messages_list[0])
        # Should mention both created and updated
        assert "1 member assigned" in message_text
        assert "1 existing record updated" in message_text

    def test_safety_officer_can_post(self):
        """Safety officer can POST to create qualifications."""
        self.client.force_login(self.safety_officer)
        response = self.client.post(
            self.url,
            {
                "qualification": self.qual.pk,
                "date_awarded": "2026-02-15",
                "members": [self.member1.pk],
            },
        )
        assert response.status_code == 302
        mq = MemberQualification.objects.get(
            member=self.member1, qualification=self.qual
        )
        assert mq.instructor == self.safety_officer
