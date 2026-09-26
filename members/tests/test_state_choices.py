"""
Tests for issue #1062: "DC" (and APO) missing from state choices.

Covers:
1. US_STATE_CHOICES includes DC and the USPS APO regions.
2. Member.state_code accepts DC (model-level validation).
3. VisitingPilotReturningUpdateForm exposes DC.
4. Data migration 0028 promotes valid 2-letter codes stored in
   state_freeform into state_code (both NULL and empty-string state_code).
5. Legacy importer accepts DC and APO codes.
6. Issue #1065: Sport Pilot glider rating present.
"""

import importlib.util
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from members.constants.membership import US_STATE_CHOICES
from members.models import Member
from members.models_applications import MembershipApplication
from siteconfig.forms import VisitingPilotReturningUpdateForm

DC = "DC"
APO_REGIONS = {"AA", "AE", "AP"}
ALL_FIFTY_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}


def _load_migration_0028():
    """Import migration 0028 by file path (module names with leading digits
    can't be imported with a plain import statement)."""
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "0028_backfill_state_code_from_freeform.py"
    )
    spec = importlib.util.spec_from_file_location("m2s_0028_backfill", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("code", [DC] + sorted(APO_REGIONS))
def test_state_choices_include_dc_and_apo_regions(code):
    """DC and every USPS APO region must be a valid state choice."""
    codes = {choice for choice, _label in US_STATE_CHOICES}
    assert code in codes, f"{code} missing from US_STATE_CHOICES"


def test_state_choices_cover_all_fifty_states():
    """Regression guard: the 50 states must remain in the choices list."""
    codes = {choice for choice, _label in US_STATE_CHOICES}
    missing = ALL_FIFTY_STATES - codes
    assert not missing, f"Missing states in US_STATE_CHOICES: {missing}"


def test_state_codes_have_unique_values():
    """No choice value may be duplicated."""
    codes = [choice for choice, _label in US_STATE_CHOICES]
    assert len(codes) == len(set(codes)), "Duplicate state codes in choices"


@pytest.mark.django_db
def test_member_state_code_accepts_dc():
    """A member with state_code='DC' passes model-level validation."""
    member = Member(username="dc_member", membership_status="Full Member")
    member.state_code = DC
    member.state_freeform = ""
    # Member extends AbstractUser, so exclude password from validation.
    member.full_clean(exclude={"password"})  # raises if 'DC' is not a choice


@pytest.mark.django_db
def test_member_state_code_rejects_unknown_code():
    """Unknown 2-letter codes must still be rejected."""
    member = Member(username="bad_state_member", membership_status="Full Member")
    member.state_code = "ZZ"
    with pytest.raises(ValidationError) as exc_info:
        member.full_clean(exclude={"password"})
    assert "state_code" in exc_info.value.message_dict


@pytest.mark.django_db
def test_visiting_pilot_form_offers_dc():
    """The returning visiting pilot form must include DC as a choice."""
    form = VisitingPilotReturningUpdateForm()
    choices = dict(form.fields["state_code"].choices)
    assert DC in choices


@pytest.mark.django_db
def test_migration_0028_promotes_state_freeform_into_state_code():
    """Migration 0028's promotion logic moves valid codes into state_code."""
    module = _load_migration_0028()

    # Rows in the state the migration expects to find:
    member = Member.objects.create(
        username="freeform_dc_member",
        membership_status="Full Member",
        state_code=None,
        state_freeform="DC",
    )
    control = Member.objects.create(
        username="freeform_junk_member",
        membership_status="Full Member",
        state_code=None,
        state_freeform="Not A State",
    )
    already_correct = Member.objects.create(
        username="already_dc_member",
        membership_status="Full Member",
        state_code=DC,
        state_freeform="",
    )

    apps_stub = type(
        "Apps",
        (),
        {"get_model": lambda self, app_label, model: Member},
    )
    module.promote_state_codes(apps_stub(), None)

    member.refresh_from_db()
    assert member.state_code == DC
    assert member.state_freeform in ("", None)

    # Invalid freeform values must be left untouched.
    control.refresh_from_db()
    assert control.state_code is None
    assert control.state_freeform == "Not A State"

    # Rows already correct must be left untouched.
    already_correct.refresh_from_db()
    assert already_correct.state_code == DC
    assert already_correct.state_freeform in ("", None)


@pytest.mark.django_db
def test_migration_0028_promotes_empty_string_state_code():
    """The legacy importer writes state_code='' (not NULL) for unsupported
    states and stores the raw value in state_freeform.  Migration 0028 must
    promote those rows too."""
    module = _load_migration_0028()

    importer_row = Member.objects.create(
        username="importer_dc_member",
        membership_status="Full Member",
        state_code="",
        state_freeform="DC",
    )

    apps_stub = type(
        "Apps",
        (),
        {"get_model": lambda self, app_label, model: Member},
    )
    module.promote_state_codes(apps_stub(), None)

    importer_row.refresh_from_db()
    assert importer_row.state_code == DC
    assert importer_row.state_freeform in ("", None)


def test_legacy_importer_accepts_dc_and_apo():
    """The legacy importer's US_STATE_ABBREVIATIONS must include DC and APO."""
    from members.management.commands.import_members_only import (
        US_STATE_ABBREVIATIONS,
    )

    for code in [DC] + sorted(APO_REGIONS):
        assert (
            code in US_STATE_ABBREVIATIONS
        ), f"{code} missing from legacy importer US_STATE_ABBREVIATIONS"


def test_glider_rating_includes_sport_pilot():
    """Issue #1065: 'sport' must be a valid glider rating on Member."""
    codes = {choice for choice, _label in Member.GLIDER_RATING_CHOICES}
    assert "sport" in codes, "Sport Pilot missing from Member.GLIDER_RATING_CHOICES"


def test_application_glider_rating_includes_sport_pilot():
    """Issue #1065: 'sport' must be a valid rating on the application too."""
    codes = {choice for choice, _label in MembershipApplication.GLIDER_RATING_CHOICES}
    assert "sport" in codes


@pytest.mark.django_db
def test_member_sport_pilot_rating_valid():
    """A member with glider_rating='sport' passes model validation."""
    member = Member(username="sport_pilot_member", membership_status="Full Member")
    member.glider_rating = "sport"
    member.full_clean(exclude={"password"})
