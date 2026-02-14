"""
Tests for the add_member_charge and delete_member_charge views.

Issue #615: User-facing form for adding miscellaneous member charges
in the logsheet workflow.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from logsheet.forms import MemberChargeForm
from logsheet.models import Airfield, Logsheet, MemberCharge
from members.models import Member
from siteconfig.models import ChargeableItem, MembershipStatus, SiteConfiguration


class MemberChargeFormTestCase(TestCase):
    """Test MemberChargeForm validation and behavior."""

    def setUp(self):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        MembershipStatus.objects.get_or_create(
            name="Inactive", defaults={"is_active": False}
        )
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        self.member = Member.objects.create_user(
            username="formtest@test.com",
            email="formtest@test.com",
            first_name="Form",
            last_name="Tester",
            membership_status="Full Member",
        )

        self.tshirt = ChargeableItem.objects.create(
            name="T-Shirt Large",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=True,
        )
        self.inactive_item = ChargeableItem.objects.create(
            name="Retired Item",
            price=Decimal("10.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=False,
        )

    def test_form_valid_data(self):
        """Test form accepts valid data."""
        form = MemberChargeForm(
            data={
                "member": self.member.pk,
                "chargeable_item": self.tshirt.pk,
                "quantity": "2",
                "notes": "Test note",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_valid_without_notes(self):
        """Test form accepts data without optional notes."""
        form = MemberChargeForm(
            data={
                "member": self.member.pk,
                "chargeable_item": self.tshirt.pk,
                "quantity": "1",
                "notes": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_requires_member(self):
        """Test form requires member selection."""
        form = MemberChargeForm(
            data={
                "member": "",
                "chargeable_item": self.tshirt.pk,
                "quantity": "1",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("member", form.errors)

    def test_form_requires_chargeable_item(self):
        """Test form requires item selection."""
        form = MemberChargeForm(
            data={
                "member": self.member.pk,
                "chargeable_item": "",
                "quantity": "1",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("chargeable_item", form.errors)

    def test_form_excludes_inactive_items(self):
        """Test that inactive items don't appear in the dropdown."""
        form = MemberChargeForm()
        item_queryset = form.fields["chargeable_item"].queryset
        self.assertIn(self.tshirt, item_queryset)
        self.assertNotIn(self.inactive_item, item_queryset)

    def test_form_groups_members_by_status(self):
        """Test that member choices are grouped by active/inactive."""
        inactive_member = Member.objects.create_user(
            username="inactive@test.com",
            email="inactive@test.com",
            first_name="Inactive",
            last_name="Person",
            membership_status="Inactive",
        )
        form = MemberChargeForm()
        choices = form.fields["member"].choices
        # Should have blank option + at least one group
        self.assertEqual(choices[0], ("", "— Select member —"))
        # Active members group should exist
        active_group = [
            c for c in choices if isinstance(c, tuple) and c[0] == "Active Members"
        ]
        self.assertTrue(len(active_group) > 0)

    def test_form_quantity_minimum(self):
        """Test form rejects zero or negative quantity."""
        form = MemberChargeForm(
            data={
                "member": self.member.pk,
                "chargeable_item": self.tshirt.pk,
                "quantity": "0",
            }
        )
        self.assertFalse(form.is_valid())


class AddMemberChargeViewTestCase(TestCase):
    """Test the add_member_charge view."""

    def setUp(self):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        self.duty_officer = Member.objects.create_user(
            username="do@test.com",
            email="do@test.com",
            password="testpass123",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
        )
        self.duty_officer.duty_officer = True
        self.duty_officer.save()

        self.member = Member.objects.create_user(
            username="pilot@test.com",
            email="pilot@test.com",
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        self.airfield = Airfield.objects.create(
            name="Test Airfield",
            identifier="TEST",
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.duty_officer,
        )

        self.tshirt = ChargeableItem.objects.create(
            name="T-Shirt Large",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=True,
        )
        self.retrieve = ChargeableItem.objects.create(
            name="Aerotow Retrieve",
            price=Decimal("120.00"),
            unit=ChargeableItem.UnitType.HOUR,
            allows_decimal_quantity=True,
            is_active=True,
        )

    def test_get_add_charge_form(self):
        """Test GET request renders the add charge form."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "logsheet/add_member_charge.html")
        self.assertIsInstance(response.context["form"], MemberChargeForm)
        self.assertEqual(response.context["logsheet"], self.logsheet)

    def test_post_creates_charge(self):
        """Test POST request creates a charge and redirects."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        data = {
            "member": self.member.pk,
            "chargeable_item": self.tshirt.pk,
            "quantity": "2",
            "notes": "Two large t-shirts",
        }
        response = self.client.post(url, data)

        # Should redirect to finances view
        self.assertRedirects(
            response,
            reverse(
                "logsheet:manage_logsheet_finances",
                kwargs={"pk": self.logsheet.pk},
            ),
        )

        # Verify charge was created
        charge = MemberCharge.objects.get(logsheet=self.logsheet, member=self.member)
        self.assertEqual(charge.chargeable_item, self.tshirt)
        self.assertEqual(charge.quantity, Decimal("2"))
        self.assertEqual(charge.unit_price, Decimal("25.00"))
        self.assertEqual(charge.total_price, Decimal("50.00"))
        self.assertEqual(charge.entered_by, self.duty_officer)
        self.assertEqual(charge.date, self.logsheet.log_date)
        self.assertEqual(charge.notes, "Two large t-shirts")

    def test_post_decimal_quantity(self):
        """Test POST with decimal quantity for hourly items."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        data = {
            "member": self.member.pk,
            "chargeable_item": self.retrieve.pk,
            "quantity": "1.8",
            "notes": "Retrieve from outlanding",
        }
        response = self.client.post(url, data)
        self.assertRedirects(
            response,
            reverse(
                "logsheet:manage_logsheet_finances",
                kwargs={"pk": self.logsheet.pk},
            ),
        )

        charge = MemberCharge.objects.get(logsheet=self.logsheet, member=self.member)
        self.assertEqual(charge.quantity, Decimal("1.8"))
        self.assertEqual(charge.total_price, Decimal("216.00"))

    def test_cannot_add_charge_to_finalized_logsheet(self):
        """Test that adding charges to a finalized logsheet is prevented."""
        self.logsheet.finalized = True
        self.logsheet.save()

        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )

        # GET should redirect
        response = self.client.get(url)
        self.assertRedirects(
            response,
            reverse(
                "logsheet:manage_logsheet_finances",
                kwargs={"pk": self.logsheet.pk},
            ),
        )

        # POST should also redirect without creating a charge
        data = {
            "member": self.member.pk,
            "chargeable_item": self.tshirt.pk,
            "quantity": "1",
        }
        response = self.client.post(url, data)
        self.assertRedirects(
            response,
            reverse(
                "logsheet:manage_logsheet_finances",
                kwargs={"pk": self.logsheet.pk},
            ),
        )
        self.assertEqual(MemberCharge.objects.count(), 0)

    def test_invalid_form_re_renders(self):
        """Test that invalid POST re-renders the form with errors."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        data = {
            "member": "",
            "chargeable_item": self.tshirt.pk,
            "quantity": "1",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())

    def test_unauthenticated_redirects_to_login(self):
        """Test that unauthenticated users are redirected to login."""
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)

    def test_charge_auto_links_to_logsheet(self):
        """Test that the charge is automatically linked to the logsheet."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        data = {
            "member": self.member.pk,
            "chargeable_item": self.tshirt.pk,
            "quantity": "1",
        }
        self.client.post(url, data)

        charge = MemberCharge.objects.first()
        self.assertEqual(charge.logsheet, self.logsheet)

    def test_charge_date_matches_logsheet_date(self):
        """Test that the charge date is set to the logsheet date."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        data = {
            "member": self.member.pk,
            "chargeable_item": self.tshirt.pk,
            "quantity": "1",
        }
        self.client.post(url, data)

        charge = MemberCharge.objects.first()
        self.assertEqual(charge.date, self.logsheet.log_date)

    def test_success_message_displayed(self):
        """Test that a success message is set after adding a charge."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:add_member_charge", kwargs={"logsheet_pk": self.logsheet.pk}
        )
        data = {
            "member": self.member.pk,
            "chargeable_item": self.tshirt.pk,
            "quantity": "1",
        }
        response = self.client.post(url, data, follow=True)
        messages = list(response.context["messages"])
        self.assertTrue(
            any("Added" in str(m) and "T-Shirt Large" in str(m) for m in messages)
        )


class DeleteMemberChargeViewTestCase(TestCase):
    """Test the delete_member_charge view."""

    def setUp(self):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        self.duty_officer = Member.objects.create_user(
            username="do@test.com",
            email="do@test.com",
            password="testpass123",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
        )

        self.member = Member.objects.create_user(
            username="pilot@test.com",
            email="pilot@test.com",
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        self.airfield = Airfield.objects.create(
            name="Test Airfield",
            identifier="TEST",
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.duty_officer,
        )

        self.tshirt = ChargeableItem.objects.create(
            name="T-Shirt Large",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=True,
        )

        self.charge = MemberCharge.objects.create(
            member=self.member,
            chargeable_item=self.tshirt,
            quantity=Decimal("1"),
            logsheet=self.logsheet,
            entered_by=self.duty_officer,
        )

    def test_delete_charge(self):
        """Test deleting a charge removes it and redirects."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:delete_member_charge",
            kwargs={
                "logsheet_pk": self.logsheet.pk,
                "charge_pk": self.charge.pk,
            },
        )
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse(
                "logsheet:manage_logsheet_finances",
                kwargs={"pk": self.logsheet.pk},
            ),
        )
        self.assertEqual(MemberCharge.objects.count(), 0)

    def test_delete_requires_post(self):
        """Test GET request is not allowed for delete."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:delete_member_charge",
            kwargs={
                "logsheet_pk": self.logsheet.pk,
                "charge_pk": self.charge.pk,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed
        self.assertEqual(MemberCharge.objects.count(), 1)

    def test_cannot_delete_from_finalized_logsheet(self):
        """Test that deleting charges from a finalized logsheet is prevented."""
        self.logsheet.finalized = True
        self.logsheet.save()

        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:delete_member_charge",
            kwargs={
                "logsheet_pk": self.logsheet.pk,
                "charge_pk": self.charge.pk,
            },
        )
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse(
                "logsheet:manage_logsheet_finances",
                kwargs={"pk": self.logsheet.pk},
            ),
        )
        # Charge should still exist
        self.assertEqual(MemberCharge.objects.count(), 1)

    def test_delete_success_message(self):
        """Test that a success message is displayed after deletion."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:delete_member_charge",
            kwargs={
                "logsheet_pk": self.logsheet.pk,
                "charge_pk": self.charge.pk,
            },
        )
        response = self.client.post(url, follow=True)
        messages = list(response.context["messages"])
        self.assertTrue(
            any("Deleted" in str(m) and "T-Shirt Large" in str(m) for m in messages)
        )

    def test_delete_wrong_logsheet_returns_404(self):
        """Test that deleting a charge from the wrong logsheet returns 404."""
        other_airfield = Airfield.objects.create(
            name="Other Airfield",
            identifier="OTHR",
        )
        other_logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=other_airfield,
            created_by=self.duty_officer,
        )
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:delete_member_charge",
            kwargs={
                "logsheet_pk": other_logsheet.pk,
                "charge_pk": self.charge.pk,
            },
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(MemberCharge.objects.count(), 1)


class FinancesViewChargeDisplayTestCase(TestCase):
    """Test that charges appear correctly in the finances view."""

    def setUp(self):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
        )

        self.duty_officer = Member.objects.create_user(
            username="do@test.com",
            email="do@test.com",
            password="testpass123",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
        )

        self.member = Member.objects.create_user(
            username="pilot@test.com",
            email="pilot@test.com",
            first_name="Test",
            last_name="Pilot",
            membership_status="Full Member",
        )

        self.airfield = Airfield.objects.create(
            name="Test Airfield",
            identifier="TEST",
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.duty_officer,
        )

        self.tshirt = ChargeableItem.objects.create(
            name="T-Shirt Large",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=True,
        )

    def test_add_charge_button_shown_on_non_finalized(self):
        """Test that 'Add Charge' button appears on non-finalized logsheet."""
        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:manage_logsheet_finances",
            kwargs={"pk": self.logsheet.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        add_url = reverse(
            "logsheet:add_member_charge",
            kwargs={"logsheet_pk": self.logsheet.pk},
        )
        self.assertContains(response, add_url)
        self.assertContains(response, "Add Charge")

    def test_add_charge_button_hidden_on_finalized(self):
        """Test that 'Add Charge' button is hidden on finalized logsheet."""
        self.logsheet.finalized = True
        self.logsheet.save()

        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:manage_logsheet_finances",
            kwargs={"pk": self.logsheet.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        add_url = reverse(
            "logsheet:add_member_charge",
            kwargs={"logsheet_pk": self.logsheet.pk},
        )
        self.assertNotContains(response, add_url)

    def test_charges_displayed_in_finances_view(self):
        """Test that existing charges appear in the finances view."""
        MemberCharge.objects.create(
            member=self.member,
            chargeable_item=self.tshirt,
            quantity=Decimal("2"),
            logsheet=self.logsheet,
            entered_by=self.duty_officer,
        )

        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:manage_logsheet_finances",
            kwargs={"pk": self.logsheet.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "T-Shirt Large")
        self.assertContains(response, "$50.00")
        self.assertContains(response, "Miscellaneous Charges")

    def test_delete_button_shown_for_non_finalized(self):
        """Test that delete buttons appear for charges on non-finalized logsheet."""
        charge = MemberCharge.objects.create(
            member=self.member,
            chargeable_item=self.tshirt,
            quantity=Decimal("1"),
            logsheet=self.logsheet,
            entered_by=self.duty_officer,
        )

        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:manage_logsheet_finances",
            kwargs={"pk": self.logsheet.pk},
        )
        response = self.client.get(url)
        delete_url = reverse(
            "logsheet:delete_member_charge",
            kwargs={
                "logsheet_pk": self.logsheet.pk,
                "charge_pk": charge.pk,
            },
        )
        self.assertContains(response, delete_url)

    def test_delete_button_hidden_for_finalized(self):
        """Test that delete buttons are hidden for finalized logsheet."""
        charge = MemberCharge.objects.create(
            member=self.member,
            chargeable_item=self.tshirt,
            quantity=Decimal("1"),
            logsheet=self.logsheet,
            entered_by=self.duty_officer,
        )

        self.logsheet.finalized = True
        self.logsheet.save()

        self.client.login(username="do@test.com", password="testpass123")
        url = reverse(
            "logsheet:manage_logsheet_finances",
            kwargs={"pk": self.logsheet.pk},
        )
        response = self.client.get(url)
        delete_url = reverse(
            "logsheet:delete_member_charge",
            kwargs={
                "logsheet_pk": self.logsheet.pk,
                "charge_pk": charge.pk,
            },
        )
        self.assertNotContains(response, delete_url)
