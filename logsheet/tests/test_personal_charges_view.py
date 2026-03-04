from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from logsheet.models import Airfield, Flight, Glider, Logsheet, MemberCharge
from members.models import Member
from siteconfig.models import ChargeableItem, MembershipStatus


@pytest.mark.django_db
class TestPersonalChargesView:
    def setup_method(self):
        MembershipStatus.objects.update_or_create(
            name="Full Member", defaults={"is_active": True}
        )

        self.member = Member.objects.create_user(
            username="charges_member",
            password="testpass123",
            first_name="Charges",
            last_name="Member",
            membership_status="Full Member",
            is_active=True,
        )
        self.other_member = Member.objects.create_user(
            username="charges_other",
            password="testpass123",
            first_name="Other",
            last_name="Member",
            membership_status="Full Member",
            is_active=True,
        )

        self.airfield = Airfield.objects.create(name="Test Field", identifier="KTS1")
        self.glider = Glider.objects.create(
            n_number="N111AA",
            make="Schleicher",
            model="ASK-21",
            club_owned=True,
            is_active=True,
        )

        today = timezone.localdate()
        self.recent_date = today - timedelta(days=5)
        self.second_recent_date = today - timedelta(days=15)
        self.old_date = today - timedelta(days=400)

        self.recent_logsheet = Logsheet.objects.create(
            log_date=self.recent_date,
            airfield=self.airfield,
            created_by=self.member,
            finalized=True,
        )
        self.second_recent_logsheet = Logsheet.objects.create(
            log_date=self.second_recent_date,
            airfield=self.airfield,
            created_by=self.member,
            finalized=True,
        )
        self.old_logsheet = Logsheet.objects.create(
            log_date=self.old_date,
            airfield=self.airfield,
            created_by=self.member,
            finalized=True,
        )

        self.flight_direct = Flight.objects.create(
            logsheet=self.recent_logsheet,
            pilot=self.member,
            glider=self.glider,
            flight_type="solo",
            tow_cost_actual=Decimal("45.00"),
            rental_cost_actual=Decimal("8.80"),
        )
        # member pays tow only via split
        self.flight_split_tow = Flight.objects.create(
            logsheet=self.second_recent_logsheet,
            pilot=self.other_member,
            split_with=self.member,
            split_type="tow",
            glider=self.glider,
            flight_type="dual",
            tow_cost_actual=Decimal("30.00"),
            rental_cost_actual=Decimal("12.50"),
        )
        # member pays nothing on this split and it should be excluded
        Flight.objects.create(
            logsheet=self.recent_logsheet,
            pilot=self.member,
            split_with=self.other_member,
            split_type="full",
            glider=self.glider,
            flight_type="dual",
            tow_cost_actual=Decimal("35.00"),
            rental_cost_actual=Decimal("10.00"),
        )
        # old flight outside 365-day window
        Flight.objects.create(
            logsheet=self.old_logsheet,
            pilot=self.member,
            glider=self.glider,
            flight_type="solo",
            tow_cost_actual=Decimal("100.00"),
            rental_cost_actual=Decimal("50.00"),
        )

        tshirt = ChargeableItem.objects.create(
            name="T-Shirt",
            price=Decimal("25.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=True,
        )
        MemberCharge.objects.create(
            member=self.member,
            chargeable_item=tshirt,
            quantity=Decimal("2.00"),
            unit_price=Decimal("25.00"),
            date=self.recent_date,
            notes="Two shirts",
            entered_by=self.member,
        )
        MemberCharge.objects.create(
            member=self.member,
            chargeable_item=tshirt,
            quantity=Decimal("1.00"),
            unit_price=Decimal("25.00"),
            date=self.old_date,
            notes="Old charge",
            entered_by=self.member,
        )

    def test_personal_charges_view_filters_and_orders_recent_rows(self, client):
        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges"))

        assert response.status_code == 200
        flight_rows = response.context["flight_rows"]
        assert len(flight_rows) == 2

        assert flight_rows[0]["flight_date"] > flight_rows[1]["flight_date"]

        direct_row = next(
            r for r in flight_rows if r["flight"].pk == self.flight_direct.pk
        )
        assert direct_row["tow_cost"] == Decimal("45.00")
        assert direct_row["rental_cost"] == Decimal("8.80")
        assert direct_row["total_cost"] == Decimal("53.80")

        split_row = next(
            r for r in flight_rows if r["flight"].pk == self.flight_split_tow.pk
        )
        assert split_row["tow_cost"] == Decimal("30.00")
        assert split_row["rental_cost"] == Decimal("0.00")
        assert split_row["total_cost"] == Decimal("30.00")

        misc_charges = response.context["misc_charges"]
        assert len(misc_charges) == 1
        assert misc_charges[0].notes == "Two shirts"

    def test_personal_charges_csv_exports_flights_and_misc(self, client):
        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges_csv"))

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert "attachment; filename=" in response["Content-Disposition"]

        content = response.content.decode("utf-8")
        assert "Charge Type" in content
        assert "Flight" in content
        assert "Misc" in content
        assert "T-Shirt" in content
        assert str(self.old_date) not in content
