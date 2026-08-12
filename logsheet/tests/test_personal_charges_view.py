import csv
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.urls import reverse

from billing.services import post_manual_charge, post_manual_payment
from logsheet.models import Airfield, Flight, Glider, Logsheet, Towplane
from members.models import Member
from siteconfig.models import MembershipStatus, SiteConfiguration


@pytest.mark.django_db
class TestPersonalChargesView:
    def setup_method(self):
        self.config = SiteConfiguration.objects.create(
            club_name="Personal Charges Test Club",
            domain_name="personal-charges-test.example.com",
            club_abbreviation="PCT",
            billing_app_enabled=True,
        )
        MembershipStatus.objects.update_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        self.member = Member.objects.create_user(
            username="charges_member",
            password="testpass123",
            is_active=True,
            membership_status="Full Member",
        )
        self.treasurer = Member.objects.create_user(
            username="charges_treasurer",
            password="testpass123",
            is_active=True,
            treasurer=True,
            membership_status="Full Member",
        )
        self.other_member = Member.objects.create_user(
            username="charges_other",
            password="testpass123",
            is_active=True,
            membership_status="Full Member",
        )

    def post_member_activity(self):
        post_manual_charge(
            member=self.member,
            actor=self.treasurer,
            amount=Decimal("42.50"),
            effective_date=date(2026, 7, 1),
            description="Monthly flying",
            reason="Treasurer-only note",
        )
        post_manual_payment(
            member=self.member,
            actor=self.treasurer,
            amount=Decimal("10.00"),
            effective_date=date(2026, 7, 2),
            description="Payment received",
            reason="Check number 123",
        )

    def test_member_statement_uses_only_own_ledger_and_hides_internal_notes(
        self, client
    ):
        self.post_member_activity()
        post_manual_charge(
            member=self.other_member,
            actor=self.treasurer,
            amount=Decimal("99.00"),
            effective_date=date(2026, 7, 3),
            description="Other member charge",
            reason="Other secret",
        )

        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges"))

        assert response.status_code == 200
        assert response.context["ledger_balance"] == Decimal("32.50")
        assert len(response.context["statement_rows"]) == 2
        content = response.content.decode()
        assert "Monthly flying" in content
        assert "Payment received" in content
        assert "Treasurer-only note" not in content
        assert "Other member charge" not in content
        assert "Amount due" in content
        assert "Contact the treasurer" in content

    def test_member_statement_csv_uses_ledger_and_sanitizes_descriptions(self, client):
        post_manual_charge(
            member=self.member,
            actor=self.treasurer,
            amount=Decimal("12.00"),
            effective_date=date(2026, 7, 1),
            description="=formula",
            reason="Private note",
        )

        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges_csv"))

        assert response.status_code == 200
        rows = list(csv.reader(StringIO(response.content.decode())))
        assert rows[0] == ["Date", "Type", "Description", "Debit", "Credit", "Balance"]
        assert rows[1][2] == "'=formula"
        assert rows[1][5] == "12.00"
        assert "Private note" not in response.content.decode()

    def test_member_statement_remains_available_when_billing_is_disabled(self, client):
        self.post_member_activity()
        self.config.billing_app_enabled = False
        self.config.save(update_fields=["billing_app_enabled"])

        client.force_login(self.member)
        assert client.get(reverse("logsheet:personal_charges")).status_code == 200
        assert client.get(reverse("logsheet:personal_charges_csv")).status_code == 200

    def test_member_statement_uses_live_operational_charges_when_billing_is_disabled(
        self, client
    ):
        self.config.billing_app_enabled = False
        self.config.save(update_fields=["billing_app_enabled"])

        airfield = Airfield.objects.create(name="Test Airfield", identifier="KTEST")
        glider = Glider.objects.create(
            n_number="N11111",
            make="Test",
            model="Glider",
            club_owned=True,
            is_active=True,
        )
        towplane = Towplane.objects.create(
            n_number="N22222",
            make="Tow",
            model="Plane",
            club_owned=True,
            is_active=True,
        )
        logsheet = Logsheet.objects.create(
            log_date=date(2026, 7, 15),
            airfield=airfield,
            created_by=self.member,
            finalized=True,
        )
        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=self.member,
            glider=glider,
            towplane=towplane,
            launch_time="10:00:00",
            tow_cost_actual="25.00",
            rental_cost_actual="30.00",
            instruction_fee_actual="10.00",
        )
        flight.is_chargeable = True
        flight.save(
            update_fields=[
                "tow_cost_actual",
                "rental_cost_actual",
                "instruction_fee_actual",
            ]
        )

        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges"))

        assert response.status_code == 200
        assert response.context["billing_active"] is False
        assert response.context["total_owed"] == Decimal("65.00")
        assert "Total charges accrued" in response.content.decode()
        assert "No ledger entries posted." not in response.content.decode()
