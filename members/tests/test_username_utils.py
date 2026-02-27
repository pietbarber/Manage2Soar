"""
Tests for the generate_username utility (members.utils.username).
"""

from django.test import TestCase

from members.models import Member
from members.utils.username import generate_username


class GenerateUsernameTests(TestCase):
    """Unit tests for the generate_username utility function."""

    def test_basic_generation(self):
        """Simple first/last name produces firstname.lastname."""
        username = generate_username("John", "Smith")
        self.assertEqual(username, "john.smith")

    def test_lowercased(self):
        """Result is always lower-case regardless of input case."""
        username = generate_username("JANE", "DOE")
        self.assertEqual(username, "jane.doe")

    def test_strips_hyphens(self):
        """Hyphens in compound names are stripped."""
        username = generate_username("Jean-Paul", "Smith")
        self.assertEqual(username, "jeanpaul.smith")

    def test_strips_spaces_in_name(self):
        """Spaces within a name fragment are stripped."""
        username = generate_username("Mary Ann", "Jones")
        self.assertEqual(username, "maryann.jones")

    def test_strips_non_alpha_last_name(self):
        """Non-alphabetic characters in the last name are stripped."""
        username = generate_username("John", "de Villiers")
        self.assertEqual(username, "john.devilliers")

    def test_collision_appends_counter(self):
        """When base username is taken, a numeric suffix is appended."""
        Member.objects.create_user(
            username="john.smith",
            email="john.smith@example.com",
            first_name="John",
            last_name="Smith",
        )
        username = generate_username("John", "Smith")
        self.assertEqual(username, "john.smith1")

    def test_collision_increments_counter(self):
        """Counter continues incrementing until a free slot is found."""
        Member.objects.create_user(
            username="john.smith",
            email="john.smith@example.com",
            first_name="John",
            last_name="Smith",
        )
        Member.objects.create_user(
            username="john.smith1",
            email="john.smith2@example.com",
            first_name="John",
            last_name="Smith",
        )
        username = generate_username("John", "Smith")
        self.assertEqual(username, "john.smith2")

    def test_returned_username_is_unique(self):
        """The returned username does not already exist in the database."""
        # Pre-populate several collisions.
        for i in ["", "1", "2", "3"]:
            suffix = i
            Member.objects.create_user(
                username=f"alice.walker{suffix}",
                email=f"alice{suffix}@example.com",
                first_name="Alice",
                last_name="Walker",
            )
        username = generate_username("Alice", "Walker")
        self.assertFalse(
            Member.objects.filter(username=username).exists(),
            f"generate_username returned an already-taken username: {username!r}",
        )
