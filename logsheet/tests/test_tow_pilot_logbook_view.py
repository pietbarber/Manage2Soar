import csv
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from logsheet.models import Airfield, Flight, Logsheet, Towplane, TowplaneCloseout
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
class TestTowPilotLogbookView:
    def setup_method(self):
        MembershipStatus.objects.update_or_create(
            name="Full Member", defaults={"is_active": True}
        )

        self.tow_pilot = Member.objects.create_user(
            username="tow_log_user",
            password="testpass123",
            first_name="Tow",
            last_name="Pilot",
            membership_status="Full Member",
            is_active=True,
            towpilot=True,
        )
        self.other_tow_pilot = Member.objects.create_user(
            username="other_tow_log_user",
            password="testpass123",
            first_name="Other",
            last_name="TowPilot",
            membership_status="Full Member",
            is_active=True,
            towpilot=True,
        )
        self.non_tow_member = Member.objects.create_user(
            username="non_tow_log_user",
            password="testpass123",
            first_name="Non",
            last_name="Tow",
            membership_status="Full Member",
            is_active=True,
            towpilot=False,
        )

        self.airfield = Airfield.objects.create(name="Skyline", identifier="KSS1")
        self.towplane = Towplane.objects.create(name="Tow One", n_number="N1TP")
        self.towplane_two = Towplane.objects.create(name="Tow Two", n_number="N2TP")

        today = timezone.localdate()
        self.day_one = today - timedelta(days=7)
        self.day_two = today - timedelta(days=3)

        self.logsheet_day_one = Logsheet.objects.create(
            log_date=self.day_one,
            airfield=self.airfield,
            created_by=self.tow_pilot,
            finalized=True,
        )
        self.logsheet_day_two = Logsheet.objects.create(
            log_date=self.day_two,
            airfield=self.airfield,
            created_by=self.tow_pilot,
            finalized=True,
        )

        # Two tows for current member on day one
        self.member_flight_one = Flight.objects.create(
            logsheet=self.logsheet_day_one,
            tow_pilot=self.tow_pilot,
            towplane=self.towplane,
            airfield=self.airfield,
            release_altitude=2000,
            flight_type="dual",
        )
        self.member_flight_two = Flight.objects.create(
            logsheet=self.logsheet_day_one,
            tow_pilot=self.tow_pilot,
            towplane=self.towplane,
            airfield=self.airfield,
            release_altitude=3000,
            flight_type="dual",
        )

        # One tow for current member on day two
        self.member_flight_three = Flight.objects.create(
            logsheet=self.logsheet_day_two,
            tow_pilot=self.tow_pilot,
            towplane=self.towplane_two,
            airfield=self.airfield,
            release_altitude=2500,
            flight_type="dual",
        )

        # Tow from another tow pilot should be excluded
        Flight.objects.create(
            logsheet=self.logsheet_day_two,
            tow_pilot=self.other_tow_pilot,
            towplane=self.towplane_two,
            airfield=self.airfield,
            release_altitude=1500,
            flight_type="dual",
        )

        TowplaneCloseout.objects.create(
            logsheet=self.logsheet_day_one,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
            end_tach=Decimal("101.40"),
            tach_time=Decimal("1.40"),
        )
        TowplaneCloseout.objects.create(
            logsheet=self.logsheet_day_two,
            towplane=self.towplane_two,
            start_tach=Decimal("55.00"),
            end_tach=Decimal("56.20"),
            tach_time=Decimal("1.20"),
        )

    def test_view_summarizes_rows_by_day(self, client):
        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        rows = response.context["day_rows"]
        assert len(rows) == 2
        assert {r["tow_date"] for r in rows} == {self.day_one, self.day_two}

        day_one_row = next(r for r in rows if r["tow_date"] == self.day_one)
        assert day_one_row["your_tows"] == 2

        day_two_row = next(r for r in rows if r["tow_date"] == self.day_two)
        assert day_two_row["your_tows"] == 1

    def test_day_hours_use_actual_when_solo_and_estimated_when_shared(self, client):
        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        rows = response.context["day_rows"]

        day_one_row = next(r for r in rows if r["tow_date"] == self.day_one)
        assert day_one_row["tow_hours"] == Decimal("1.40")
        assert day_one_row["hours_source"] == "Actual tach (solo tow pilot day)"

        day_two_row = next(r for r in rows if r["tow_date"] == self.day_two)
        assert day_two_row["tow_hours"] == Decimal("0.10")
        assert day_two_row["hours_source"] == "Estimated (shared tow day)"

    def test_summary_cards_and_estimates_are_correct(self, client):
        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        assert response.context["total_tows"] == 3
        assert response.context["distinct_tow_days"] == 2
        assert response.context["total_tow_hours"] == Decimal("1.50")
        assert response.context["estimated_tach_total"] == Decimal("0.30")
        assert response.context["estimated_hobbs_total"] == Decimal("0.60")

    def test_solo_day_without_closeout_uses_solo_estimate_label(self, client):
        TowplaneCloseout.objects.filter(logsheet=self.logsheet_day_one).delete()

        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        rows = response.context["day_rows"]
        day_one_row = next(r for r in rows if r["tow_date"] == self.day_one)
        assert day_one_row["tow_hours"] == Decimal("0.20")
        assert (
            day_one_row["hours_source"]
            == "Estimated (solo tow pilot day - no tach closeout)"
        )

    def test_solo_day_actual_tach_excludes_rental_hours_chargeable(self, client):
        closeout = TowplaneCloseout.objects.get(logsheet=self.logsheet_day_one)
        closeout.rental_hours_chargeable = Decimal("0.3")
        closeout.save(update_fields=["rental_hours_chargeable"])

        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        rows = response.context["day_rows"]
        day_one_row = next(r for r in rows if r["tow_date"] == self.day_one)
        assert day_one_row["tow_hours"] == Decimal("1.10")
        assert day_one_row["hours_source"] == "Actual tach (solo tow pilot day)"

    def test_guest_or_legacy_towpilot_reference_marks_day_as_shared(self, client):
        Flight.objects.create(
            logsheet=self.logsheet_day_one,
            towplane=self.towplane,
            guest_towpilot_name="Guest Tow Pilot",
            release_altitude=2000,
            flight_type="dual",
        )

        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        rows = response.context["day_rows"]
        day_one_row = next(r for r in rows if r["tow_date"] == self.day_one)
        assert day_one_row["tow_hours"] == Decimal("0.20")
        assert day_one_row["hours_source"] == "Estimated (shared tow day)"

    def test_day_grouping_uses_logsheet_airfield_when_flight_airfield_missing(
        self, client
    ):
        Flight.objects.create(
            logsheet=self.logsheet_day_one,
            tow_pilot=self.tow_pilot,
            towplane=self.towplane,
            airfield=None,
            flight_type="dual",
        )

        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        rows = response.context["day_rows"]
        assert len(rows) == 2
        day_one_row = next(r for r in rows if r["tow_date"] == self.day_one)
        assert day_one_row["airfield_identifier"] == "KSS1"
        assert day_one_row["your_tows"] == 3

    def test_distinct_tow_days_counts_unique_dates_not_logsheets(self, client):
        second_airfield_same_date = Airfield.objects.create(
            name="Skyline West",
            identifier="KSS2",
        )
        extra_logsheet_same_date = Logsheet.objects.create(
            log_date=self.day_one,
            airfield=second_airfield_same_date,
            created_by=self.tow_pilot,
            finalized=True,
        )
        Flight.objects.create(
            logsheet=extra_logsheet_same_date,
            tow_pilot=self.tow_pilot,
            towplane=self.towplane,
            airfield=second_airfield_same_date,
            flight_type="dual",
        )

        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 200
        assert response.context["distinct_tow_days"] == 2
        same_day_rows = [
            row
            for row in response.context["day_rows"]
            if row["tow_date"] == self.day_one
        ]
        assert [row["airfield_identifier"] for row in same_day_rows] == [
            "KSS1",
            "KSS2",
        ]

    def test_csv_export_contains_expected_columns_and_rows(self, client):
        client.force_login(self.tow_pilot)
        response = client.get(reverse("logsheet:tow_pilot_logbook_csv"))

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")

        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        assert rows[0] == [
            "Date",
            "Airfield",
            "Your Tows",
            "Tow Hours (Tach)",
            "Hours Source",
        ]
        assert len(rows) == 3

        csv_body = response.content.decode("utf-8")
        assert str(self.day_one) in csv_body
        assert str(self.day_two) in csv_body
        assert "KSS1" in csv_body
        assert "Actual tach (solo tow pilot day)" in csv_body
        assert "Estimated (shared tow day)" in csv_body

    def test_non_towpilot_user_is_redirected_with_message(self, client):
        client.force_login(self.non_tow_member)
        response = client.get(reverse("logsheet:tow_pilot_logbook"))

        assert response.status_code == 302
        assert response.url == reverse("home")
        messages = [m.message for m in get_messages(response.wsgi_request)]
        assert "Only tow pilots can access the tow logbook." in messages

    def test_non_towpilot_csv_is_redirected_with_message(self, client):
        client.force_login(self.non_tow_member)
        response = client.get(reverse("logsheet:tow_pilot_logbook_csv"))

        assert response.status_code == 302
        assert response.url == reverse("home")
        messages = [m.message for m in get_messages(response.wsgi_request)]
        assert "Only tow pilots can export the tow logbook." in messages
