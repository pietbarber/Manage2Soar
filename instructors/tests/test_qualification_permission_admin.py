import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from instructors.models import (
    ClubQualificationType,
    GroundInstruction,
    QualificationPermissionGrant,
)
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


@pytest.mark.django_db
class ClubQualificationTypeAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        cls.admin = Member.objects.create_superuser(
            username="qualification-admin",
            email="qualification-admin@example.com",
            password="secret",
            membership_status="Full Member",
        )
        cls.staff = Member.objects.create_user(
            username="qualification-staff",
            email="qualification-staff@example.com",
            password="secret",
            is_staff=True,
            membership_status="Full Member",
        )
        Member.objects.filter(pk=cls.staff.pk).update(is_active=True)
        change_permissions = Permission.objects.filter(
            content_type__app_label="instructors",
            content_type__model="clubqualificationtype",
            codename__in=(
                "add_clubqualificationtype",
                "change_clubqualificationtype",
                "view_clubqualificationtype",
            ),
        )
        cls.staff.user_permissions.add(*change_permissions)

        cls.group = cls._make_bundle("Qualification bundle")
        cls.replacement_group = cls._make_bundle("Replacement bundle")
        cls.qualification = ClubQualificationType.objects.create(
            code="TEST-QUAL",
            name="Test qualification",
            permission_group=cls.group,
        )
        cls.url = reverse(
            "admin:instructors_clubqualificationtype_change",
            args=(cls.qualification.pk,),
        )

    @classmethod
    def _make_bundle(cls, name):
        group = Group.objects.create(name=name)
        RoleMetadata.objects.create(
            group=group,
            key=name.lower().replace(" ", "-"),
            display_name=name,
            qualification_permission_bundle=True,
        )
        permission, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(GroundInstruction),
            codename="can_manage_ground_instruction",
            defaults={"name": "Can manage ground instruction"},
        )
        group.permissions.add(permission)
        QualificationPermissionGrant.objects.create(
            group=group,
            permission=permission,
        )
        return group

    def test_active_superuser_sees_and_can_change_mapping(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="permission_group"')

        response = self.client.post(
            self.url,
            {
                "code": "TEST-QUAL",
                "name": "Renamed qualification",
                "applies_to": "both",
                "is_obsolete": "",
                "tooltip": "",
                "permission_group": self.replacement_group.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.qualification.refresh_from_db()
        self.assertEqual(
            self.qualification.permission_group_id, self.replacement_group.pk
        )

    def test_staff_can_edit_normal_fields_but_mapping_is_hidden_and_preserved(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="permission_group"')
        self.assertNotContains(response, self.group.name)

        response = self.client.post(
            self.url,
            {
                "code": "TEST-QUAL",
                "name": "Staff-edited qualification",
                "applies_to": "student",
                "is_obsolete": "",
                "tooltip": "Updated by staff",
                "permission_group": self.replacement_group.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.qualification.refresh_from_db()
        self.assertEqual(self.qualification.name, "Staff-edited qualification")
        self.assertEqual(self.qualification.applies_to, "student")
        self.assertEqual(
            self.qualification.permission_group_id,
            self.group.pk,
        )
