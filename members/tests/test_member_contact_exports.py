import csv
import json
from io import StringIO

from django.contrib import admin
from django.test import TestCase
from tablib import Dataset

from members.admin import MemberAdmin
from members.models import EmergencyContact, Member
from members.resources import MemberResource


class MemberContactCSVTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create_user(
            username="csv.member",
            email="csv.member@example.com",
            first_name="CSV",
            last_name="Member",
            contact_visibility={"email": "hide", "address": "hide"},
        )
        EmergencyContact.objects.create(
            member=self.member,
            name="Jane Doe",
            relationship="Spouse",
            home_phone="555-0100",
            preferred_contact_method="home_phone",
            preferred_contact_details="Call after 5",
            address="1 Soaring Way, Lancaster",
        )

    def test_import_export_resource_round_trips_structured_contacts(self):
        dataset = MemberResource().export(Member.objects.filter(pk=self.member.pk))
        row = dataset.dict[0]

        self.assertEqual(
            json.loads(row["emergency_contacts"]),
            [
                {
                    "name": "Jane Doe",
                    "relationship": "Spouse",
                    "home_phone": "555-0100",
                    "mobile_phone": "",
                    "preferred_contact_method": "home_phone",
                    "preferred_contact_details": "Call after 5",
                    "address": "1 Soaring Way, Lancaster",
                }
            ],
        )
        self.assertEqual(
            json.loads(row["contact_visibility"]),
            {"email": "hide", "address": "hide"},
        )

        self.member.emergency_contacts.all().delete()
        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        contact = self.member.emergency_contacts.get()
        self.assertEqual(contact.name, "Jane Doe")
        self.assertEqual(contact.preferred_contact_details, "Call after 5")
        self.assertEqual(contact.address, "1 Soaring Way, Lancaster")

    def test_import_export_resource_round_trips_contact_visibility_for_new_member(self):
        exported = MemberResource().export(Member.objects.filter(pk=self.member.pk))
        row = exported.dict[0]
        row["id"] = ""
        row["username"] = "restored.member"
        dataset = Dataset(headers=exported.headers)
        dataset.append(tuple(row[field] for field in exported.headers))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        restored_member = Member.objects.get(username="restored.member")
        self.assertEqual(
            restored_member.contact_visibility,
            {"email": "hide", "address": "hide"},
        )

    def test_empty_contacts_array_clears_structured_contacts(self):
        dataset = Dataset(headers=["id", "username", "emergency_contacts"])
        dataset.append((self.member.pk, self.member.username, "[]"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertFalse(self.member.emergency_contacts.exists())

    def test_legacy_import_without_contacts_column_preserves_contacts(self):
        dataset = Dataset(headers=["id", "username"])
        dataset.append((self.member.pk, self.member.username))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertEqual(self.member.emergency_contacts.get().name, "Jane Doe")

    def test_invalid_replacement_contact_preserves_existing_contacts(self):
        invalid_contacts = [
            [{"name": "Invalid Contact", "preferred_contact_method": "carrier_pigeon"}],
            [{"name": "N" * 201}],
            [{"name": "Invalid Contact", "home_phone": "1" * 21}],
        ]

        for contacts in invalid_contacts:
            with self.subTest(contacts=contacts):
                dataset = Dataset(headers=["id", "username", "emergency_contacts"])
                dataset.append(
                    (
                        self.member.pk,
                        self.member.username,
                        json.dumps(contacts),
                    )
                )
                result = MemberResource().import_data(dataset, dry_run=False)

                self.assertTrue(result.has_validation_errors())
                self.assertEqual(
                    list(self.member.emergency_contacts.values_list("name", flat=True)),
                    ["Jane Doe"],
                )

    def test_invalid_contact_visibility_is_rejected_without_changing_preferences(self):
        invalid_visibility_values = (
            "invalid json",
            "[]",
            '{"unexpected":"hide"}',
            '{"email":"hidden"}',
        )
        for visibility in invalid_visibility_values:
            with self.subTest(visibility=visibility):
                dataset = Dataset(headers=["id", "username", "contact_visibility"])
                dataset.append((self.member.pk, self.member.username, visibility))

                result = MemberResource().import_data(dataset, dry_run=False)

                self.assertTrue(result.has_errors())
                self.member.refresh_from_db()
                self.assertEqual(
                    self.member.contact_visibility,
                    {"email": "hide", "address": "hide"},
                )

    def test_custom_admin_csv_action_includes_structured_contacts(self):
        member_admin = MemberAdmin(Member, admin.site)
        response = member_admin.export_members_csv(
            request=None,
            queryset=Member.objects.filter(pk=self.member.pk),
        )

        reader = csv.DictReader(StringIO(response.content.decode()))
        row = next(reader)

        self.assertEqual(
            json.loads(row["emergency_contacts"])[0]["name"],
            "Jane Doe",
        )
        self.assertEqual(
            json.loads(row["contact_visibility"]),
            {"email": "hide", "address": "hide"},
        )
