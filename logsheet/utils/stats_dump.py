import csv
import os
import tempfile
from decimal import ROUND_HALF_UP, Decimal

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from logsheet.models import (
    Flight,
    StatsDumpOutbox,
    TowplaneChargeScheme,
    TowplaneChargeTier,
)
from logsheet.utils.flight_charges import (
    effective_rental_cost as _effective_rental_cost,
)
from siteconfig.models import (
    MembershipBillingRule,
    MembershipGliderRentalRule,
    SiteConfiguration,
)
from utils.csv import sanitize_csv_cell as _sanitize_csv_cell

MAX_LAST_ERROR_LENGTH = 2000


def _stats_dump_person_name(*, member=None, guest_name=None, legacy_name=None):
    """Return a best-effort display name for people columns in stats dump CSV."""
    if member:
        if hasattr(member, "full_display_name") and member.full_display_name:
            return member.full_display_name
        first = (member.first_name or "").strip()
        last = (member.last_name or "").strip()
        if first or last:
            return " ".join(part for part in [first, last] if part)
        return member.username

    guest = (guest_name or "").strip()
    if guest:
        return guest

    legacy = (legacy_name or "").strip()
    if legacy:
        return legacy

    return ""


def _stats_dump_duration_text(duration):
    """Return duration in HH:MM:SS form, preserving empty values."""
    if duration is None:
        return ""

    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def iter_stats_dump_rows():
    """Yield stats dump rows as a sequence of CSV-compatible values."""
    yield [
        "flight_tracking_id",
        "flight_date",
        "pilot",
        "passenger",
        "glider",
        "instructor",
        "towpilot",
        "flight_type",
        "takeoff_time",
        "landing_time",
        "flight_time",
        "release_altitude",
        "flight_cost",
        "tow_cost",
        "total_cost",
        "field",
    ]

    flights = (
        Flight.objects.select_related(
            "logsheet",
            "logsheet__airfield",
            "airfield",
            "pilot",
            "passenger",
            "glider",
            "instructor",
            "towplane",
            "towplane__charge_scheme",
            "tow_pilot",
        )
        .order_by("logsheet__log_date", "logsheet_id", "pk")
        .iterator(chunk_size=2000)
    )

    pricing_caches_loaded = False
    active_tiers_by_scheme = {}
    billing_rules_by_status = {}
    glider_rules_by_status_glider = {}
    site_config = SiteConfiguration.objects.first()

    for flight in flights:
        flight._site_config_cache = site_config

        needs_calculated_pricing = (not flight.logsheet.finalized) or (
            flight.logsheet.finalized
            and (flight.tow_cost_actual is None or flight.rental_cost_actual is None)
        )

        if needs_calculated_pricing:
            if not pricing_caches_loaded:
                for tier in (
                    TowplaneChargeTier.objects.filter(
                        is_active=True,
                        charge_scheme__is_active=True,
                    )
                    .select_related("charge_scheme")
                    .order_by("charge_scheme_id", "altitude_start")
                ):
                    active_tiers_by_scheme.setdefault(tier.charge_scheme_id, []).append(
                        tier
                    )

                billing_rules_by_status = {
                    rule.membership_status.name: rule
                    for rule in MembershipBillingRule.objects.select_related(
                        "membership_status"
                    ).filter(is_active=True)
                }
                glider_rules_by_status_glider = {
                    (rule.membership_status.name, rule.glider_id): rule
                    for rule in MembershipGliderRentalRule.objects.select_related(
                        "membership_status", "glider"
                    ).filter(is_active=True)
                }
                pricing_caches_loaded = True

            pilot_status = (
                flight.pilot.membership_status
                if flight.pilot and flight.pilot.membership_status
                else None
            )
            if pilot_status:
                flight._membership_billing_rule_cache = (
                    billing_rules_by_status.get(pilot_status) or False
                )
                if flight.glider and flight.glider.pk:
                    flight._membership_glider_rental_rule_cache = (
                        glider_rules_by_status_glider.get(
                            (pilot_status, flight.glider.pk)
                        )
                        or False
                    )
                else:
                    flight._membership_glider_rental_rule_cache = False
            else:
                flight._membership_billing_rule_cache = False
                flight._membership_glider_rental_rule_cache = False
        else:
            flight._membership_billing_rule_cache = False
            flight._membership_glider_rental_rule_cache = False

        if needs_calculated_pricing and flight.towplane_id:
            try:
                scheme = flight.towplane.charge_scheme
                scheme._active_charge_tiers = active_tiers_by_scheme.get(scheme.pk, [])
            except TowplaneChargeScheme.DoesNotExist:
                pass

        if flight.logsheet.finalized:
            tow_cost = flight.tow_cost_actual
            if tow_cost is None:
                tow_cost = flight.tow_cost_calculated or Decimal("0.00")

            rental_cost = _effective_rental_cost(flight) or Decimal("0.00")
            instruction_cost = flight.instruction_fee_actual or Decimal("0.00")
        else:
            tow_cost = flight.tow_cost_calculated or Decimal("0.00")
            rental_cost = _effective_rental_cost(flight) or Decimal("0.00")
            instruction_cost = flight.instruction_fee_calculated or Decimal("0.00")

        flight_cost = (rental_cost + instruction_cost).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        tow_cost = tow_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_cost = (flight_cost + tow_cost).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        airfield_label = ""
        field_airfield = None
        if (
            flight.airfield_id
            and flight.logsheet
            and flight.logsheet.airfield_id
            and flight.airfield_id != flight.logsheet.airfield_id
        ):
            field_airfield = flight.airfield
        elif flight.logsheet and flight.logsheet.airfield:
            field_airfield = flight.logsheet.airfield
        elif flight.airfield_id:
            field_airfield = flight.airfield

        if field_airfield:
            airfield_label = field_airfield.identifier or field_airfield.name or ""

        yield [
            str(flight.pk),
            flight.logsheet.log_date.isoformat() if flight.logsheet else "",
            _sanitize_csv_cell(
                _stats_dump_person_name(
                    member=flight.pilot,
                    guest_name=flight.guest_pilot_name,
                    legacy_name=flight.legacy_pilot_name,
                )
            ),
            _sanitize_csv_cell(
                _stats_dump_person_name(
                    member=flight.passenger,
                    guest_name=flight.passenger_name,
                    legacy_name=flight.legacy_passenger_name,
                )
            ),
            _sanitize_csv_cell(str(flight.glider) if flight.glider else ""),
            _sanitize_csv_cell(
                _stats_dump_person_name(
                    member=flight.instructor,
                    guest_name=flight.guest_instructor_name,
                    legacy_name=flight.legacy_instructor_name,
                )
            ),
            _sanitize_csv_cell(
                _stats_dump_person_name(
                    member=flight.tow_pilot,
                    guest_name=flight.guest_towpilot_name,
                    legacy_name=flight.legacy_towpilot_name,
                )
            ),
            _sanitize_csv_cell(flight.flight_type or ""),
            flight.launch_time.isoformat() if flight.launch_time else "",
            flight.landing_time.isoformat() if flight.landing_time else "",
            _stats_dump_duration_text(flight.computed_duration),
            flight.release_altitude if flight.release_altitude is not None else "",
            f"{flight_cost:.2f}",
            f"{tow_cost:.2f}",
            f"{total_cost:.2f}",
            _sanitize_csv_cell(airfield_label),
        ]


def _build_stats_dump_filename(outbox_id):
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    return f"stats_dump_{timestamp}_{outbox_id}.csv"


def process_stats_dump_outbox_job(outbox_id):
    """Process one durable outbox entry and generate stats dump CSV."""
    with transaction.atomic():
        outbox = StatsDumpOutbox.objects.select_for_update().get(pk=outbox_id)
        if outbox.status in [
            StatsDumpOutbox.STATUS_PROCESSING,
            StatsDumpOutbox.STATUS_READY,
        ]:
            return

        outbox.status = StatsDumpOutbox.STATUS_PROCESSING
        outbox.attempt_count += 1
        outbox.started_at = timezone.now()
        outbox.completed_at = None
        outbox.last_error = ""
        outbox.save(
            update_fields=[
                "status",
                "attempt_count",
                "started_at",
                "completed_at",
                "last_error",
            ]
        )

    filename = _build_stats_dump_filename(outbox_id)

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            suffix=".csv",
            delete=False,
        ) as tmp_file:
            writer = csv.writer(tmp_file)
            for row in iter_stats_dump_rows():
                writer.writerow(row)
            temp_path = tmp_file.name

        outbox = StatsDumpOutbox.objects.get(pk=outbox_id)
        if outbox.result_file:
            outbox.result_file.delete(save=False)

        with open(temp_path, "rb") as generated_file:
            outbox.result_file.save(filename, File(generated_file), save=False)

        outbox.status = StatsDumpOutbox.STATUS_READY
        outbox.result_filename = filename
        outbox.completed_at = timezone.now()
        outbox.last_error = ""
        outbox.save(
            update_fields=[
                "result_file",
                "status",
                "result_filename",
                "completed_at",
                "last_error",
            ]
        )
    except Exception as exc:
        StatsDumpOutbox.objects.filter(pk=outbox_id).update(
            status=StatsDumpOutbox.STATUS_FAILED,
            last_error=str(exc)[:MAX_LAST_ERROR_LENGTH],
            completed_at=timezone.now(),
        )
    finally:
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
