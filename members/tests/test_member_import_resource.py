from django.test import TestCase
from tablib import Dataset

from members.models import Member
from members.resources import MemberResource


class MemberImportResourceTests(TestCase):
    """Regression tests for member CSV import normalization."""

    def test_null_like_ssa_values_are_stored_as_none(self):
        dataset = Dataset(headers=["username", "SSA_member_number"])
        dataset.append(("pilot.alpha", "NULL"))
        dataset.append(("pilot.beta", "0"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertIsNone(Member.objects.get(username="pilot.alpha").SSA_member_number)
        self.assertIsNone(Member.objects.get(username="pilot.beta").SSA_member_number)

    def test_real_ssa_value_is_trimmed_and_preserved(self):
        dataset = Dataset(headers=["username", "SSA_member_number"])
        dataset.append(("pilot.gamma", " 12345 "))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertEqual(
            Member.objects.get(username="pilot.gamma").SSA_member_number, "12345"
        )

    def test_null_like_legacy_username_values_are_stored_as_none(self):
        dataset = Dataset(headers=["username", "legacy_username"])
        dataset.append(("pilot.delta", "NULL"))
        dataset.append(("pilot.echo", ""))
        dataset.append(("pilot.foxtrot", "0"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertIsNone(Member.objects.get(username="pilot.delta").legacy_username)
        self.assertIsNone(Member.objects.get(username="pilot.echo").legacy_username)
        self.assertIsNone(Member.objects.get(username="pilot.foxtrot").legacy_username)

    def test_blank_username_is_generated_from_names(self):
        dataset = Dataset(headers=["username", "first_name", "last_name"])
        dataset.append(("", "Jane", "Doe"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertTrue(Member.objects.filter(username="jane.doe").exists())

    def test_duplicate_usernames_are_auto_resolved(self):
        Member.objects.create_user(username="jane.doe", email="existing@example.com")

        dataset = Dataset(headers=["username", "first_name", "last_name"])
        dataset.append(("jane.doe", "Jane", "Doe"))
        dataset.append(("jane.doe", "Jane", "Doe"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertEqual(Member.objects.filter(username="jane.doe").count(), 1)
        self.assertTrue(Member.objects.filter(username="jane.doe1").exists())
        self.assertTrue(Member.objects.filter(username="jane.doe2").exists())

    def test_case_variant_username_is_normalized_and_deduplicated(self):
        Member.objects.create_user(username="jane.doe", email="existing@example.com")

        dataset = Dataset(headers=["username", "first_name", "last_name"])
        dataset.append(("Jane.Doe", "Jane", "Doe"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertTrue(Member.objects.filter(username="jane.doe1").exists())

    def test_invalid_username_falls_back_to_generated_username(self):
        dataset = Dataset(headers=["username", "first_name", "last_name"])
        dataset.append(("!!!", "Chris", "Pine"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertTrue(Member.objects.filter(username="chris.pine").exists())

    def test_same_file_new_rows_with_identical_username_are_auto_suffixed(self):
        """Two brand-new rows sharing the same explicit username must not collide.

        This exercises the batch-reservation logic for new instances (pk=None):
        the second row must detect the first row's reservation and be assigned
        a suffixed username instead of failing the DB unique constraint.
        """
        dataset = Dataset(headers=["username", "first_name", "last_name"])
        dataset.append(("sam.jones", "Sam", "Jones"))
        dataset.append(("sam.jones", "Sam", "Jones"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertEqual(Member.objects.filter(username="sam.jones").count(), 1)
        self.assertTrue(Member.objects.filter(username="sam.jones1").exists())

    def test_update_by_id_rename_releases_old_username_in_same_import(self):
        """Renaming an existing member by id should free the old username key.

        This verifies in-memory username tracking stays consistent when an
        existing member is renamed and a later row in the same file claims the
        just-freed username.
        """
        existing = Member.objects.create_user(
            username="pilot.old", email="existing@example.com"
        )

        dataset = Dataset(headers=["id", "username", "first_name", "last_name"])
        dataset.append((str(existing.pk), "pilot.new", "Pilot", "Renamed"))
        dataset.append(("", "pilot.old", "New", "Member"))

        result = MemberResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        existing.refresh_from_db()
        self.assertEqual(existing.username, "pilot.new")
        self.assertEqual(Member.objects.filter(username="pilot.old").count(), 1)
