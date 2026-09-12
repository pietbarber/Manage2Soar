"""Tests for LogsheetTowplane (Issue #1048): day-level towplane roster.

Covers:
- Model: unique constraint, get_last_end_tach helper
- Form: LogsheetTowplaneForm filtering (no virtual towplanes, towpilot role)
- Views: create_logsheet saves the roster; add_towplane_closeout seeds a
  roster row; edit_logsheet_closeout renders the roster formset.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from logsheet.models import (
    Airfield,
    Logsheet,
    LogsheetCloseout,
    LogsheetTowplane,
    MaintenanceIssue,
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

    def test_get_last_end_tach_map_uses_one_query(self):
        TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            end_tach=Decimal("123.45"),
        )
        with self.assertNumQueries(1):
            tach_map = LogsheetTowplane.get_last_end_tach_map(
                Towplane.objects.filter(pk=self.towplane.pk),
                before_date=date.today() + timedelta(days=1),
            )
        self.assertEqual(tach_map[self.towplane.pk], Decimal("123.45"))

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

    def test_existing_inactive_towplane_and_pilot_remain_selectable(self):
        from logsheet.forms import LogsheetTowplaneForm

        member = _make_member("inactive_roster_pilot", towpilot=True)
        member.membership_status = "Inactive"
        member.towpilot = False
        member.save(update_fields=["membership_status", "towpilot"])
        airfield = Airfield.objects.create(
            name="Inactive Field", identifier="INA", is_active=True
        )
        logsheet = _make_logsheet(airfield, member)
        row = LogsheetTowplane.objects.create(
            logsheet=logsheet,
            towplane=self.towplane,
            tow_pilot=member,
        )
        self.towplane.is_active = False
        self.towplane.save(update_fields=["is_active"])

        form = LogsheetTowplaneForm(instance=row)
        self.assertIn(self.towplane, form.fields["towplane"].queryset)
        self.assertIn(member, form.fields["tow_pilot"].queryset)

    def test_grounded_existing_row_can_be_bound_for_closeout_edits(self):
        from logsheet.forms import LogsheetTowplaneForm

        airfield = Airfield.objects.create(
            name="Grounded Closeout Field", identifier="GCF", is_active=True
        )
        member = _make_member("grounded_closeout_pilot", towpilot=True)
        logsheet = _make_logsheet(airfield, member)
        row = LogsheetTowplane.objects.create(logsheet=logsheet, towplane=self.towplane)
        MaintenanceIssue.objects.create(
            towplane=self.towplane,
            description="Grounded for closeout test",
            grounded=True,
            resolved=False,
            report_date=date.today(),
        )

        form = LogsheetTowplaneForm(instance=row, allow_grounded_instance=True)
        self.assertIn(self.towplane, form.fields["towplane"].queryset)

    def test_admin_roster_surfaces_use_constrained_form(self):
        from logsheet.admin import LogsheetTowplaneAdmin, LogsheetTowplaneInline
        from logsheet.forms import LogsheetTowplaneForm

        self.assertIs(LogsheetTowplaneInline.form, LogsheetTowplaneForm)
        self.assertIsNot(LogsheetTowplaneAdmin.form, LogsheetTowplaneForm)
        self.assertIn("logsheet", LogsheetTowplaneAdmin.form.base_fields)

    def test_admin_roster_form_exposes_parent_logsheet(self):
        from logsheet.admin import LogsheetTowplaneAdmin

        form = LogsheetTowplaneAdmin.form()
        self.assertIn("logsheet", form.fields)

    def test_start_tach_rejects_negative(self):
        from logsheet.forms import LogsheetTowplaneForm

        form = LogsheetTowplaneForm(
            {"start_tach": "-1.00", "towplane": self.towplane.pk}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("start_tach", form.errors)

    def test_model_full_clean_rejects_negative_start_tach(self):
        row = LogsheetTowplane(
            logsheet=_make_logsheet(
                Airfield.objects.create(name="V", identifier="VAL", is_active=True),
                _make_member("fullclean_pilot"),
            ),
            towplane=self.towplane,
            start_tach=Decimal("-5"),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_grounding_filter_excludes_grounded_instance(self):
        # An existing roster row must not remain selectable after its towplane
        # becomes grounded, even though the current-instance exception exists
        # for inactive planes.
        from logsheet.forms import LogsheetTowplaneForm

        airfield = Airfield.objects.create(
            name="Grounded Field", identifier="GRD", is_active=True
        )
        member = _make_member("ground_roster_pilot", towpilot=True)
        logsheet = _make_logsheet(airfield, member)
        row = LogsheetTowplane.objects.create(logsheet=logsheet, towplane=self.towplane)
        MaintenanceIssue.objects.create(
            towplane=self.towplane,
            description="Hydraulic leak",
            grounded=True,
            resolved=False,
            report_date=date.today(),
        )
        self.assertTrue(self.towplane.is_grounded)

        form = LogsheetTowplaneForm(instance=row)
        self.assertNotIn(self.towplane, form.fields["towplane"].queryset)

    def test_tow_pilot_label_uses_siteconfig_title(self):
        from logsheet.forms import LogsheetTowplaneForm

        SiteConfiguration.objects.create(
            club_name="Custom Club",
            domain_name="custom.com",
            club_abbreviation="CCU",
            towpilot_title="Lead Tow Pilot",
        )
        form = LogsheetTowplaneForm()
        self.assertEqual(form.fields["tow_pilot"].label, "Lead Tow Pilot")

    def test_towplane_queryset_excludes_virtual_case_insensitively(self):
        from logsheet.forms import LogsheetTowplaneForm

        virtual = Towplane.objects.create(
            name="Winch Lowercase", n_number="winch", is_active=True, club_owned=True
        )
        form = LogsheetTowplaneForm()
        self.assertNotIn(virtual, form.fields["towplane"].queryset)


class TowplaneCloseoutModelTests(TestCase):
    def setUp(self):
        self.member = _make_member("closeout_model_operator")
        self.airfield = Airfield.objects.create(
            name="Closeout Field", identifier="CLS", is_active=True
        )
        self.logsheet = _make_logsheet(self.airfield, self.member)
        self.towplane = Towplane.objects.create(
            name="Closeout Husky", n_number="NCLS", is_active=True, club_owned=True
        )

    def test_authoritative_start_tach_edit_clears_roster_provenance(self):
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
            start_tach_auto_derived_from_roster=True,
        )
        closeout.start_tach = Decimal("101.00")
        closeout.save()
        closeout.refresh_from_db()
        self.assertFalse(closeout.start_tach_auto_derived_from_roster)
        self.assertFalse(closeout.start_tach_manually_cleared)

    def test_authoritative_clear_marks_closeout_as_manually_cleared(self):
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
            start_tach_auto_derived_from_roster=True,
        )
        closeout.start_tach = None
        closeout.save()
        closeout.refresh_from_db()
        self.assertFalse(closeout.start_tach_auto_derived_from_roster)
        self.assertTrue(closeout.start_tach_manually_cleared)


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

    def test_create_logsheet_rejects_duplicate_roster_towplanes(self):
        self.client.force_login(self.member)
        url = reverse("logsheet:create")
        data = self._valid_form_data(
            extra={
                "towplanes-TOTAL_FORMS": "2",
                "towplanes-INITIAL_FORMS": "0",
                "towplanes-MIN_NUM_FORMS": "0",
                "towplanes-MAX_NUM_FORMS": "1000",
                "towplanes-0-towplane": self.towplane.pk,
                "towplanes-0-tow_pilot": "",
                "towplanes-0-start_tach": "100.00",
                "towplanes-1-towplane": self.towplane.pk,
                "towplanes-1-tow_pilot": "",
                "towplanes-1-start_tach": "101.00",
            }
        )
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Logsheet.objects.filter(
                log_date=date.today(), airfield=self.airfield
            ).exists()
        )

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
        lowercase_virtual = Towplane.objects.create(
            name="Lowercase Self", n_number="self", is_active=True, club_owned=True
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls, towplane=virtual, end_tach=Decimal("99.99")
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls, towplane=lowercase_virtual, end_tach=Decimal("98.98")
        )
        url = reverse("logsheet:create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ctx_map = response.context["towplane_start_tach_map"]
        self.assertEqual(ctx_map[str(self.towplane.pk)], "42.42")
        self.assertNotIn(str(virtual.pk), ctx_map)
        self.assertNotIn(str(lowercase_virtual.pk), ctx_map)

    def test_logsheet_list_page_includes_roster_formset_and_prefill_map(self):
        self.client.force_login(self.member)
        prior_ls = _make_logsheet(
            self.airfield, self.member, date.today() - timedelta(days=2)
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls,
            towplane=self.towplane,
            end_tach=Decimal("77.70"),
        )
        virtual = Towplane.objects.create(
            name="Winch", n_number="WINCH", is_active=True, club_owned=True
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls,
            towplane=virtual,
            end_tach=Decimal("88.80"),
        )

        response = self.client.get(reverse("logsheet:index"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("towplane_formset", response.context)
        self.assertIn("towplane_start_tach_map", response.context)
        ctx_map = response.context["towplane_start_tach_map"]
        self.assertEqual(ctx_map[str(self.towplane.pk)], "77.70")
        self.assertNotIn(str(virtual.pk), ctx_map)

    def test_logsheet_list_prefill_map_respects_requested_log_date(self):
        self.client.force_login(self.member)
        older_ls = _make_logsheet(
            self.airfield, self.member, date.today() - timedelta(days=3)
        )
        newer_ls = _make_logsheet(
            self.airfield, self.member, date.today() - timedelta(days=1)
        )
        TowplaneCloseout.objects.create(
            logsheet=older_ls,
            towplane=self.towplane,
            end_tach=Decimal("111.10"),
        )
        TowplaneCloseout.objects.create(
            logsheet=newer_ls,
            towplane=self.towplane,
            end_tach=Decimal("222.20"),
        )

        selected_day = (date.today() - timedelta(days=1)).isoformat()
        response = self.client.get(
            reverse("logsheet:index"), {"log_date": selected_day}
        )
        self.assertEqual(response.status_code, 200)
        ctx_map = response.context["towplane_start_tach_map"]
        # before_date is exclusive, so selected day should use only prior rows.
        self.assertEqual(ctx_map[str(self.towplane.pk)], "111.10")


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

    def test_add_towplane_closeout_uses_roster_start_tach(self):
        LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("88.80"),
        )
        self.client.force_login(self.member)
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        self.client.post(url, {"towplane": self.towplane.pk}, follow=True)

        closeout = TowplaneCloseout.objects.get(
            logsheet=self.logsheet, towplane=self.towplane
        )
        self.assertEqual(closeout.start_tach, Decimal("88.80"))

    def test_roster_start_tach_does_not_overwrite_closeout_start_tach(self):
        TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("77.70"),
        )
        LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("88.80"),
        )
        self.client.force_login(self.member)
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        self.client.post(url, {"towplane": self.towplane.pk}, follow=True)

        closeout = TowplaneCloseout.objects.get(
            logsheet=self.logsheet, towplane=self.towplane
        )
        self.assertEqual(closeout.start_tach, Decimal("77.70"))

    def test_roster_start_tach_precedes_historical_closeout_tach(self):
        prior_ls = _make_logsheet(
            self.airfield, self.member, self.logsheet.log_date - timedelta(days=1)
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_ls,
            towplane=self.towplane,
            end_tach=Decimal("100.00"),
        )
        LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("88.80"),
        )
        self.client.force_login(self.member)
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        self.client.post(url, {"towplane": self.towplane.pk}, follow=True)

        closeout = TowplaneCloseout.objects.get(
            logsheet=self.logsheet, towplane=self.towplane
        )
        self.assertEqual(closeout.start_tach, Decimal("88.80"))

    def test_virtual_towplane_closeout_does_not_seed_roster_row(self):
        virtual = Towplane.objects.create(
            name="Winch", n_number="WINCH", is_active=True, club_owned=True
        )
        self.client.force_login(self.member)
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        self.client.post(url, {"towplane": virtual.pk}, follow=True)

        self.assertFalse(
            LogsheetTowplane.objects.filter(
                logsheet=self.logsheet, towplane=virtual
            ).exists()
        )

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
        self.assertContains(response, 'name="roster-0-id"')
        self.assertIn(
            self.towplane,
            [
                closeout_form.instance.towplane
                for closeout_form in response.context["formset"]
            ],
        )

    def test_closeout_form_remains_logsheet_closeout_with_towplane_closeout(self):
        TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"].instance, LogsheetCloseout)

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
        self.assertTrue(
            TowplaneCloseout.objects.filter(
                logsheet=self.logsheet, towplane=self.towplane
            ).exists()
        )

    def test_roster_tach_correction_updates_auto_seeded_closeout(self):
        # The closeout start was auto-seeded from the roster and the operator
        # leaves it untouched on this POST, so it still follows the roster.
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
            end_tach=Decimal("120.00"),
            start_tach_auto_derived_from_roster=True,
        )
        roster_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Correct roster tach",
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(closeout.pk),
            "form-0-towplane": str(self.towplane.pk),
            "form-0-start_tach": "100.00",
            "form-0-end_tach": "120.00",
            "form-0-fuel_added": "",
            "form-0-notes": "",
            "roster-TOTAL_FORMS": "2",
            "roster-INITIAL_FORMS": "1",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-id": str(roster_row.pk),
            "roster-0-towplane": str(self.towplane.pk),
            "roster-0-tow_pilot": "",
            "roster-0-start_tach": "110.00",
            "roster-1-id": "",
            "roster-1-towplane": "",
            "roster-1-tow_pilot": "",
            "roster-1-start_tach": "",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        closeout.refresh_from_db()
        self.assertEqual(closeout.start_tach, Decimal("110.00"))
        self.assertEqual(closeout.tach_time, Decimal("10.00"))

    def test_roster_start_tach_does_not_overwrite_explicit_closeout_edit(self):
        # The operator intentionally cleared the auto-seeded closeout start
        # tach while the roster still holds a value: that explicit clear must
        # be respected, not overwritten with the roster value.
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
            end_tach=Decimal("120.00"),
        )
        roster_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Clear closeout start explicitly",
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(closeout.pk),
            "form-0-towplane": str(self.towplane.pk),
            "form-0-start_tach": "",
            "form-0-end_tach": "",
            "form-0-fuel_added": "",
            "form-0-notes": "",
            "roster-TOTAL_FORMS": "2",
            "roster-INITIAL_FORMS": "1",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-id": str(roster_row.pk),
            "roster-0-towplane": str(self.towplane.pk),
            "roster-0-tow_pilot": "",
            "roster-0-start_tach": "100.00",
            "roster-1-id": "",
            "roster-1-towplane": "",
            "roster-1-tow_pilot": "",
            "roster-1-start_tach": "",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        closeout.refresh_from_db()
        self.assertIsNone(closeout.start_tach)
        self.assertIsNone(closeout.tach_time)
        self.assertTrue(closeout.start_tach_manually_cleared)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["formset"].forms[0].instance.start_tach)
        data["roster-0-id"] = str(
            LogsheetTowplane.objects.get(
                logsheet=self.logsheet, towplane=self.towplane
            ).pk
        )
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        closeout.refresh_from_db()
        self.assertIsNone(closeout.start_tach)

    def test_roster_tach_correction_does_not_overwrite_matching_manual_closeout(self):
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
        )
        roster_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Leave matching manual closeout alone",
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(closeout.pk),
            "form-0-towplane": str(self.towplane.pk),
            "form-0-start_tach": "100.00",
            "form-0-end_tach": "",
            "form-0-fuel_added": "",
            "form-0-notes": "",
            "roster-TOTAL_FORMS": "2",
            "roster-INITIAL_FORMS": "1",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-id": str(roster_row.pk),
            "roster-0-towplane": str(self.towplane.pk),
            "roster-0-tow_pilot": "",
            "roster-0-start_tach": "110.00",
            "roster-1-id": "",
            "roster-1-towplane": "",
            "roster-1-tow_pilot": "",
            "roster-1-start_tach": "",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        closeout.refresh_from_db()
        self.assertEqual(closeout.start_tach, Decimal("100.00"))

    def test_add_towplane_closeout_rejects_grounded_towplane(self):
        """A grounded towplane must not create a closeout/roster row."""
        MaintenanceIssue.objects.create(
            towplane=self.towplane,
            description="Hydraulic leak",
            grounded=True,
            resolved=False,
            report_date=date.today(),
        )
        self.assertTrue(self.towplane.is_grounded)
        self.client.force_login(self.member)
        url = reverse("logsheet:add_towplane_closeout", kwargs={"pk": self.logsheet.pk})
        response = self.client.post(url, {"towplane": self.towplane.pk}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            TowplaneCloseout.objects.filter(
                logsheet=self.logsheet, towplane=self.towplane
            ).exists()
        )
        self.assertFalse(
            LogsheetTowplane.objects.filter(
                logsheet=self.logsheet, towplane=self.towplane
            ).exists()
        )
        self.assertContains(response, "grounded")

    def test_edit_closeout_available_towplanes_excludes_grounded_planes(self):
        second_towplane = Towplane.objects.create(
            name="Second Husky", n_number="N6086S", is_active=True, club_owned=True
        )
        MaintenanceIssue.objects.create(
            towplane=self.towplane,
            description="Hydraulic leak",
            grounded=True,
            resolved=False,
            report_date=date.today(),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        available_towplanes = list(response.context["available_towplanes"])
        self.assertNotIn(self.towplane, available_towplanes)
        self.assertIn(second_towplane, available_towplanes)

        virtual = Towplane.objects.create(
            name="Winch", n_number="winch", is_active=True, club_owned=True
        )
        response = self.client.get(url)
        self.assertNotIn(virtual, response.context["available_towplanes"])

    def test_roster_swap_persists_without_unique_constraint_failure(self):
        second_towplane = Towplane.objects.create(
            name="Second Husky", n_number="N6086S", is_active=True, club_owned=True
        )
        first_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet, towplane=self.towplane, start_tach=Decimal("100.00")
        )
        second_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=second_towplane,
            start_tach=Decimal("200.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Swap roster planes",
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            "form-TOTAL_FORMS": "0",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "roster-TOTAL_FORMS": "2",
            "roster-INITIAL_FORMS": "2",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-id": str(first_row.pk),
            "roster-0-towplane": str(second_towplane.pk),
            "roster-0-tow_pilot": "",
            "roster-0-start_tach": "100.00",
            "roster-1-id": str(second_row.pk),
            "roster-1-towplane": str(self.towplane.pk),
            "roster-1-tow_pilot": "",
            "roster-1-start_tach": "200.00",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LogsheetTowplane.objects.filter(
                logsheet=self.logsheet, towplane=self.towplane
            ).exists()
        )
        self.assertTrue(
            LogsheetTowplane.objects.filter(
                logsheet=self.logsheet, towplane=second_towplane
            ).exists()
        )

    def test_roster_save_preserves_unchanged_existing_rows(self):
        second_towplane = Towplane.objects.create(
            name="Second Husky", n_number="N6086S", is_active=True, club_owned=True
        )
        first_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet, towplane=self.towplane, start_tach=Decimal("100.00")
        )
        second_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=second_towplane,
            start_tach=Decimal("200.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Save unchanged roster",
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            "form-TOTAL_FORMS": "0",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "roster-TOTAL_FORMS": "2",
            "roster-INITIAL_FORMS": "2",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-id": str(first_row.pk),
            "roster-0-towplane": str(self.towplane.pk),
            "roster-0-tow_pilot": "",
            "roster-0-start_tach": "100.00",
            "roster-1-id": str(second_row.pk),
            "roster-1-towplane": str(second_towplane.pk),
            "roster-1-tow_pilot": "",
            "roster-1-start_tach": "200.00",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            LogsheetTowplane.objects.filter(logsheet=self.logsheet).count(), 2
        )

    def test_roster_tach_correction_recomputes_derived_tach_time(self):
        closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
            end_tach=Decimal("110.00"),
            tach_time=Decimal("10.00"),
            start_tach_auto_derived_from_roster=True,
        )
        roster_row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Recompute tach",
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(closeout.pk),
            "form-0-towplane": str(self.towplane.pk),
            "form-0-start_tach": "100.00",
            "form-0-end_tach": "110.00",
            "form-0-fuel_added": "",
            "form-0-notes": "",
            "roster-TOTAL_FORMS": "2",
            "roster-INITIAL_FORMS": "1",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-id": str(roster_row.pk),
            "roster-0-towplane": str(self.towplane.pk),
            "roster-0-tow_pilot": "",
            "roster-0-start_tach": "105.00",
            "roster-1-id": "",
            "roster-1-towplane": "",
            "roster-1-tow_pilot": "",
            "roster-1-start_tach": "",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        closeout.refresh_from_db()
        self.assertEqual(closeout.start_tach, Decimal("105.00"))
        self.assertEqual(closeout.tach_time, Decimal("5.00"))

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

    def test_roster_delete_existing_row(self):
        row = LogsheetTowplane.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            tow_pilot=self.member,
            start_tach=Decimal("90.00"),
        )
        self.client.force_login(self.member)
        url = reverse(
            "logsheet:edit_logsheet_closeout", kwargs={"pk": self.logsheet.pk}
        )
        data = {
            "safety_issues": "None",
            "equipment_issues": "None",
            "operations_summary": "Delete roster row",
            "duty_officer": "",
            "assistant_duty_officer": "",
            "duty_instructor": "",
            "surge_instructor": "",
            "tow_pilot": "",
            "surge_tow_pilot": "",
            "form-TOTAL_FORMS": "0",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "roster-TOTAL_FORMS": "2",
            "roster-INITIAL_FORMS": "1",
            "roster-MIN_NUM_FORMS": "0",
            "roster-MAX_NUM_FORMS": "1000",
            "roster-0-id": str(row.pk),
            "roster-0-towplane": str(self.towplane.pk),
            "roster-0-tow_pilot": str(self.member.pk),
            "roster-0-start_tach": "90.00",
            "roster-0-DELETE": "on",
            "roster-1-id": "",
            "roster-1-towplane": "",
            "roster-1-tow_pilot": "",
            "roster-1-start_tach": "",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LogsheetTowplane.objects.filter(pk=row.pk).exists())


class TowplaneStartTachApiTests(TestCase):
    def setUp(self):
        self.member = _make_member("api_operator", towpilot=True)
        self.towplane = Towplane.objects.create(
            name="Husky", n_number="N7000S", is_active=True, club_owned=True
        )
        self.airfield = Airfield.objects.create(
            name="Test Field", identifier="TST", is_active=True
        )

    def test_returns_start_tach_for_selected_towplane(self):
        self.client.force_login(self.member)
        prior = _make_logsheet(
            self.airfield, self.member, date.today() - timedelta(days=2)
        )
        TowplaneCloseout.objects.create(
            logsheet=prior,
            towplane=self.towplane,
            end_tach=Decimal("123.45"),
        )
        url = reverse("logsheet:api_towplane_start_tach")
        response = self.client.get(url, {"towplane_id": self.towplane.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["start_tach"], "123.45")

    def test_malformed_towplane_id_returns_empty_prefill(self):
        self.client.force_login(self.member)
        url = reverse("logsheet:api_towplane_start_tach")
        response = self.client.get(url, {"towplane_id": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["start_tach"])

    def test_respects_before_date_filter(self):
        self.client.force_login(self.member)
        older = _make_logsheet(
            self.airfield, self.member, date.today() - timedelta(days=3)
        )
        newer = _make_logsheet(
            self.airfield, self.member, date.today() - timedelta(days=1)
        )
        TowplaneCloseout.objects.create(
            logsheet=older,
            towplane=self.towplane,
            end_tach=Decimal("100.00"),
        )
        TowplaneCloseout.objects.create(
            logsheet=newer,
            towplane=self.towplane,
            end_tach=Decimal("200.00"),
        )
        cutoff = date.today() - timedelta(days=1)
        url = reverse("logsheet:api_towplane_start_tach")
        response = self.client.get(
            url,
            {
                "towplane_id": self.towplane.pk,
                "before_date": cutoff.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["start_tach"], "100.00")
