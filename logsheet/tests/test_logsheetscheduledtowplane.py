"""Tests for LogsheetTowplane (Issue #1048): day-level towplane roster.

Covers:
- Model: unique constraint, get_last_end_tach helper
- Form: LogsheetTowplaneForm filtering (no virtual towplanes, towpilot role)
- Views: create_logsheet saves the roster; add_towplane_closeout seeds a
  roster row; edit_logsheet_closeout renders the roster formset.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from logsheet.models import (
    Airfield,
    Logsheet,
    LogsheetTowplane,
    Towplane,
    TowplaneCloseout,
)
from members.models import Member
from siteconfig.models import SiteConfiguration


def _make_member(username, **kwargs):
    defaults = dict(
        username=username,
        password="testpass123",
        first_name="Test",
        last_name=username.title(),
        membership_status="Full Member",
        email=f"{username}@example.com",
    )
    defaults.update(kwargs)
    return Member.objects.create_user(**defaults)


def _make_logsheet(airfield, user, when=None):
    return Logsheet.objects.create(
        log_date=when or date.today(),
        airfield=airfield,
        created_by=user,
    )


class LogsheetTowplaneModelTests(TestCase):
    def setUp(self):
        self.member = _make_member("roster_pilot", towpilot=True)
        self.towplane = Towplane.objects.create(
            name="Husky", n_number="N6085S", is_active=True, club_owned=True
        )
        self.airfield = Airfield.objects.create(
            name="Test Field", identifier="TST", is_active=True
        )
        self.logsheet = _make_logsheet(self.airfield, self.member)

    def test_str(self):
        row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet, towplane=self.towplane, tow_pilot=self.member
        )
        self.assertIn("N6085S", str(row))

    def test_unique_constraint_enforced(self):
        LogsheetTowplane.objects.create(logsheet=self.logsheet, towplane=self.towplane)
        with self.assertRaises(Exception):
            # Intentionally not asserting IntegrityError to be agnostic about
            # the backend; the point is that the second save must fail.
            LogsheetTowplane.objects.create(
                logsheet=self.logsheet, towplane=self.towplane
            )

    def test_unique_per_logsheet(self):
        LogsheetTowplane.objects.create(
            logsheet=self.logsheet, towplane=self.towplane, tow_pilot=self.member
        )
        # Same towplane on a different logsheet (different date) is allowed.
        other_logsheet = _make_logsheet(
            self.airfield, self.member, date.today() + timedelta(days=5)
        )
        LogsheetTowplane.objects.create(logsheet=other_logsheet, towplane=self.towplane)
        self.assertEqual(
            LogsheetTowplane.objects.filter(
                logsheet=self.logsheet, towplane=self.towplane
            ).count(),
            1,
        )
        self.assertEqual(
            LogsheetTowplane.objects.filter(
                logsheet=other_logsheet, towplane=self.towplane
            ).count(),
            1,
        )

    def test_get_last_end_tach_returns_none_without_closeouts(self):
        self.assertIsNone(LogsheetTowplane.get_last_end_tach(self.towplane))

    def test_get_last_end_tach_returns_most_recent(self):
        d1 = date.today() - timedelta(days=3)
        d2 = date.today() - timedelta(days=1)
        ls1 = _make_logsheet(self.airfield, self.member, d1)
        ls2 = _make_logsheet(self.airfield, self.member, d2)
        TowplaneCloseout.objects.create(
            logsheet=ls1, towplane=self.towplane, end_tach=Decimal("100.00")
        )
        TowplaneCloseout.objects.create(
            logsheet=ls2, towplane=self.towplane, end_tach=Decimal("150.25")
        )
        self.assertEqual(
            LogsheetTowplane.get_last_end_tach(self.towplane), Decimal("150.25")
        )

    def test_get_last_end_tach_respects_before_date_exclusive(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        # Use distinct log_date per logsheet (Logsheet has a unique
        # (log_date, airfield) constraint).
        ls_y = _make_logsheet(self.airfield, self.member, yesterday)
        ls_t = _make_logsheet(self.airfield, self.member, today + timedelta(days=1))
        TowplaneCloseout.objects.create(
            logsheet=ls_y, towplane=self.towplane, end_tach=Decimal("100.00")
        )
        TowplaneCloseout.objects.create(
            logsheet=ls_t, towplane=self.towplane, end_tach=Decimal("150.25")
        )
        # before_date=tomorrow excludes tomorrow's closeout
        self.assertEqual(
            LogsheetTowplane.get_last_end_tach(
                self.towplane, before_date=today + timedelta(days=1)
            ),
            Decimal("100.00"),
        )

    def test_get_last_end_tach_skips_null_end_tach(self):
        d1 = date.today() - timedelta(days=2)
        d2 = date.today() - timedelta(days=1)
        ls1 = _make_logsheet(self.airfield, self.member, d1)
        ls2 = _make_logsheet(self.airfield, self.member, d2)
        TowplaneCloseout.objects.create(
            logsheet=ls1, towplane=self.towplane, end_tach=Decimal("100.00")
        )
        TowplaneCloseout.objects.create(
            logsheet=ls2, towplane=self.towplane, end_tach=None
        )
        self.assertEqual(
            LogsheetTowplane.get_last_end_tach(self.towplane), Decimal("100.00")
        )

    def test_set_null_on_member_delete(self):
        other = _make_member("other_pilot", towpilot=True)
        row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet, towplane=self.towplane, tow_pilot=other
        )
        other.delete()
        row.refresh_from_db()
        self.assertIsNone(row.tow_pilot)


class LogsheetTowplaneFormTests(TestCase):
    def setUp(self):
        self.towplane = Towplane.objects.create(
            name="Husky", n_number="N6085S", is_active=True, club_owned=True
        )
        self.virtual = Towplane.objects.create(
            name="Self Launch", n_number="SELF", is_active=True, club_owned=True
        )

    def test_towplane_queryset_excludes_virtual(self):
        from logsheet.forms import LogsheetTowplaneForm

        form = LogsheetTowplaneForm()
        choices = form.fields["towplane"].queryset
        self.assertIn(self.towplane, choices)
        self.assertNotIn(self.virtual, choices)

    def test_tow_pilot_queryset_requires_towpilot_role(self):
        from logsheet.forms import LogsheetTowplaneForm

        Member.objects.create_user(
            username="not_pilot",
            password="testpass123",
            first_name="Not",
            last_name="Pilot",
            membership_status="Full Member",
            email="np@example.com",
        )
        Member.objects.create_user(
            username="real_pilot",
            password="testpass123",
            first_name="Real",
            last_name="Pilot",
            membership_status="Full Member",
            towpilot=True,
            email="rp@example.com",
        )
        form = LogsheetTowplaneForm()
        pilot_ids = list(form.fields["tow_pilot"].queryset.values_list("pk", flat=True))
        real_pilot = Member.objects.get(username="real_pilot")
        not_pilot = Member.objects.get(username="not_pilot")
        self.assertIn(real_pilot.pk, pilot_ids)
        self.assertNotIn(not_pilot.pk, pilot_ids)


class CreateLogsheetRosterViewTests(TestCase):
    def setUp(self):
        self.member = _make_member("op1", towpilot=True)
        self.towplane = Towplane.objects.create(
            name="Husky", n_number="N6085S", is_active=True, club_owned=True
        )
        self.airfield = Airfield.objects.create(
            name="Test Field", identifier="TST", is_active=True
        )

    def _valid_form_data(self, extra=None):
        data = {
            "log_date": date.today().isoformat(),
            "airfield": self.airfield.pk,
        }
        if extra:
            data.update(extra)
        return data

    def test_create_logsheet_with_towplane_row(self):
        self.client.force_login(self.member)
        url = reverse("logsheet:create")
        data = self._valid_form_data(
            extra={
                "towplanes-TOTAL_FORMS": "1",
                "towplanes-INITIAL_FORMS": "0",
                "towplanes-MIN_NUM_FORMS": "0",
                "towplanes-MAX_NUM_FORMS": "1000",
                "towplanes-0-towplane": self.towplane.pk,
                "towplanes-0-tow_pilot": self.member.pk,
                "towplanes-0-start_tach": "100.00",
            }
        )
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        logsheet = Logsheet.objects.get(log_date=date.today(), airfield=self.airfield)
        row = LogsheetTowplane.objects.get(logsheet=logsheet)
        self.assertEqual(row.towplane, self.towplane)
        self.assertEqual(row.tow_pilot, self.member)
        self.assertEqual(row.start_tach, Decimal("100.00"))

    def test_create_logsheet_without_roster_row(self):
        self.client.force_login(self.member)
        url = reverse("logsheet:create")
        data = self._valid_form_data(
            extra={
                "towplanes-TOTAL_FORMS": "1",
                "towplanes-INITIAL_FORMS": "0",
                "towplanes-MIN_NUM_FORMS": "0",
                "towplanes-MAX_NUM_FORMS": "1000",
                # Empty row (towplane blank): the loop should skip it.
                "towplanes-0-towplane": "",
                "towplanes-0-tow_pilot": "",
                "towplanes-0-start_tach": "",
            }
        )
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        logsheet = Logsheet.objects.get(log_date=date.today(), airfield=self.airfield)
        self.assertEqual(LogsheetTowplane.objects.filter(logsheet=logsheet).count(), 0)

    def test_start_tach_prefill_map_excludes_virtual(self):
        self.client.force_login(self.member)
        # Seed a closeout with end_tach so the prefill map has an entry.
        prior_ls = _make_logsheet(
            self.airfield, self.member, date.today() - timedelta(days=1)
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls,
            towplane=self.towplane,
            end_tach=Decimal("42.42"),
        )
        # Add a virtual towplane with an end_tach too (should be excluded)
        virtual = Towplane.objects.create(
            name="Self", n_number="SELF", is_active=True, club_owned=True
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls, towplane=virtual, end_tach=Decimal("99.99")
        )
        url = reverse("logsheet:create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ctx_map = response.context["towplane_start_tach_map"]
        self.assertEqual(ctx_map[str(self.towplane.pk)], "42.42")
        self.assertNotIn(str(virtual.pk), ctx_map)


class AddTowplaneCloseoutRosterViewTests(TestCase):
    def setUp(self):
        self.member = _make_member("biff", towpilot=True)
        self.towplane = Towplane.objects.create(
            name="Husky", n_number="N6085S", is_active=True, club_owned=True
        )
        self.airfield = Airfield.objects.create(
            name="Test Field", identifier="TST", is_active=True
        )
        self.logsheet = _make_logsheet(self.airfield, self.member)

    def test_add_towplane_closeout_seeds_roster_row(self):
        self.client.force_login(self.member)
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        response = self.client.post(url, {"towplane": self.towplane.pk}, follow=True)
        self.assertEqual(response.status_code, 200)
        closeout = TowplaneCloseout.objects.get(
            logsheet=self.logsheet, towplane=self.towplane
        )
        self.assertIsNotNone(closeout.pk)
        row = LogsheetTowplane.objects.get(
            logsheet=self.logsheet, towplane=self.towplane
        )
        self.assertIsNotNone(row.pk)

    def test_add_towplane_closeout_seeds_start_tach_from_prior_closeout(self):
        self.client.force_login(self.member)
        prior_ls = _make_logsheet(
            self.airfield, self.member, self.logsheet.log_date - timedelta(days=1)
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls,
            towplane=self.towplane,
            end_tach=Decimal("100.55"),
        )
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        self.client.post(url, {"towplane": self.towplane.pk}, follow=True)
        closeout = TowplaneCloseout.objects.get(
            logsheet=self.logsheet, towplane=self.towplane
        )
        self.assertEqual(closeout.start_tach, Decimal("100.55"))

    def test_add_towplane_closeout_no_towplane_returns_message(self):
        self.client.force_login(self.member)
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        response = self.client.post(url, {}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            LogsheetTowplane.objects.filter(logsheet=self.logsheet).count(), 0
        )


class EditLogsheetCloseoutRosterViewTests(TestCase):
    def setUp(self):
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TSC",
        )
        self.member = _make_member("operator", towpilot=True)
        self.other = _make_member("other", towpilot=True)
        self.towplane = Towplane.objects.create(
            name="Husky", n_number="N6085S", is_active=True, club_owned=True
        )
        self.airfield = Airfield.objects.create(
            name="Test Field", identifier="TST", is_active=True
        )
        self.logsheet = _make_logsheet(self.airfield, self.member)

    def test_roster_formset_rendered_on_get(self):
        LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            tow_pilot=self.member,
            start_tach=Decimal("100.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("roster_formset", response.context)
        # The formset should include one seeded row + one extra empty form
        # (extra=1 in the formset factory).
        forms = list(response.context["roster_formset"])
        self.assertGreaterEqual(len(forms), 1)
        # First form should have our seeded row.
        self.assertEqual(forms[0].instance.towplane, self.towplane)

    def test_roster_save_creates_and_updates_rows(self):
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            # Closeout form (LogsheetCloseout)
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Test",
            # Duty crew form (all optional; leave blank)
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            # Existing closeout formset: no rows
            "form-TOTAL_FORMS": "0",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            # Roster formset: 1 row
            "roster-TOTAL_FORMS": "1",
            "roster-INITIAL_FORMS": "0",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-towplane": self.towplane.pk,
            "roster-0-tow_pilot": self.other.pk,
            "roster-0-start_tach": "100.00",
        }
        response = self.client.post(url, data)
        if response.status_code == 200:
            # Inspect form errors on the re-rendered page.
            ctx = response.context
            self.fail(
                "POST returned 200 (form errors). "
                "form.errors: %s | "
                "duty_form.errors: %s | "
                "roster_formset.errors: %s | "
                "roster_formset.non_form_errors: %s"
                % (
                    ctx["form"].errors,
                    ctx["duty_form"].errors,
                    ctx["roster_formset"].errors,
                    list(ctx["roster_formset"].non_form_errors()),
                )
            )
        self.assertEqual(response.status_code, 302)
        row = LogsheetTowplane.objects.get(
            logsheet=self.logsheet, towplane=self.towplane
        )
        self.assertEqual(row.tow_pilot, self.other)
        self.assertEqual(row.start_tach, Decimal("100.00"))

    def test_add_flight_returns_towplane_pilot_map(self):
        # Ensure the auto-fill map is exposed when rendering the add-flight form.
        LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            tow_pilot=self.member,
        )
        self.client.force_login(self.member)
        url = reverse("logsheet:add_flight", args=[self.logsheet.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # The map is embedded via json_script
        self.assertIn('id="towplane_pilot_map"', content)
        # And the pilot name/id should be in it
        self.assertIn(str(self.member.pk), content)
