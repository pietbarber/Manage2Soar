
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.core import mail
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

from .models import VisitorContact
from .forms import VisitorContactForm
from .admin import VisitorContactAdmin


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
            ip_address="192.168.1.100"
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
            message="How do I join?"
        )

        expected_str = f"Jane Smith - Club membership inquiry ({contact.submitted_at.strftime('%Y-%m-%d')})"
        self.assertEqual(str(contact), expected_str)

    def test_visitor_contact_ordering(self):
        """Test that contacts are ordered by submission date (newest first)."""
        contact1 = VisitorContact.objects.create(
            name="First Contact",
            email="first@example.com",
            subject="First subject",
            message="First message"
        )
        contact2 = VisitorContact.objects.create(
            name="Second Contact",
            email="second@example.com",
            subject="Second subject",
            message="Second message"
        )

        contacts = list(VisitorContact.objects.all())
        self.assertEqual(contacts[0], contact2)  # Newest first
        self.assertEqual(contacts[1], contact1)


class VisitorContactFormTests(TestCase):
    """Test the VisitorContactForm validation and functionality."""

    def test_valid_form(self):
        """Test that a valid form passes validation."""
        form_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'phone': '555-123-4567',
            'subject': 'Interested in lessons',
            'message': 'I would like to learn more about your gliding programs.'
        }
        form = VisitorContactForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_required_fields(self):
        """Test that required fields are enforced."""
        form = VisitorContactForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('email', form.errors)
        self.assertIn('subject', form.errors)
        self.assertIn('message', form.errors)

    def test_phone_optional(self):
        """Test that phone field is optional."""
        form_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'subject': 'Test subject',
            'message': 'This is a test message with sufficient length.'
        }
        form = VisitorContactForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_email_validation(self):
        """Test email validation including spam domain blocking."""
        # Test invalid email format
        form_data = {
            'name': 'John Doe',
            'email': 'not-an-email',
            'subject': 'Test',
            'message': 'Test message with enough length.'
        }
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

        # Test spam domain blocking
        form_data['email'] = 'spammer@tempmail.org'
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_message_length_validation(self):
        """Test message minimum length validation."""
        form_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'subject': 'Test',
            'message': 'Short'  # Too short
        }
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_spam_keyword_detection(self):
        """Test that spam keywords are detected in messages."""
        form_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'subject': 'Test',
            'message': 'Click here to win money from casino lottery!'
        }
        form = VisitorContactForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)


class VisitorContactViewTests(TestCase):
    """Test the visitor contact views."""

    def setUp(self):
        self.client = Client()

    def test_contact_page_get(self):
        """Test that the contact page loads successfully."""
        response = self.client.get(reverse('cms:contact'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Contact Skyline Soaring Club')
        self.assertContains(response, 'form')

    def test_contact_page_no_auth_required(self):
        """Test that the contact page doesn't require authentication."""
        # Ensure no user is logged in
        response = self.client.get(reverse('cms:contact'))
        self.assertEqual(response.status_code, 200)

    @patch('django.core.mail.send_mail')
    def test_contact_form_submission_success(self, mock_send_mail):
        """Test successful contact form submission."""
        # Create a member manager to receive the email
        member_manager = User.objects.create_user(
            username='manager',
            email='manager@skylinesoaring.org',
            member_manager=True,
            is_active=True
        )

        form_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'phone': '555-123-4567',
            'subject': 'Interested in lessons',
            'message': 'I would like to learn more about your gliding programs.'
        }

        response = self.client.post(reverse('cms:contact'), data=form_data)

        # Should redirect to success page
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('cms:contact_success'))

        # Check that contact was created
        self.assertEqual(VisitorContact.objects.count(), 1)
        contact = VisitorContact.objects.get(email='john@example.com')
        self.assertEqual(contact.name, 'John Doe')
        self.assertEqual(contact.email, 'john@example.com')

        # Check that email was sent
        mock_send_mail.assert_called_once()

    def test_contact_form_submission_invalid(self):
        """Test contact form submission with invalid data."""
        form_data = {
            'name': '',  # Required field missing
            'email': 'invalid-email',
            'subject': '',
            'message': 'Short'
        }

        response = self.client.post(reverse('cms:contact'), data=form_data)

        # Should stay on the same page with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required')

        # No contact should be created
        self.assertEqual(VisitorContact.objects.count(), 0)

    def test_contact_success_page(self):
        """Test that the contact success page loads."""
        response = self.client.get(reverse('cms:contact_success'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Message Sent Successfully')

    @patch('cms.views._get_client_ip')
    def test_ip_address_capture(self, mock_get_ip):
        """Test that IP address is captured during form submission."""
        mock_get_ip.return_value = '192.168.1.100'

        form_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'subject': 'Test subject',
            'message': 'This is a test message with sufficient length.'
        }

        self.client.post(reverse('cms:contact'), data=form_data)

        contact = VisitorContact.objects.get(email='john@example.com')
        self.assertEqual(contact.ip_address, '192.168.1.100')
        mock_get_ip.assert_called_once()


class VisitorContactEmailTests(TestCase):
    """Test email notification functionality."""

    def setUp(self):
        # Create member managers
        self.member_manager = User.objects.create_user(
            username='manager1',
            email='manager1@skylinesoaring.org',
            first_name='Manager',
            last_name='One',
            member_manager=True,
            is_active=True
        )

        self.webmaster = User.objects.create_user(
            username='webmaster',
            email='webmaster@skylinesoaring.org',
            first_name='Web',
            last_name='Master',
            webmaster=True,
            is_active=True
        )

    def test_email_sent_to_member_managers(self):
        """Test that emails are sent to member managers."""
        contact = VisitorContact.objects.create(
            name="John Doe",
            email="john@example.com",
            subject="Test inquiry",
            message="This is a test message."
        )

        # Submit form to trigger email
        form_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'subject': 'Test inquiry',
            'message': 'This is a test message with sufficient length.'
        }

        self.client.post(reverse('cms:contact'), data=form_data)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        self.assertIn('New Visitor Contact', email.subject)
        self.assertIn('john@example.com', email.body)
        self.assertIn('Test inquiry', email.body)
        self.assertIn(self.member_manager.email, email.to)

    def test_fallback_to_webmasters(self):
        """Test fallback to webmasters when no member managers exist."""
        # Remove member manager privilege
        self.member_manager.member_manager = False
        self.member_manager.save()

        form_data = {
            'name': 'Jane Doe',
            'email': 'jane@example.com',
            'subject': 'Another test',
            'message': 'This is another test message with sufficient length.'
        }

        self.client.post(reverse('cms:contact'), data=form_data)

        # Should send to webmaster instead
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn(self.webmaster.email, email.to)


class VisitorContactAdminTests(TestCase):
    """Test the admin interface for visitor contacts."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@skylinesoaring.org',
            is_staff=True,
            is_superuser=True
        )

        self.contact = VisitorContact.objects.create(
            name="John Doe",
            email="john@example.com",
            subject="Test inquiry",
            message="This is a test message.",
            ip_address="192.168.1.100"
        )

    def test_admin_registration(self):
        """Test that VisitorContact is registered in admin."""
        from django.contrib import admin
        self.assertIn(VisitorContact, admin.site._registry)

    def test_admin_list_display(self):
        """Test admin list display fields."""
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())

        expected_fields = ['submitted_at', 'name', 'email', 'subject',
                           'status', 'handled_by_name', 'ip_display']
        self.assertEqual(list(admin_class.list_display), expected_fields)

    def test_admin_readonly_fields(self):
        """Test that submission data is readonly in admin."""
        factory = RequestFactory()
        request = factory.get('/admin/cms/visitorcontact/')
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())
        readonly_fields = admin_class.get_readonly_fields(request, self.contact)

        # Contact details should be readonly when editing
        self.assertIn('name', readonly_fields)
        self.assertIn('email', readonly_fields)
        self.assertIn('subject', readonly_fields)
        self.assertIn('message', readonly_fields)

    def test_admin_no_add_permission(self):
        """Test that contacts cannot be manually created in admin."""
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())
        request = MagicMock()
        request.user = self.admin_user

        self.assertFalse(admin_class.has_add_permission(request))

    def test_admin_bulk_actions(self):
        """Test admin bulk actions for status updates."""
        admin_class = VisitorContactAdmin(VisitorContact, AdminSite())

        expected_actions = ['mark_read', 'mark_responded', 'mark_closed']
        action_names = []
        if admin_class.actions:
            for action in admin_class.actions:
                if hasattr(action, '__name__'):
                    action_names.append(action.__name__)
                else:
                    action_names.append(str(action))

        for expected_action in expected_actions:
            self.assertIn(expected_action, action_names)


class VisitorContactIntegrationTests(TestCase):
    """Integration tests for the complete visitor contact workflow."""

    def setUp(self):
        self.member_manager = User.objects.create_user(
            username='manager',
            email='manager@skylinesoaring.org',
            first_name='Member',
            last_name='Manager',
            member_manager=True,
            is_active=True
        )

    def test_complete_contact_workflow(self):
        """Test the complete workflow from form submission to admin management."""
        # 1. Visitor submits contact form
        form_data = {
            'name': 'Alice Johnson',
            'email': 'alice@example.com',
            'phone': '555-987-6543',
            'subject': 'Trial flight inquiry',
            'message': 'I would like to schedule a trial flight to experience gliding.'
        }

        response = self.client.post(reverse('cms:contact'), data=form_data)

        # 2. Verify successful submission
        self.assertEqual(response.status_code, 302)
        self.assertEqual(VisitorContact.objects.count(), 1)

        # 3. Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('alice@example.com', email.body)
        self.assertIn('Trial flight inquiry', email.subject)

        # 4. Verify contact can be managed in admin
        contact = VisitorContact.objects.get(email='alice@example.com')
        self.assertEqual(contact.name, 'Alice Johnson')
        self.assertEqual(contact.status, 'new')

        # 5. Simulate admin updating status
        contact.status = 'responded'
        contact.handled_by = self.member_manager
        contact.admin_notes = 'Responded via email with trial flight options'
        contact.save()

        # 6. Verify updates
        updated_contact = VisitorContact.objects.get(email='alice@example.com')
        self.assertEqual(updated_contact.status, 'responded')
        self.assertEqual(updated_contact.handled_by, self.member_manager)
        self.assertIsNotNone(updated_contact.admin_notes)
        self.assertIn('trial flight options', str(updated_contact.admin_notes))

    def test_url_accessibility(self):
        """Test that contact URLs are accessible at expected paths."""
        # Test /contact/ (through CMS app)
        response = self.client.get('/contact/')
        self.assertEqual(response.status_code, 200)

        # Test success page
        response = self.client.get('/contact/success/')
        self.assertEqual(response.status_code, 200)
