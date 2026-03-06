import csv
import re
from datetime import time, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.urls import reverse
from django.utils import timezone

from logsheet.models import (
    Airfield,
    Flight,
    Glider,
    Logsheet,
    MemberCharge,
    Towplane,
    TowplaneChargeScheme,
    TowplaneChargeTier,
)
from logsheet.views import _get_personal_charge_data
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

        content = response.content.decode("utf-8")
        sortable_tables = re.findall(
            r"<table[^>]*class=\"[^\"]*\bsort\b[^\"]*\"",
            content,
            flags=re.IGNORECASE,
        )
        assert len(sortable_tables) == 2

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

    def test_personal_charges_csv_sanitizes_formula_like_cells(self, client):
        bad_glider = Glider.objects.create(
            n_number="=2+2",
            make="Test",
            model="Glider",
            club_owned=True,
            is_active=True,
        )
        bad_item = ChargeableItem.objects.create(
            name="@malicious-item",
            price=Decimal("5.00"),
            unit=ChargeableItem.UnitType.EACH,
            is_active=True,
        )

        Flight.objects.create(
            logsheet=self.recent_logsheet,
            pilot=self.member,
            glider=bad_glider,
            flight_type="solo",
            tow_cost_actual=Decimal("1.00"),
            rental_cost_actual=Decimal("2.00"),
        )
        MemberCharge.objects.create(
            member=self.member,
            chargeable_item=bad_item,
            quantity=Decimal("1.00"),
            unit_price=Decimal("5.00"),
            date=self.recent_date,
            notes=" +SUM(1,2)",
            entered_by=self.member,
        )

        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges_csv"))
        assert response.status_code == 200

        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        data_rows = rows[1:]

        sanitized_glider_values = [r[2] for r in data_rows if r[1] == "Flight"]
        sanitized_item_values = [r[3] for r in data_rows if r[1] == "Misc"]
        sanitized_notes_values = [r[8] for r in data_rows if r[1] == "Misc"]

        assert any(value.startswith("'=2+2") for value in sanitized_glider_values)
        assert "'@malicious-item" in sanitized_item_values
        assert "' +SUM(1,2)" in sanitized_notes_values

    def test_personal_charges_view_covers_even_rental_and_full_splits(self, client):
        flight_even = Flight.objects.create(
            logsheet=self.recent_logsheet,
            pilot=self.other_member,
            split_with=self.member,
            split_type="even",
            glider=self.glider,
            flight_type="dual",
            tow_cost_actual=Decimal("10.00"),
            rental_cost_actual=Decimal("5.00"),
        )
        flight_rental = Flight.objects.create(
            logsheet=self.recent_logsheet,
            pilot=self.other_member,
            split_with=self.member,
            split_type="rental",
            glider=self.glider,
            flight_type="dual",
            tow_cost_actual=Decimal("9.00"),
            rental_cost_actual=Decimal("4.00"),
        )
        flight_full = Flight.objects.create(
            logsheet=self.recent_logsheet,
            pilot=self.other_member,
            split_with=self.member,
            split_type="full",
            glider=self.glider,
            flight_type="dual",
            tow_cost_actual=Decimal("3.00"),
            rental_cost_actual=Decimal("2.00"),
        )

        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges"))
        assert response.status_code == 200

        rows_by_flight_id = {
            row["flight"].pk: row for row in response.context["flight_rows"]
        }

        even_row = rows_by_flight_id[flight_even.pk]
        assert even_row["tow_cost"] == Decimal("5.00")
        assert even_row["rental_cost"] == Decimal("2.50")
        assert even_row["total_cost"] == Decimal("7.50")

        rental_row = rows_by_flight_id[flight_rental.pk]
        assert rental_row["tow_cost"] == Decimal("0.00")
        assert rental_row["rental_cost"] == Decimal("4.00")
        assert rental_row["total_cost"] == Decimal("4.00")

        full_row = rows_by_flight_id[flight_full.pk]
        assert full_row["tow_cost"] == Decimal("3.00")
        assert full_row["rental_cost"] == Decimal("2.00")
        assert full_row["total_cost"] == Decimal("5.00")

    def test_non_finalized_flight_path_uses_calculated_and_half_up_rounding(
        self, client
    ):
        self.glider.rental_rate = Decimal("11.11")
        self.glider.save(update_fields=["rental_rate"])

        non_finalized_logsheet = Logsheet.objects.create(
            log_date=self.recent_date - timedelta(days=1),
            airfield=self.airfield,
            created_by=self.member,
            finalized=False,
        )
        flight_non_finalized = Flight.objects.create(
            logsheet=non_finalized_logsheet,
            pilot=self.other_member,
            split_with=self.member,
            split_type="even",
            glider=self.glider,
            flight_type="dual",
            launch_time=time(10, 0),
            landing_time=time(11, 0),
            tow_cost_actual=Decimal("0.00"),
            rental_cost_actual=Decimal("0.00"),
        )

        client.force_login(self.member)
        response = client.get(reverse("logsheet:personal_charges"))
        assert response.status_code == 200

        non_finalized_row = next(
            row
            for row in response.context["flight_rows"]
            if row["flight"].pk == flight_non_finalized.pk
        )
        assert non_finalized_row["tow_cost"] == Decimal("0.00")
        assert non_finalized_row["rental_cost"] == Decimal("5.56")
        assert non_finalized_row["total_cost"] == Decimal("5.56")

    def test_personal_charge_data_avoids_n_plus_one_for_charge_tiers(
        self, django_assert_num_queries
    ):
        towplane = Towplane.objects.create(
            name="Tow 1",
            n_number="N200TP",
            is_active=True,
        )
        scheme = TowplaneChargeScheme.objects.create(
            towplane=towplane,
            name="Standard",
            is_active=True,
            hookup_fee=Decimal("0.00"),
        )
        TowplaneChargeTier.objects.create(
            charge_scheme=scheme,
            altitude_start=0,
            altitude_end=None,
            rate_type="per_1000ft",
            rate_amount=Decimal("20.00"),
            is_active=True,
        )

        non_finalized_logsheet = Logsheet.objects.create(
            log_date=self.recent_date - timedelta(days=1),
            airfield=self.airfield,
            created_by=self.member,
            finalized=False,
        )

        for altitude in [1000, 1200, 1400, 1600, 1800]:
            Flight.objects.create(
                logsheet=non_finalized_logsheet,
                pilot=self.other_member,
                split_with=self.member,
                split_type="tow",
                glider=self.glider,
                towplane=towplane,
                flight_type="dual",
                release_altitude=altitude,
                tow_cost_actual=Decimal("0.00"),
                rental_cost_actual=Decimal("0.00"),
            )

        start_date = timezone.localdate() - timedelta(days=365)
        with django_assert_num_queries(4):
            flight_rows, misc_charges = _get_personal_charge_data(
                self.member, start_date
            )
            assert len(flight_rows) >= 5
            assert len(misc_charges) >= 1
