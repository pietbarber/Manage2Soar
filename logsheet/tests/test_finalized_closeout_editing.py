from datetime import date

import pytest
from django.test import TestCase
from django.urls import reverse

from logsheet.models import (
    Airfield,
    Logsheet,
    LogsheetCloseout,
    RevisionLog,
    Towplane,
    TowplaneCloseout,
    TowplaneRentalCharge,
)
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
class FinalizedCloseoutEditingTests(TestCase):
    def setUp(self):
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            allow_towplane_rental=True,
            billing_app_enabled=True,
        )
        self.member = Member.objects.create_user(
            username="closeout-editor",
            membership_status="Full Member",
            duty_officer=True,
        )
        airfield = Airfield.objects.create(identifier="KCLS", name="Closeout")
        towplane = Towplane.objects.create(
            name="Towplane",
            n_number="NCLS",
            is_active=True,
            club_owned=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=airfield,
            created_by=self.member,
            finalized=True,
            duty_officer=self.member,
        )
        self.closeout = LogsheetCloseout.objects.create(logsheet=self.logsheet)
        self.towplane_closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=towplane,
            start_tach="100.0",
            end_tach="105.0",
            fuel_added="10.0",
        )
        RevisionLog.objects.create(
            logsheet=self.logsheet,
            revised_by=self.member,
            note="Logsheet finalized",
        )
        self.client.force_login(self.member)

    def _post_data(self, **overrides):
        data = {
            "safety_issues": "Updated safety notes",
            "equipment_issues": "Updated equipment notes",
            "operations_summary": "Updated operations summary",
            "duty_officer": self.member.pk,
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": self.towplane_closeout.pk,
            "form-0-towplane": self.towplane_closeout.towplane_id,
            "form-0-start_tach": "100.0",
            "form-0-end_tach": "106.5",
            "form-0-fuel_added": "15.0",
            "form-0-notes": "Operational update",
            # Per-renter rental formset (Issue #968): one blank row.
            "rc-0-TOTAL_FORMS": "1",
            "rc-0-INITIAL_FORMS": "0",
            "rc-0-MIN_NUM_FORMS": "0",
            "rc-0-MAX_NUM_FORMS": "1000",
            "rc-0-0-member": "",
            "rc-0-0-hours": "",
        }
        data.update(overrides)
        return data

    def test_finalized_closeout_allows_operational_updates(self):
        TowplaneRentalCharge.objects.create(
            closeout=self.towplane_closeout,
            member=self.member,
            hours="2.0",
        )
        response = self.client.post(
            reverse("logsheet:edit_logsheet_closeout", args=[self.logsheet.pk]),
            self._post_data(),
        )

        assert response.status_code == 302
        self.towplane_closeout.refresh_from_db()
        assert self.towplane_closeout.end_tach == 106.5
        assert self.towplane_closeout.fuel_added == 15.0

    def test_finalized_summary_exposes_operational_edit_action(self):
        response = self.client.get(
            reverse("logsheet:view_logsheet_closeout", args=[self.logsheet.pk])
        )

        assert response.status_code == 200
        assert "Edit Operational Closeout" in response.content.decode()
        assert "Finalized - Billing Locked" in response.content.decode()

    def test_finalized_closeout_rejects_rental_charge_changes(self):
        """Post-finalization: any rental charge row with data is a billing correction."""
        response = self.client.post(
            reverse("logsheet:edit_logsheet_closeout", args=[self.logsheet.pk]),
            self._post_data(**{"rc-0-0-member": self.member.pk, "rc-0-0-hours": "2.0"}),
        )

        assert response.status_code == 200
        # No rental charge rows should have been created.
        from logsheet.models import TowplaneRentalCharge

        self.towplane_closeout.refresh_from_db()
        assert self.towplane_closeout.rental_charges.count() == 0
        assert (
            TowplaneRentalCharge.objects.filter(closeout=self.towplane_closeout).count()
            == 0
        )
