from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q

from logsheet.models import Flight, Towplane, TowplaneCloseout

TOW_LOGBOOK_ESTIMATED_TACH_PER_TOW = Decimal("0.1")
TOW_LOGBOOK_ESTIMATED_HOBBS_PER_TOW = Decimal("0.2")


def _tow_logbook_estimates(total_tows):
    """Return summary-only estimated tach and Hobbs totals."""
    estimated_tach = (
        Decimal(total_tows) * TOW_LOGBOOK_ESTIMATED_TACH_PER_TOW
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    estimated_hobbs = (
        Decimal(total_tows) * TOW_LOGBOOK_ESTIMATED_HOBBS_PER_TOW
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return estimated_tach, estimated_hobbs


def get_tow_logbook_data(member, start_date):
    """Build day-level tow logbook rows and summary metrics for a tow pilot member."""
    virtual_towplane_q = Q()
    for virtual_n_number in Towplane.VIRTUAL_N_NUMBERS:
        virtual_towplane_q |= Q(towplane__n_number__iexact=virtual_n_number)

    tow_launch_filter = Q(towplane__isnull=False) & ~virtual_towplane_q

    tow_flights = (
        Flight.objects.filter(
            tow_pilot=member,
            logsheet__log_date__gte=start_date,
        )
        .filter(tow_launch_filter)
        .select_related("logsheet", "logsheet__airfield")
    )

    day_summaries = (
        tow_flights.values(
            "logsheet_id",
            "logsheet__log_date",
            "logsheet__airfield__identifier",
        )
        .annotate(your_tows=Count("id"))
        .order_by(
            "-logsheet__log_date",
            "logsheet__airfield__identifier",
            "-logsheet_id",
        )
    )
    day_summaries = list(day_summaries)

    member_towplane_ids_by_logsheet = {}
    towplane_tows_by_logsheet = {}
    for row in tow_flights.values(
        "logsheet_id", "towplane_id", "towplane__n_number"
    ).annotate(tows=Count("id")):
        member_towplane_ids_by_logsheet.setdefault(row["logsheet_id"], set()).add(
            row["towplane_id"]
        )
        towplane_tows_by_logsheet.setdefault(row["logsheet_id"], {})[
            row["towplane_id"]
        ] = (row["towplane__n_number"], row["tows"])

    logsheet_ids = [row["logsheet_id"] for row in day_summaries]
    tow_pilot_counts = {
        row["logsheet_id"]: row["pilot_count"]
        for row in Flight.objects.filter(
            logsheet_id__in=logsheet_ids, tow_pilot__isnull=False
        )
        .filter(tow_launch_filter)
        .values("logsheet_id")
        .annotate(pilot_count=Count("tow_pilot", distinct=True))
    }

    logsheet_ids_with_guest_or_legacy_tow_refs = set(
        Flight.objects.filter(logsheet_id__in=logsheet_ids)
        .filter(tow_launch_filter)
        .filter(
            Q(guest_towpilot_name__isnull=False) & ~Q(guest_towpilot_name="")
            | Q(legacy_towpilot_name__isnull=False) & ~Q(legacy_towpilot_name="")
        )
        .values_list("logsheet_id", flat=True)
        .distinct()
    )

    closeouts_by_logsheet = {}
    for closeout in (
        TowplaneCloseout.objects.filter(logsheet_id__in=logsheet_ids)
        .exclude(virtual_towplane_q)
        .select_related("towplane")
        .prefetch_related("rental_charges")
    ):
        member_towplane_ids = member_towplane_ids_by_logsheet.get(
            closeout.logsheet_id, set()
        )
        if closeout.towplane_id in member_towplane_ids:
            closeouts_by_logsheet.setdefault(closeout.logsheet_id, []).append(closeout)

    day_rows = []
    total_tow_hours = Decimal("0.00")
    total_tows = 0

    for summary in day_summaries:
        logsheet_id = summary["logsheet_id"]
        your_tows = summary["your_tows"]
        total_tows += your_tows

        solo_towpilot_day = (
            tow_pilot_counts.get(logsheet_id, 0) == 1
            and logsheet_id not in logsheet_ids_with_guest_or_legacy_tow_refs
        )
        tow_hours = None
        if solo_towpilot_day:
            hours_source = "Estimated (solo tow pilot day - no tach closeout)"
        else:
            hours_source = "Estimated (shared tow day)"

        actual_by_towplane = {}
        if solo_towpilot_day:
            closeouts = closeouts_by_logsheet.get(logsheet_id, [])
            closeout_total = Decimal("0.00")
            has_actual = False
            for closeout in closeouts:
                # Issue #968: sum of per-renter charges; falls back to the
                # legacy single-renter scalar when no charge rows exist.
                rental_hours = Decimal(closeout.total_rental_hours or 0)
                closeout_hours = None
                if closeout.tach_time is not None:
                    closeout_hours = max(
                        Decimal("0.00"), Decimal(closeout.tach_time) - rental_hours
                    )
                elif closeout.start_tach is not None and closeout.end_tach is not None:
                    closeout_hours = max(
                        Decimal("0.00"),
                        (Decimal(closeout.end_tach) - Decimal(closeout.start_tach))
                        - rental_hours,
                    )
                if closeout_hours is not None:
                    closeout_total += closeout_hours
                    has_actual = True
                    actual_by_towplane[closeout.towplane_id] = (
                        actual_by_towplane.get(closeout.towplane_id, Decimal("0.00"))
                        + closeout_hours
                    )

            if has_actual:
                tow_hours = closeout_total.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                hours_source = "Actual tach (solo tow pilot day)"

        if tow_hours is None:
            tow_hours = (
                Decimal(your_tows) * TOW_LOGBOOK_ESTIMATED_TACH_PER_TOW
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Per-towplane split: actual tach when this towplane has a closeout,
        # otherwise the per-tow estimate. On a day with actual tach for another
        # towplane, a towplane without a closeout is flagged unresolved at 0.00
        # so the per-towplane hours still sum to tow_hours.
        towplanes = []
        for towplane_id, (n_number, tows) in sorted(
            towplane_tows_by_logsheet.get(logsheet_id, {}).items(),
            key=lambda item: (item[1][0] or "", item[0]),
        ):
            allocation_resolved = True
            if actual_by_towplane:
                tp_hours = actual_by_towplane.get(towplane_id)
                if tp_hours is None:
                    tp_hours = Decimal("0.00")
                    allocation_resolved = False
            else:
                tp_hours = Decimal(tows) * TOW_LOGBOOK_ESTIMATED_TACH_PER_TOW
            towplanes.append(
                {
                    "towplane_id": towplane_id,
                    "n_number": n_number or "",
                    "tows": tows,
                    "hours": tp_hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    "allocation_resolved": allocation_resolved,
                }
            )

        total_tow_hours += tow_hours
        day_rows.append(
            {
                "tow_date": summary["logsheet__log_date"],
                "airfield_identifier": summary["logsheet__airfield__identifier"] or "—",
                "your_tows": your_tows,
                "tow_hours": tow_hours,
                "hours_source": hours_source,
                "towplanes": towplanes,
            }
        )

    distinct_tow_days = len({row["tow_date"] for row in day_rows})
    total_tow_hours = total_tow_hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    estimated_tach_total, estimated_hobbs_total = _tow_logbook_estimates(total_tows)

    return {
        "day_rows": day_rows,
        "total_tows": total_tows,
        "distinct_tow_days": distinct_tow_days,
        "total_tow_hours": total_tow_hours,
        "estimated_tach_total": estimated_tach_total,
        "estimated_hobbs_total": estimated_hobbs_total,
    }
