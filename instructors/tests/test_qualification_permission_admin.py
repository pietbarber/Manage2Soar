import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from instructors.models import GroundInstruction, QualificationPermissionGrant
from members.models import Member, RoleMetadata
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
class QualificationPermissionGrantAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        cls.admin = Member.objects.create_superuser(
            username="qa-admin",
            email="qa-admin@example.com",
            password="secret",
            membership_status="Full Member",
        )
        cls.user = Member.objects.create_user(
            username="qa-user",
            email="qa-user@example.com",
            password="secret",
            is_staff=True,
            membership_status="Full Member",
        )
        Member.objects.filter(pk=cls.user.pk).update(is_active=True)
        cls.user.refresh_from_db()
        cls.group = Group.objects.create(name="Qualification actions")
        RoleMetadata.objects.create(
            group=cls.group,
            key="qualification-actions",
            display_name="Qualification actions",
            qualification_permission_bundle=True,
        )
        cls.safe, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(GroundInstruction),
            codename="can_manage_ground_instruction",
            defaults={"name": "Can manage ground instruction"},
        )
        cls.unsafe = Permission.objects.get(
            content_type__app_label="members",
            content_type__model="member",
            codename="change_member",
        )
        cls.group.permissions.add(cls.safe, cls.unsafe)
        cls.url = reverse("admin:instructors_qualificationpermissiongrant_changelist")

    def test_superuser_can_manage_grants(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        add_url = reverse("admin:instructors_qualificationpermissiongrant_add")
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qualification actions")
        self.assertContains(response, self.safe.name)
        self.assertNotContains(response, self.unsafe.name)

    def test_non_superuser_cannot_access_or_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        add_url = reverse("admin:instructors_qualificationpermissiongrant_add")
        self.assertEqual(self.client.post(add_url, {}).status_code, 403)

    def test_admin_creates_grant_from_group_permission(self):
        self.client.force_login(self.admin)
        add_url = reverse("admin:instructors_qualificationpermissiongrant_add")
        response = self.client.post(
            add_url, {"group": self.group.pk, "permission": self.safe.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            QualificationPermissionGrant.objects.filter(
                group=self.group, permission=self.safe
            ).exists()
        )

    def test_unsafe_and_non_bundle_group_are_not_choices(self):
        from instructors.admin import QualificationPermissionGrantAdminForm

        form = QualificationPermissionGrantAdminForm(data={"group": self.group.pk})
        self.assertIn(self.safe, form.fields["permission"].queryset)
        self.assertNotIn(self.unsafe, form.fields["permission"].queryset)
        protected = Group.objects.create(name="Protected")
        RoleMetadata.objects.create(
            group=protected,
            key="protected-test",
            display_name="Protected",
            is_protected=True,
        )
        self.assertNotIn(protected, form.fields["group"].queryset)
