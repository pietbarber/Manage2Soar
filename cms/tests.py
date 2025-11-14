from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from .admin import VisitorContactAdmin
from .forms import VisitorContactForm
from .models import VisitorContact

User = get_user_model()


class VisitorContactModelTests(TestCase):
    """Test the VisitorContact model functionality."""

    def test_create_visitor_contact(self):
        """Test creating a visitor contact with all fields."""
        contact = VisitorContact.objects.create(
            name="John Doe",
            email="john@example.com",
            phone="555-123-4567",
            subject="Interested in gliding lessons",
            message="I'd like to learn more about your training programs.",
            ip_address="192.168.1.100",
        )

        self.assertEqual(contact.name, "John Doe")
        self.assertEqual(contact.email, "john@example.com")
        self.assertEqual(contact.phone, "555-123-4567")
        self.assertEqual(contact.subject, "Interested in gliding lessons")
        self.assertEqual(contact.status, "new")  # Default status
        self.assertIsNotNone(contact.submitted_at)

    def test_visitor_contact_str_method(self):
        """Test the string representation of VisitorContact."""
        contact = VisitorContact.objects.create(
            name="Jane Smith",
            email="jane@example.com",
            subject="Club membership inquiry",
            message="How do I join?",
        )

        expected_str = f"Jane Smith - Club membership inquiry ({contact.submitted_at.strftime('%Y-%m-%d')})"
        self.assertEqual(str(contact), expected_str)

    def test_visitor_contact_ordering(self):
        """Test that contacts are ordered by submission date (newest first)."""
        contact1 = VisitorContact.objects.create(
            name="First Contact",
            email="first@example.com",
            subject="First subject",
            message="First message",
        )
        contact2 = VisitorContact.objects.create(
            name="Second Contact",
            email="second@example.com",
            subject="Second subject",
            message="Second message",
        )

        contacts = list(VisitorContact.objects.all())
        self.assertEqual(contacts[0], contact2)  # Newest first
        self.assertEqual(contacts[1], contact1)


class VisitorContactFormTests(TestCase):
    """Test the VisitorContactForm validation and functionality."""

    def test_valid_form(self):
        """Test that a valid form passes validation."""
        form_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-123-4567",
            "subject": "Interested in lessons",
            "message": "I would like to learn more about your gliding programs.",
        }
        form = VisitorContactForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_required_fields(self):
        """Test that required fields are enforced."""
        form = VisitorContactForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("subject", form.errors)
        self.assertIn("message", form.errors)

    def test_phone_optional(self):
        """Test that phone field is optional."""
        form_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "subject": "Test subject",
            "message": "This is a test message with sufficient length.",
        }
        form = VisitorContactForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_email_validation(self):
        """Test email validation including spam domain blocking."""
        # Test invalid email format
        form_data = {
            "name": "John Doe",
            "email": "not-an-email",
            "subject": "Test",
            "message": "Test message with enough length.",
        }
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

        # Test spam domain blocking
        form_data["email"] = "spammer@tempmail.org"
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_message_length_validation(self):
        """Test message minimum length validation."""
        form_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "subject": "Test",
            "message": "Short",  # Too short
        }
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)

    def test_spam_keyword_detection(self):
        """Test that spam keywords are detected in messages."""
        form_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "subject": "Test",
            "message": "Click here to win money from casino lottery!",
        }
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)


class VisitorContactViewTests(TestCase):
    """Test the visitor contact views."""

    def setUp(self):
        self.client = Client()
        # Create SiteConfiguration for testing
        from siteconfig.models import SiteConfiguration

        self.site_config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="test.example.com",
            club_abbreviation="TSC",
        )

    def test_contact_page_get(self):
        """Test that the contact page loads successfully."""
        response = self.client.get(reverse("cms:contact"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contact Test Soaring Club")
        self.assertContains(response, "form")

    def test_contact_page_no_auth_required(self):
        """Test that the contact page doesn't require authentication."""
        # Ensure no user is logged in
        response = self.client.get(reverse("cms:contact"))
        self.assertEqual(response.status_code, 200)

    @patch("django.core.mail.send_mail")
    def test_contact_form_submission_success(self, mock_send_mail):
        """Test successful contact form submission."""
        # Create a member manager to receive the email
        manager = User.objects.create_user(
            username="manager",
            email="manager@skylinesoaring.org",
            membership_status="Full Member",
        )
        manager.member_manager = True
        manager.save()

        form_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-123-4567",
            "subject": "Interested in lessons",
            "message": "I would like to learn more about your gliding programs.",
        }

        response = self.client.post(reverse("cms:contact"), data=form_data)

        # Should redirect to success page
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("cms:contact_success"))

        # Check that contact was created
        self.assertEqual(VisitorContact.objects.count(), 1)
        contact = VisitorContact.objects.get(email="john@example.com")
        self.assertEqual(contact.name, "John Doe")
        self.assertEqual(contact.email, "john@example.com")

        # Check that email was sent
        mock_send_mail.assert_called_once()

    def test_contact_form_submission_invalid(self):
        """Test contact form submission with invalid data."""
        form_data = {
            "name": "",  # Required field missing
            "email": "invalid-email",
            "subject": "",
            "message": "Short",
        }

        response = self.client.post(reverse("cms:contact"), data=form_data)

        # Should stay on the same page with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")

        # No contact should be created
        self.assertEqual(VisitorContact.objects.count(), 0)

    def test_contact_success_page(self):
        """Test that the contact success page loads."""
        response = self.client.get(reverse("cms:contact_success"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message Sent Successfully")

    @patch("cms.views._get_client_ip")
    def test_ip_address_capture(self, mock_get_ip):
        """Test that IP address is captured during form submission."""
        mock_get_ip.return_value = "192.168.1.100"

        form_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "subject": "Test subject",
            "message": "This is a test message with sufficient length.",
        }

        self.client.post(reverse("cms:contact"), data=form_data)

        contact = VisitorContact.objects.get(email="john@example.com")
        self.assertEqual(contact.ip_address, "192.168.1.100")
        mock_get_ip.assert_called_once()


class VisitorContactEmailTests(TestCase):
    """Test email notification functionality."""

    def setUp(self):
        # Create member managers
        self.member_manager = User.objects.create_user(
            username="manager1",
            email="manager1@skylinesoaring.org",
            first_name="Manager",
            last_name="One",
            membership_status="Full Member",
        )
        self.member_manager.member_manager = True
        self.member_manager.save()

        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@skylinesoaring.org",
            first_name="Web",
            last_name="Master",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

    def test_email_sent_to_member_managers(self):
        """Test that emails are sent to member managers."""
        # Submit form to trigger email
        form_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "subject": "Test inquiry",
            "message": "This is a test message with sufficient length.",
        }

        self.client.post(reverse("cms:contact"), data=form_data)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        self.assertIn("New Visitor Contact", email.subject)
        self.assertIn("john@example.com", email.body)
        self.assertIn("Test inquiry", email.body)
        self.assertIn(self.member_manager.email, email.to)

    def test_fallback_to_webmasters(self):
        """Test fallback to webmasters when no member managers exist."""
        # Remove member manager privilege
        self.member_manager.member_manager = False
        self.member_manager.save()

        form_data = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "subject": "Another test",
            "message": "This is another test message with sufficient length.",
        }

        self.client.post(reverse("cms:contact"), data=form_data)

        # Should send to webmaster instead
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn(self.webmaster.email, email.to)


class VisitorContactAdminTests(TestCase):
    """Test the admin interface for visitor contacts."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@skylinesoaring.org",
            is_staff=True,
            is_superuser=True,
        )

        self.contact = VisitorContact.objects.create(
            name="John Doe",
            email="john@example.com",
            subject="Test inquiry",
            message="This is a test message.",
            ip_address="192.168.1.100",
        )

    def test_admin_registration(self):
        """Test that VisitorContact is registered in admin."""
        from django.contrib import admin

        self.assertIn(VisitorContact, admin.site._registry)

    def test_admin_list_display(self):
        """Test admin list display fields."""
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())

        expected_fields = [
            "submitted_at",
            "name",
            "email",
            "subject",
            "status",
            "handled_by_name",
            "ip_display",
        ]
        self.assertEqual(list(admin_class.list_display), expected_fields)

    def test_admin_readonly_fields(self):
        """Test that submission data is readonly in admin."""
        factory = RequestFactory()
        request = factory.get("/admin/cms/visitorcontact/")
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())
        readonly_fields = admin_class.get_readonly_fields(request, self.contact)

        # Contact details should be readonly when editing
        self.assertIn("name", readonly_fields)
        self.assertIn("email", readonly_fields)
        self.assertIn("subject", readonly_fields)
        self.assertIn("message", readonly_fields)
        # Security: prevent manual assignment
        self.assertIn("handled_by", readonly_fields)

    def test_admin_no_add_permission(self):
        """Test that contacts cannot be manually created in admin."""
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())
        request = MagicMock()
        request.user = self.admin_user

        self.assertFalse(admin_class.has_add_permission(request))

    def test_admin_bulk_actions(self):
        """Test admin bulk actions for status updates."""
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())

        expected_actions = ["mark_read", "mark_responded", "mark_closed"]
        action_names = []
        if admin_class.actions:
            for action in admin_class.actions:
                if hasattr(action, "__name__"):
                    action_names.append(action.__name__)
                else:
                    action_names.append(str(action))

        for expected_action in expected_actions:
            self.assertIn(expected_action, action_names)


class VisitorContactIntegrationTests(TestCase):
    """Integration tests for the complete visitor contact workflow."""

    def setUp(self):
        self.member_manager = User.objects.create_user(
            username="manager",
            email="manager@skylinesoaring.org",
            first_name="Member",
            last_name="Manager",
            membership_status="Full Member",
        )
        self.member_manager.member_manager = True
        self.member_manager.save()

    def test_complete_contact_workflow(self):
        """Test the complete workflow from form submission to admin management."""
        # 1. Visitor submits contact form
        form_data = {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "phone": "555-987-6543",
            "subject": "Trial flight inquiry",
            "message": "I would like to schedule a trial flight to experience gliding.",
        }

        response = self.client.post(reverse("cms:contact"), data=form_data)

        # 2. Verify successful submission
        self.assertEqual(response.status_code, 302)
        self.assertEqual(VisitorContact.objects.count(), 1)

        # 3. Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("alice@example.com", email.body)
        self.assertIn("Trial flight inquiry", email.subject)

        # 4. Verify contact can be managed in admin
        contact = VisitorContact.objects.get(email="alice@example.com")
        self.assertEqual(contact.name, "Alice Johnson")
        self.assertEqual(contact.status, "new")

        # 5. Simulate admin updating status
        contact.status = "responded"
        contact.handled_by = self.member_manager
        contact.admin_notes = "Responded via email with trial flight options"
        contact.save()

        # 6. Verify updates
        updated_contact = VisitorContact.objects.get(email="alice@example.com")
        self.assertEqual(updated_contact.status, "responded")
        self.assertEqual(updated_contact.handled_by, self.member_manager)
        self.assertIsNotNone(updated_contact.admin_notes)
        self.assertIn("trial flight options", str(updated_contact.admin_notes))

    def test_url_accessibility(self):
        """Test that contact URLs are accessible at expected paths."""
        # Test /contact/ (through CMS app)
        response = self.client.get("/contact/")
        self.assertEqual(response.status_code, 200)

        # Test success page
        response = self.client.get("/contact/success/")
        self.assertEqual(response.status_code, 200)


class VisitorContactAdminSecurityTests(TestCase):
    """Security tests for the VisitorContact admin interface."""

    def setUp(self):
        # Create two users to test admin assignment security
        self.active_admin = User.objects.create_user(
            username="activeadmin",
            email="active@skylinesoaring.org",
            first_name="Active",
            last_name="Admin",
            is_staff=True,
            is_active=True,
            member_manager=True,
        )

        self.deceased_user = User.objects.create_user(
            username="deceasedmember",
            email="deceased@skylinesoaring.org",
            first_name="Deceased",
            last_name="Member",
            is_staff=True,
            is_active=False,  # Simulating deceased/inactive
            member_manager=True,
        )

        # Create a visitor contact
        self.contact = VisitorContact.objects.create(
            name="Test Visitor",
            email="visitor@example.com",
            subject="Test Subject",
            message="Test message",
            ip_address="192.168.1.100",
        )

        # Set up admin instance
        self.admin = VisitorContactAdmin(VisitorContact, AdminSite())

    def test_handled_by_readonly_on_edit(self):
        """Test that handled_by field becomes readonly when editing existing contact."""
        # Mock request
        from django.http import HttpRequest

        request = HttpRequest()
        request.user = self.active_admin

        # Check readonly fields for existing object
        readonly_fields = self.admin.get_readonly_fields(request, self.contact)

        # handled_by should be readonly when editing
        self.assertIn("handled_by", readonly_fields)
        # Contact details should also be readonly
        self.assertIn("name", readonly_fields)
        self.assertIn("email", readonly_fields)

    def test_save_model_sets_current_user(self):
        """Test that save_model always sets handled_by to current user."""
        from django.http import HttpRequest

        # Mock request
        request = HttpRequest()
        request.user = self.active_admin

        # Mock form with changed data
        form = MagicMock()
        # Initially, contact has no handler
        form.changed_data = ["status", "admin_notes"]
        self.assertIsNone(self.contact.handled_by)

        # Simulate admin save with current user
        self.admin.save_model(request, self.contact, form, change=True)

        # Should be set to current user, not allow manual assignment
        self.assertEqual(self.contact.handled_by, self.active_admin)

    def test_cannot_assign_to_different_user(self):
        """Test that handled_by cannot be manually set to a different user."""
        from django.http import HttpRequest

        # Mock request with active admin
        request = HttpRequest()
        request.user = self.active_admin

        # Mock form with changed data
        form = MagicMock()
        # Try to manually set to deceased user (security vulnerability)
        form.changed_data = ["status"]
        self.contact.handled_by = self.deceased_user

        # Admin save should override with current user
        self.admin.save_model(request, self.contact, form, change=True)

        # Should be current user, NOT the manually set deceased user
        self.assertEqual(self.contact.handled_by, self.active_admin)
        self.assertNotEqual(self.contact.handled_by, self.deceased_user)


# Role-based Access Control Tests for Issue #239


class PageRolePermissionModelTests(TestCase):
    """Test the PageRolePermission model functionality."""

    def setUp(self):
        from .models import Page, PageRolePermission

        self.page = Page.objects.create(
            title="Board Documents", slug="board-docs", is_public=False
        )

    def test_create_role_permission(self):
        """Test creating a role permission."""
        from .models import PageRolePermission

        perm = PageRolePermission.objects.create(page=self.page, role_name="director")

        self.assertEqual(perm.page, self.page)
        self.assertEqual(perm.role_name, "director")
        self.assertEqual(str(perm), "Board Documents - Director")

    def test_unique_constraint(self):
        """Test that the same role cannot be added twice to the same page."""
        from django.db import IntegrityError

        from .models import PageRolePermission

        PageRolePermission.objects.create(page=self.page, role_name="director")

        with self.assertRaises(IntegrityError):
            PageRolePermission.objects.create(page=self.page, role_name="director")

    def test_role_choices(self):
        """Test that all expected roles are available."""
        from .models import PageRolePermission

        expected_roles = [
            "instructor",
            "towpilot",
            "duty_officer",
            "assistant_duty_officer",
            "secretary",
            "treasurer",
            "webmaster",
            "director",
            "member_manager",
            "rostermeister",
        ]

        role_choices = [choice[0] for choice in PageRolePermission.ROLE_CHOICES]
        for role in expected_roles:
            self.assertIn(role, role_choices)


class PageAccessControlTests(TestCase):
    """Test the Page model access control functionality."""

    def setUp(self):
        from .models import Page

        self.public_page = Page.objects.create(
            title="Public Info", slug="public", is_public=True
        )
        self.private_page = Page.objects.create(
            title="Member Info", slug="member", is_public=False
        )
        self.role_restricted_page = Page.objects.create(
            title="Board Info", slug="board", is_public=False
        )

        # Set up users
        self.anonymous_user = User()  # Not authenticated
        self.member = User.objects.create_user(
            username="member", email="member@test.com", membership_status="Full Member"
        )
        self.director = User.objects.create_user(
            username="director",
            email="director@test.com",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

        self.instructor = User.objects.create_user(
            username="instructor",
            email="instructor@test.com",
            membership_status="Full Member",
        )
        self.instructor.instructor = True
        self.instructor.save()

    def test_public_page_access(self):
        """Test that public pages are accessible to everyone."""
        self.assertTrue(self.public_page.can_user_access(self.anonymous_user))
        self.assertTrue(self.public_page.can_user_access(self.member))
        self.assertTrue(self.public_page.can_user_access(self.director))

    def test_private_page_no_roles_access(self):
        """Test private page access without role restrictions."""
        # Anonymous user cannot access
        self.assertFalse(self.private_page.can_user_access(self.anonymous_user))
        # Active members can access
        self.assertTrue(self.private_page.can_user_access(self.member))
        self.assertTrue(self.private_page.can_user_access(self.director))

    def test_role_restricted_page_access(self):
        """Test access to role-restricted pages."""
        from .models import PageRolePermission

        # Add director role requirement
        PageRolePermission.objects.create(
            page=self.role_restricted_page, role_name="director"
        )

        # Anonymous user cannot access
        self.assertFalse(self.role_restricted_page.can_user_access(self.anonymous_user))
        # Regular member cannot access
        self.assertFalse(self.role_restricted_page.can_user_access(self.member))
        # Director can access
        self.assertTrue(self.role_restricted_page.can_user_access(self.director))
        # Instructor cannot access (not a director)
        self.assertFalse(self.role_restricted_page.can_user_access(self.instructor))

    def test_multiple_role_access(self):
        """Test access when multiple roles are allowed (OR logic)."""
        from .models import PageRolePermission

        # Allow both directors and instructors
        PageRolePermission.objects.create(
            page=self.role_restricted_page, role_name="director"
        )
        PageRolePermission.objects.create(
            page=self.role_restricted_page, role_name="instructor"
        )

        # Regular member still cannot access
        self.assertFalse(self.role_restricted_page.can_user_access(self.member))
        # Both director and instructor can access
        self.assertTrue(self.role_restricted_page.can_user_access(self.director))
        self.assertTrue(self.role_restricted_page.can_user_access(self.instructor))

    def test_page_validation_public_with_roles(self):
        """Test that public pages cannot have role restrictions."""
        from django.core.exceptions import ValidationError

        from .models import Page, PageRolePermission

        # Test that creating a role permission for public page fails at model level
        with self.assertRaises(ValidationError):
            PageRolePermission.objects.create(
                page=self.public_page, role_name="director"
            )

        # Test that adding role permission to existing public page also fails at page level
        # First create a private page with role permissions, then make it public
        private_page = Page.objects.create(
            title="Test Private",
            slug="test-private",
            content="Test content",
            is_public=False,
        )
        PageRolePermission.objects.create(page=private_page, role_name="director")

        # Now try to make it public (should fail validation)
        private_page.is_public = True
        with self.assertRaises(ValidationError):
            private_page.clean()

        # Clean up
        private_page.delete()

    def test_page_helper_methods(self):
        """Test the helper methods on Page model."""
        from .models import PageRolePermission

        # Test has_role_restrictions
        self.assertFalse(self.private_page.has_role_restrictions())
        PageRolePermission.objects.create(page=self.private_page, role_name="director")
        self.assertTrue(self.private_page.has_role_restrictions())

        # Test get_required_roles
        roles = self.private_page.get_required_roles()
        self.assertEqual(roles, ["director"])

        # Add another role
        PageRolePermission.objects.create(page=self.private_page, role_name="treasurer")
        roles = self.private_page.get_required_roles()
        self.assertIn("director", roles)
        self.assertIn("treasurer", roles)
        self.assertEqual(len(roles), 2)


class CMSRoleBasedViewTests(TestCase):
    """Test CMS views with role-based access control."""

    def setUp(self):
        from .models import Page, PageRolePermission

        # Create test pages
        self.public_page = Page.objects.create(
            title="Public Info", slug="public", is_public=True, content="Public content"
        )
        self.member_page = Page.objects.create(
            title="Member Info",
            slug="member",
            is_public=False,
            content="Member content",
        )
        self.board_page = Page.objects.create(
            title="Board Info", slug="board", is_public=False, content="Board content"
        )

        # Add role restrictions to board page
        PageRolePermission.objects.create(page=self.board_page, role_name="director")
        PageRolePermission.objects.create(page=self.board_page, role_name="treasurer")

        # Create test users
        self.member = User.objects.create_user(
            username="member", email="member@test.com", membership_status="Full Member"
        )
        self.director = User.objects.create_user(
            username="director",
            email="director@test.com",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

        self.client = Client()

    def test_public_page_access(self):
        """Test that public pages are accessible to anonymous users."""
        response = self.client.get("/cms/public/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public content")

    def test_member_page_requires_login(self):
        """Test that member-only pages redirect to login for anonymous users."""
        response = self.client.get("/cms/member/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

    def test_member_page_access_for_members(self):
        """Test that active members can access member-only pages."""
        self.client.force_login(self.member)
        response = self.client.get("/cms/member/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member content")

    def test_role_restricted_page_denies_regular_members(self):
        """Test that role-restricted pages deny access to regular members."""
        self.client.force_login(self.member)
        response = self.client.get("/cms/board/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

    def test_role_restricted_page_allows_authorized_roles(self):
        """Test that users with required roles can access restricted pages."""
        self.client.force_login(self.director)
        response = self.client.get("/cms/board/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Board content")

    def test_cms_index_filters_inaccessible_pages(self):
        """Test that CMS index only shows pages user can access."""
        # Anonymous user should only see public page
        response = self.client.get("/cms/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public Info")
        self.assertNotContains(response, "Member Info")
        self.assertNotContains(response, "Board Info")

        # Regular member should see public and member pages
        self.client.force_login(self.member)
        response = self.client.get("/cms/")
        self.assertContains(response, "Public Info")
        self.assertContains(response, "Member Info")
        self.assertNotContains(response, "Board Info")

        # Director should see all pages
        self.client.force_login(self.director)
        response = self.client.get("/cms/")
        self.assertContains(response, "Public Info")
        self.assertContains(response, "Member Info")
        self.assertContains(response, "Board Info")
