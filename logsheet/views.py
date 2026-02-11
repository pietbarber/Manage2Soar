# AJAX endpoint to update split fields for a flight
import logging
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_time
from django.utils.timezone import now
from django.views.decorators.http import require_GET, require_POST

from duty_roster.models import GliderReservation
from members.decorators import active_member_required
from members.models import Member
from siteconfig.models import SiteConfiguration

from .forms import (
    CreateLogsheetForm,
    FlightForm,
    LogsheetCloseoutForm,
    LogsheetDutyCrewForm,
    MaintenanceIssueForm,
    TowplaneCloseoutFormSet,
)
from .models import (
    AircraftMeister,
    Flight,
    Glider,
    Logsheet,
    LogsheetCloseout,
    LogsheetPayment,
    MaintenanceDeadline,
    MaintenanceIssue,
    MemberCharge,
    RevisionLog,
    Towplane,
    TowplaneCloseout,
)

logger = logging.getLogger(__name__)


def get_validation_message(validation_error):
    """
    Extract user-facing message from a Django ValidationError.

    This helper ensures we only expose the message text, not any
    internal exception details. ValidationError messages are designed
    to be shown to users (e.g., "This glider is already scheduled...").

    Args:
        validation_error: Django ValidationError instance

    Returns:
        str: The user-facing error message
    """
    # Access .messages directly - Django ValidationError always has this
    if hasattr(validation_error, "messages") and validation_error.messages:
        return "; ".join(str(m) for m in validation_error.messages)
    # Fallback: generic message instead of str(exception) to avoid stack trace exposure
    return "Validation failed"


@require_POST
@active_member_required
def update_flight_split(request, flight_id):
    flight = get_object_or_404(Flight, id=flight_id)
    logsheet = flight.logsheet
    if logsheet.finalized:
        return JsonResponse(
            {"success": False, "error": "Logsheet is finalized."}, status=403
        )

    split_with_id = request.POST.get("split_with")
    split_type = request.POST.get("split_type")

    # Allow clearing the split by accepting empty values. If provided, validate.
    split_with = None
    if split_with_id:
        try:
            split_with = Member.objects.get(id=split_with_id)
        except Member.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Invalid member selected."}, status=400
            )

    # Validate split_type only if provided (non-empty). Empty => clear.
    valid_types = ["even", "tow", "rental", "full"]
    split_type_value = split_type or None
    if split_type_value and split_type_value not in valid_types:
        return JsonResponse(
            {"success": False, "error": "Invalid split type."}, status=400
        )

    flight.split_with = split_with
    flight.split_type = split_type_value
    flight.save(update_fields=["split_with", "split_type"])
    return JsonResponse({"success": True})


# --- LANDING NOW AJAX ENDPOINT ---


@require_POST
@active_member_required
def land_flight_now(request, flight_id):
    import json

    from django.core.exceptions import ValidationError

    from .forms import validate_glider_availability

    try:
        flight = get_object_or_404(Flight, pk=flight_id)
        if not flight.launch_time:
            return JsonResponse(
                {"success": False, "error": "Flight has not launched yet."}, status=400
            )
        if flight.landing_time:
            return JsonResponse(
                {"success": False, "error": "Flight already landed."}, status=400
            )
        data = json.loads(request.body.decode())
        landing_time_str = data.get("landing_time")
        if not landing_time_str:
            return JsonResponse(
                {"success": False, "error": "No landing time provided."}, status=400
            )
        landing_time = parse_time(landing_time_str)
        if not landing_time:
            return JsonResponse(
                {"success": False, "error": "Invalid time format."}, status=400
            )

        # Validate glider availability before setting landing time
        try:
            validate_glider_availability(
                flight, flight.glider, flight.launch_time, landing_time
            )
        except ValidationError as e:
            # Use helper to extract only user-facing message (not stack trace)
            return JsonResponse(
                {"success": False, "error": get_validation_message(e)}, status=400
            )

        flight.landing_time = landing_time
        flight.save(update_fields=["landing_time"])
        return JsonResponse({"success": True})
    except Exception as e:
        logger.exception("Error landing flight %s", flight_id)
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."},
            status=500,
        )


@require_POST
@active_member_required
def launch_flight_now(request, flight_id):
    import json

    from django.core.exceptions import ValidationError

    from .forms import validate_glider_availability

    try:
        flight = get_object_or_404(Flight, pk=flight_id)
        if flight.launch_time:
            return JsonResponse(
                {"success": False, "error": "Flight already launched."}, status=400
            )
        data = json.loads(request.body.decode())
        launch_time_str = data.get("launch_time")
        if not launch_time_str:
            return JsonResponse(
                {"success": False, "error": "No launch time provided."}, status=400
            )
        launch_time = parse_time(launch_time_str)
        if not launch_time:
            return JsonResponse(
                {"success": False, "error": "Invalid time format."}, status=400
            )

        # Validate glider availability before setting launch time
        try:
            validate_glider_availability(
                flight, flight.glider, launch_time, flight.landing_time
            )
        except ValidationError as e:
            # Use helper to extract only user-facing message (not stack trace)
            return JsonResponse(
                {"success": False, "error": get_validation_message(e)}, status=400
            )

        flight.launch_time = launch_time
        flight.save(update_fields=["launch_time"])
        return JsonResponse({"success": True})
    except Exception as e:
        logger.exception("Error launching flight %s", flight_id)
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."},
            status=500,
        )


# Delete logsheet if empty (no flights, no closeout, no payments)


@require_POST
@active_member_required
def delete_logsheet(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    has_towplane_closeout = (
        logsheet.towplane_closeouts.exists()
        if hasattr(logsheet, "towplane_closeouts")
        else False
    )
    if (
        logsheet.flights.count() == 0
        and not hasattr(logsheet, "closeout")
        and logsheet.payments.count() == 0
        and not logsheet.finalized
        and not has_towplane_closeout
    ):
        logsheet.delete()
        messages.success(request, "Logsheet deleted.")
        return redirect("logsheet:index")
    else:
        return HttpResponseForbidden(
            "Logsheet cannot be deleted: it has flights, closeout, payments, towplane summary, or is finalized."
        )


# AJAX API endpoint for duty assignment lookup


@require_GET
@active_member_required
def api_duty_assignment(request):
    from duty_roster.models import DutyAssignment

    date_str = request.GET.get("date")
    result = {
        "duty_officer": None,
        "assistant_duty_officer": None,
        "duty_instructor": None,
        "surge_instructor": None,
        "tow_pilot": None,
        "surge_tow_pilot": None,
    }
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            assignment = DutyAssignment.objects.filter(date=dt).first()
            if assignment:
                result["duty_officer"] = assignment.duty_officer_id
                result["assistant_duty_officer"] = assignment.assistant_duty_officer_id
                result["duty_instructor"] = assignment.instructor_id
                result["surge_instructor"] = assignment.surge_instructor_id
                result["tow_pilot"] = assignment.tow_pilot_id
                result["surge_tow_pilot"] = assignment.surge_tow_pilot_id
        except Exception as e:
            logging.warning(f"Failed to fetch duty assignments for date: {e}")
    return JsonResponse(result)


#################################################
# index
# This function might have been abandoned.  Considering updating it or deleting it.
@active_member_required
def index(request):
    return render(request, "logsheet/index.html")


#################################################
# Handles the creation of a new logsheet.
#
# This view is accessible only to active members due to the `@active_member_required` decorator.
# It processes both GET and POST requests:
# - For GET requests, it initializes an empty `CreateLogsheetForm` and renders the logsheet creation page.
# - For POST requests, it validates the submitted form data, creates a new logsheet instance, associates it with the currently logged-in user, and saves it to the database. If successful, it redirects the user to the logsheet management page and displays a success message.
#
# Args:
#    request (HttpRequest): The HTTP request object containing metadata about the request.
#
# Returns:
#    HttpResponse: Renders the logsheet creation page with the form for GET requests.
#    HttpResponseRedirect: Redirects to the logsheet management page upon successful creation of a logsheet.


@active_member_required
def create_logsheet(request):
    if request.method == "POST":
        form = CreateLogsheetForm(request.POST)
        if form.is_valid():
            logsheet = form.save(commit=False)
            logsheet.created_by = request.user
            logsheet.save()
            messages.success(
                request,
                f"Logsheet for {logsheet.log_date} at {logsheet.airfield} created.",
            )
            return redirect("logsheet:manage", pk=logsheet.pk)
    else:
        # Auto-populate duty crew for today's date
        form = CreateLogsheetForm(duty_assignment_date=date.today())

    return render(request, "logsheet/start_logsheet.html", {"form": form})


#################################################
# manage_logsheet

# This view handles the management of a specific logsheet.
#
# It allows active members to:
# - View all flights associated with the logsheet, with optional filtering by pilot or instructor name.
# - Add new flights to the logsheet (if not finalized).
# - Finalize the logsheet, locking in all calculated costs as actual costs.
# - Reopen a finalized logsheet for revision (authorized users only).
#
# Args:
#    request (HttpRequest): The HTTP request object containing metadata about the request.
#    pk (int): The primary key of the logsheet to manage.
#
# Returns:
#    HttpResponse: Renders the logsheet management page with the list of flights and a form for adding flights.
#    HttpResponseRedirect: Redirects to the same page after performing actions like finalizing, revising, or adding flights.


@active_member_required
def manage_logsheet(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    # Base queryset for all flights in the logsheet
    all_flights = (
        Flight.objects.select_related(
            "pilot", "instructor", "glider", "towplane", "tow_pilot"
        )
        .filter(logsheet=logsheet)
        .order_by("-landing_time", "-launch_time")
    )

    # Filtered queryset for display purposes only
    flights = all_flights
    query = request.GET.get("q")
    if query:
        flights = flights.filter(
            Q(pilot__first_name__icontains=query)
            | Q(pilot__last_name__icontains=query)
            | Q(instructor__first_name__icontains=query)
            | Q(instructor__last_name__icontains=query)
        )

    if request.method == "POST" and "finalize" in request.POST:
        if logsheet.finalized:
            messages.info(request, "This logsheet has already been finalized.")
            return redirect("logsheet:manage", pk=logsheet.pk)

        # 🔒 REQUIRE CLOSEOUT BEFORE FINALIZATION
        if not hasattr(logsheet, "closeout"):
            messages.error(request, "Cannot finalize. Closeout has not been completed.")
            return redirect("logsheet:manage", pk=logsheet.pk)

        responsible_members = set()
        invalid_flights = []

        # Use unfiltered queryset for validation to avoid filtered subset issues
        for flight in all_flights:
            pilot = flight.pilot
            partner = flight.split_with
            split = flight.split_type

            # Ensure that the flight has a valid pilot
            if partner and split == "full":
                responsible_members.add(partner)
            elif partner and split in ("even", "tow", "rental"):
                responsible_members.update([pilot, partner])
            elif pilot:
                responsible_members.add(pilot)

            # Validate required fields before finalization
            if flight.landing_time is None:
                invalid_flights.append(
                    f"Flight #{flight.id} is missing a landing time."
                )
            if flight.release_altitude is None:
                invalid_flights.append(
                    f"Flight #{flight.id} is missing a release altitude."
                )
            # Only require towplane and tow pilot for towplane launches
            if flight.requires_tow:
                if not flight.towplane:
                    invalid_flights.append(
                        f"Flight #{flight.id} is missing a tow plane."
                    )
                if not flight.tow_pilot:
                    invalid_flights.append(
                        f"Flight #{flight.id} is missing a tow pilot."
                    )
            if flight.launch_time is None:
                invalid_flights.append(f"Flight #{flight.id} is missing a launch time.")

        # Enforce required duty crew before finalization
        # Only require logsheet.tow_pilot if there are any towplane launches
        # Use unfiltered queryset for validation
        has_tow_flights = any(f.requires_tow for f in all_flights)

        required_roles = {
            "duty_officer": logsheet.duty_officer,
            "duty_instructor": logsheet.duty_instructor,
        }

        # Only require tow pilot if any flights use towplane launches
        if has_tow_flights:
            required_roles["tow_pilot"] = logsheet.tow_pilot

        missing_roles = [
            label.replace("_", " ").title()
            for label, value in required_roles.items()
            if not value
        ]

        if missing_roles:
            messages.error(
                request,
                "Cannot finalize. Missing duty crew: " + ", ".join(missing_roles),
            )
            return redirect("logsheet:manage", pk=logsheet.pk)

        missing = []

        # Check if all responsible members have a payment method set
        for member in responsible_members:
            try:
                payment = LogsheetPayment.objects.get(logsheet=logsheet, member=member)
                if not payment.payment_method:
                    missing.append(member)
            except LogsheetPayment.DoesNotExist:
                missing.append(member)

        # If there are invalid flights, do not finalize
        if invalid_flights:
            for msg in invalid_flights:
                messages.error(request, msg)
            return redirect("logsheet:manage", pk=logsheet.pk)

        # If there are missing payment methods, do not finalize
        if missing:
            messages.error(
                request,
                "Cannot finalize. Missing payment method for: "
                + ", ".join(str(m) for m in missing),
            )
            return redirect("logsheet:manage_logsheet_finances", pk=logsheet.pk)

        # Check towplane closeout data if there were flights
        # Use unfiltered queryset for validation
        if all_flights.exists():
            from logsheet.utils.towplane_utils import get_relevant_towplanes

            towplane_closeouts = logsheet.towplane_closeouts.all()
            missing_towplane_data = []

            # Get towplanes that require closeout using centralized logic
            # This ensures finalization validation matches UI behavior
            relevant_towplanes = get_relevant_towplanes(logsheet)
            relevant_towplane_ids = set(relevant_towplanes.values_list("pk", flat=True))

            for towplane in relevant_towplanes:
                closeout = towplane_closeouts.filter(towplane=towplane).first()

                if not closeout:
                    missing_towplane_data.append(
                        f"Missing closeout data for {towplane.n_number}"
                    )
                elif (
                    closeout.start_tach is None or closeout.end_tach is None
                ) and closeout.fuel_added is None:
                    missing_towplane_data.append(
                        f"Missing tach times or fuel data for {towplane.n_number}"
                    )

            if missing_towplane_data:
                for msg in missing_towplane_data:
                    messages.error(request, f"Cannot finalize. {msg}")
                return redirect("logsheet:manage", pk=logsheet.pk)

        # Lock in cost values
        # That means take the temporary values we calculated for the costs
        # and place them in these other variables that get perma-written to the database.
        # Use unfiltered queryset to lock in costs for all flights
        for flight in all_flights:
            if flight.tow_cost_actual is None:
                flight.tow_cost_actual = flight.tow_cost_calculated
            if flight.rental_cost_actual is None:
                flight.rental_cost_actual = flight.rental_cost_calculated
            flight.save()

        logsheet.finalized = True
        logsheet.save()

        RevisionLog.objects.create(
            logsheet=logsheet, revised_by=request.user, note="Logsheet finalized"
        )

        # Retire visiting pilot token when logsheet is finalized
        config = SiteConfiguration.objects.first()
        if config and config.visiting_pilot_enabled and config.visiting_pilot_token:
            config.retire_visiting_pilot_token()
            logger.info(
                f"Retired visiting pilot token for finalized logsheet {logsheet.pk}"
            )
        elif config is None:
            logger.warning(
                f"SiteConfiguration row is missing. Could not retire visiting pilot token for finalized logsheet {logsheet.pk}."
            )

        messages.success(
            request, "Logsheet has been finalized and all costs locked in."
        )
        return redirect("logsheet:manage", pk=logsheet.pk)

    # If the logsheet is finalized, prevent adding new flights
    # This check is done here to ensure that only authorized users can reopen finalized logbooks
    # If there is a "revise", then we'll remove the finalized status
    # and the logsheet can be returned to editing status.
    elif request.method == "POST":

        if "revise" in request.POST:
            from logsheet.utils.permissions import can_unfinalize_logsheet

            if can_unfinalize_logsheet(request.user, logsheet):
                logsheet.finalized = False
                logsheet.save()

                RevisionLog.objects.create(
                    logsheet=logsheet,
                    revised_by=request.user,
                    note="Logsheet returned to revised state",
                )

            else:
                return HttpResponseForbidden(
                    "You do not have permission to unfinalize this logsheet. "
                    "Only superusers, treasurers, webmasters, or the duty officer "
                    "who finalized it can unfinalize a logsheet."
                )
            return redirect("logsheet:manage", pk=logsheet.pk)

    revisions = (
        RevisionLog.objects.select_related("revised_by")
        .filter(logsheet=logsheet)
        .order_by("-revised_at")
    )

    flight_total = flights.count()
    flight_landed = flights.filter(
        launch_time__isnull=False, landing_time__isnull=False
    ).count()
    flight_flying = flights.filter(
        launch_time__isnull=False, landing_time__isnull=True
    ).count()
    flight_pending = flights.filter(launch_time__isnull=True).count()

    from logsheet.utils.permissions import can_edit_logsheet

    # Get glider reservations for this day (Issue #410)
    reservations = GliderReservation.get_reservations_for_date(logsheet.log_date)

    context = {
        "logsheet": logsheet,
        "flights": flights,
        "can_edit": can_edit_logsheet(request.user, logsheet),
        "revisions": revisions,
        "flight_total": flight_total,
        "flight_landed": flight_landed,
        "flight_flying": flight_flying,
        "flight_pending": flight_pending,
        "reservations": reservations,
    }
    # Find previous logsheet
    previous_logsheet = (
        Logsheet.objects.filter(log_date__lt=logsheet.log_date)
        .order_by("-log_date")
        .first()
    )

    # Find next logsheet
    next_logsheet = (
        Logsheet.objects.filter(log_date__gt=logsheet.log_date)
        .order_by("log_date")
        .first()
    )

    # Add them to your context
    context["previous_logsheet"] = previous_logsheet
    context["next_logsheet"] = next_logsheet

    # Add visiting pilot configuration with daily token
    config = SiteConfiguration.objects.first()
    if config and config.visiting_pilot_enabled:
        config.visiting_pilot_daily_token = config.get_or_create_daily_token()
    context["visiting_pilot_config"] = config

    return render(request, "logsheet/logsheet_manage.html", context)


#################################################
# view_flight
# This view handles the viewing of a specific flight within a logsheet.


@active_member_required
def view_flight(request, pk):
    flight = get_object_or_404(Flight, pk=pk)
    is_modal = request.headers.get("HX-Request") == "true"
    if is_modal:
        return render(
            request,
            "logsheet/flight_detail_content.html",
            {"flight": flight, "is_modal": True},
        )
    return render(
        request, "logsheet/flight_view.html", {"flight": flight, "is_modal": False}
    )


#################################################
# list_logsheets

# This view handles the listing of all logsheets.
#
# It allows active members to:
# - View a list of all logsheets, optionally filtered by a search query.
# - Search logsheets by log date, location, or the username of the creator.
#
# Args:
#    request (HttpRequest): The HTTP request object containing metadata about the request.
#
# Returns:
#    HttpResponse: Renders the logsheet list page with the filtered or unfiltered list of logsheets.


@active_member_required
def list_logsheets(request):
    query = request.GET.get("q", "")
    # Default to current year
    year = request.GET.get("year", str(timezone.now().year))
    logsheets = Logsheet.objects.all()

    if year:
        logsheets = logsheets.filter(log_date__year=year)

    if query:
        logsheets = logsheets.filter(
            Q(airfield__identifier__icontains=query)
            | Q(airfield__name__icontains=query)
            | Q(created_by__username__icontains=query)
            | Q(duty_officer__last_name__icontains=query)
            | Q(tow_pilot__last_name__icontains=query)
            | Q(duty_instructor__last_name__icontains=query)
        )
    # logsheets = logsheets.filter(airfield__identifier__icontains="VG55")

    logsheets = logsheets.order_by("-log_date", "-created_at")

    paginator = Paginator(logsheets, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    from django.db.models.functions import ExtractYear

    # Get years from existing logsheets
    db_years = set(
        Logsheet.objects.annotate(year=ExtractYear("log_date"))
        .values_list("year", flat=True)
        .distinct()
    )
    # Always include the current year so users can access historical logsheets
    # even when no logsheets exist for the current year (fixes issue #466)
    current_year = timezone.now().year
    db_years.add(current_year)
    available_years = sorted(db_years, reverse=True)

    from .forms import CreateLogsheetForm

    # If a log_date is provided in GET, use it to prepopulate from duty roster
    log_date = request.GET.get("log_date")
    form = None
    if log_date:
        try:
            from datetime import datetime

            parsed_date = datetime.strptime(log_date, "%Y-%m-%d").date()
            form = CreateLogsheetForm(duty_assignment_date=parsed_date)
        except (ValueError, TypeError) as e:
            logging.warning(f"Invalid date format provided: {log_date}, error: {e}")
            form = CreateLogsheetForm()
    else:
        form = CreateLogsheetForm()
    return render(
        request,
        "logsheet/logsheet_list.html",
        {
            "logsheets": page_obj.object_list,
            "query": query,
            "year": year,
            "page_obj": page_obj,
            "paginator": paginator,
            "available_years": available_years,
            "form": form,
        },
    )


#################################################
# edit_flight

# This view handles the editing of an existing flight within a specific logsheet.
#
# It allows active members to:
# - Edit the details of a flight associated with a logsheet.
# - Prevent edits if the logsheet is finalized (unless the user is authorized).
#
# Args:
#    request (HttpRequest): The HTTP request object containing metadata about the request.
#    logsheet_pk (int): The primary key of the logsheet containing the flight.
#    flight_pk (int): The primary key of the flight to edit.
#
# Returns:
#    HttpResponse: Renders the flight editing form for GET requests.
#    HttpResponseRedirect: Redirects to the logsheet management page upon successful update of the flight.


@active_member_required
def edit_flight(request, logsheet_pk, flight_pk):
    logsheet = get_object_or_404(Logsheet, pk=logsheet_pk)
    flight = get_object_or_404(Flight, pk=flight_pk, logsheet=logsheet)

    # Only allow edits if user has permission
    from logsheet.utils.permissions import can_edit_logsheet

    if not can_edit_logsheet(request.user, logsheet):
        return HttpResponseForbidden("This logsheet is finalized and cannot be edited.")

    # Build sorted glider list for template
    from logsheet.models import Glider

    gliders = Glider.objects.all()

    def glider_sort_key(g):
        group = (
            0
            if g.club_owned and g.is_active and g.seats == 2
            else (
                1
                if g.club_owned and g.is_active and g.seats == 1
                else 2 if not g.club_owned and g.is_active else 3
            )
        )
        if group == 2:
            # Private active: sort by contest number
            secondary = g.competition_number or ""
        else:
            secondary = g.n_number or g.competition_number or g.model or ""
        return (group, secondary)

    gliders_sorted = sorted(
        [g for g in gliders if not g.is_grounded], key=glider_sort_key
    )
    # Split into optgroup categories
    club_gliders = [g for g in gliders_sorted if g.club_owned and g.is_active]
    club_private = [g for g in gliders_sorted if not g.club_owned and g.is_active]
    inactive_gliders = [g for g in gliders_sorted if not g.is_active]

    if request.method == "POST":
        form = FlightForm(request.POST, instance=flight, logsheet=logsheet)
        if form.is_valid():
            form.save()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            messages.success(request, "Flight updated.")
            return redirect("logsheet:manage", pk=logsheet.pk)
        # AJAX: return form HTML with errors for modal
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return render(
                request,
                "logsheet/edit_flight_form.html",
                {
                    "form": form,
                    "flight": flight,
                    "logsheet": logsheet,
                    "club_gliders": club_gliders,
                    "club_private": club_private,
                    "inactive_gliders": inactive_gliders,
                },
                status=400,
            )
    else:
        form = FlightForm(instance=flight, logsheet=logsheet)

    return render(
        request,
        "logsheet/edit_flight_form.html",
        {
            "form": form,
            "flight": flight,
            "logsheet": logsheet,
            "club_gliders": club_gliders,
            "club_private": club_private,
            "inactive_gliders": inactive_gliders,
        },
    )


#################################################
# add_flight

# This view handles the addition of a new flight to a specific logsheet.
#
# It allows active members to:
# - Add a new flight to the logsheet if it is not finalized.
# - Display a form for entering flight details.
#
# Args:
#    request (HttpRequest): The HTTP request object containing metadata about the request.
#    logsheet_pk (int): The primary key of the logsheet to which the flight will be added.
#
# Returns:
#    HttpResponse: Renders the flight addition form for GET requests.
#    HttpResponseRedirect: Redirects to the logsheet management page upon successful addition of the flight.


@active_member_required
def add_flight(request, logsheet_pk):
    logsheet = get_object_or_404(Logsheet, pk=logsheet_pk)

    from logsheet.models import Glider

    gliders = Glider.objects.all()

    def glider_sort_key(g):
        group = (
            0
            if g.club_owned and g.is_active and g.seats == 2
            else (
                1
                if g.club_owned and g.is_active and g.seats == 1
                else 2 if not g.club_owned and g.is_active else 3
            )
        )
        if group == 2:
            secondary = g.competition_number or ""
        else:
            secondary = g.n_number or g.competition_number or g.model or ""
        return (group, secondary)

    gliders_sorted = sorted(
        [g for g in gliders if not g.is_grounded], key=glider_sort_key
    )
    club_gliders = [g for g in gliders_sorted if g.club_owned and g.is_active]
    club_private = [g for g in gliders_sorted if not g.club_owned and g.is_active]
    inactive_gliders = [g for g in gliders_sorted if not g.is_active]

    if request.method == "POST":
        form = FlightForm(request.POST, logsheet=logsheet)
        if form.is_valid():
            flight = form.save(commit=False)
            flight.logsheet = logsheet
            flight.save()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            return redirect("logsheet:manage", pk=logsheet.pk)
        # AJAX: return form HTML with errors for modal
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return render(
                request,
                "logsheet/edit_flight_form.html",
                {
                    "form": form,
                    "logsheet": logsheet,
                    "mode": "add",
                    "club_gliders": club_gliders,
                    "club_private": club_private,
                    "inactive_gliders": inactive_gliders,
                },
                status=400,
            )
    else:
        initial = {}
        if logsheet.tow_pilot_id:
            initial["tow_pilot"] = logsheet.tow_pilot_id
        if logsheet.default_towplane_id:
            initial["towplane"] = logsheet.default_towplane_id
        form = FlightForm(initial=initial)

    return render(
        request,
        "logsheet/edit_flight_form.html",
        {
            "form": form,
            "logsheet": logsheet,
            "mode": "add",
            "club_gliders": club_gliders,
            "club_private": club_private,
            "inactive_gliders": inactive_gliders,
        },
    )


#################################################
# delete_flight

# This view handles the deletion of a flight from a specific logsheet.
#
# Decorators:
# - @require_POST: Ensures that this view can only be accessed via a POST request, preventing accidental deletions through GET requests.
# - @active_member_required: Restricts access to active members only, ensuring that only authorized users can perform this action.
#
# Functionality:
# - Deletes a flight associated with a logsheet if the logsheet is not finalized.
# - Prevents deletion of flights from finalized logsheets to maintain data integrity.
# - Displays a success message upon successful deletion.
#
# Args:
#    request (HttpRequest): The HTTP request object containing metadata about the request.
#    logsheet_pk (int): The primary key of the logsheet containing the flight.
#    flight_pk (int): The primary key of the flight to delete.
#
# Returns:
#    HttpResponseForbidden: If the logsheet is finalized, deletion is forbidden.
#    HttpResponseRedirect: Redirects to the logsheet management page after successful deletion.


@require_POST
@active_member_required
def delete_flight(request, logsheet_pk, flight_pk):
    logsheet = get_object_or_404(Logsheet, pk=logsheet_pk)
    flight = get_object_or_404(Flight, pk=flight_pk, logsheet=logsheet)

    if logsheet.finalized:
        return HttpResponseForbidden("Cannot delete a finalized flight.")

    flight.delete()
    messages.success(request, "Flight deleted.")
    return redirect("logsheet:manage", pk=logsheet_pk)


#################################################
# manage_logsheet_finances
#
# Purpose:
# Handles the financial management of a specific logsheet.
# Allows active members to:
# - View detailed breakdowns of flight costs.
# - Display actual costs if finalized, or calculated costs if pending.
# - Summarize financial data per pilot: flights, tow costs, rental costs, total costs.
# - Calculate and distribute charges per member, accounting for split-payment arrangements.
# - Update payment methods and notes for each responsible member.
# - Finalize the logsheet, locking in all costs and validating payment information.
#
# Internal Methods:
# - flight_costs(flight): Returns tow, rental, and total costs depending on finalization state.
#
# POST Handling:
# - "Finalize" request:
#   - Verifies all responsible members have payment methods.
#   - Locks in flight costs.
#   - Marks the logsheet as finalized.
# - "Update" request:
#   - Saves updated payment methods and notes per member.
#
# Args:
# - request (HttpRequest): The incoming HTTP request (GET or POST).
# - pk (int): Primary key of the logsheet to manage.
#
# Returns:
# - HttpResponse: Renders the financial management page with cost breakdowns, summaries, and member charges.
#################################################


@active_member_required
def manage_logsheet_finances(request, pk):
    # For split modal: all members, grouped by active/non-active
    from members.models import Member

    # Use centralized helper for active membership status filtering
    from members.utils.membership import get_active_membership_statuses

    active_status_names = get_active_membership_statuses()
    active_members = Member.objects.filter(
        membership_status__in=active_status_names
    ).order_by("last_name", "first_name")
    inactive_members = Member.objects.exclude(
        membership_status__in=active_status_names
    ).order_by("last_name", "first_name")

    logsheet = get_object_or_404(Logsheet, pk=pk)

    # OPTIMIZATION: Use select_related to avoid N+1 queries for pilot, glider, towplane
    flights = logsheet.flights.select_related(
        "pilot", "instructor", "glider", "towplane", "split_with"
    ).all()

    # Get towplane rental costs for this logsheet
    # OPTIMIZATION: Already optimized with select_related
    towplane_closeouts = logsheet.towplane_closeouts.select_related(
        "towplane", "rental_charged_to"
    ).all()

    # OPTIMIZATION: Cache SiteConfiguration to avoid N+1 queries when processing retrieve flights
    # (Issue #66 - retrieve flights may query SiteConfiguration to check waiver settings)
    from siteconfig.models import SiteConfiguration

    site_config = SiteConfiguration.objects.first()

    # Pre-cache config on all Flight instances to avoid repeated DB lookups
    for flight in flights:
        flight._site_config_cache = site_config

    # Use locked-in values if finalized, else use capped property
    def flight_costs(f):
        return {
            "tow": f.tow_cost_actual if logsheet.finalized else f.tow_cost_calculated,
            "rental": f.rental_cost_actual if logsheet.finalized else f.rental_cost,
            "total": (
                f.total_cost
                if logsheet.finalized
                else ((f.tow_cost_calculated or 0) + (f.rental_cost or 0))
            ),
        }

    flight_data = []
    total_tow = total_rental = total_towplane_rental = total_sum = 0

    for flight in flights:
        costs = flight_costs(flight)
        flight_data.append((flight, costs))
        total_tow += costs["tow"] or 0
        total_rental += costs["rental"] or 0
        total_sum += costs["total"] or 0

    # Add towplane rental costs
    towplane_data = []
    for closeout in towplane_closeouts:
        rental_cost = closeout.rental_cost or 0
        towplane_data.append((closeout, rental_cost))
        total_towplane_rental += rental_cost

    total_sum += total_towplane_rental

    from collections import defaultdict
    from decimal import Decimal

    from .models import LogsheetPayment

    # Summary per pilot
    pilot_summary = defaultdict(lambda: {"count": 0, "tow": 0, "rental": 0, "total": 0})
    for flight, costs in flight_data:
        pilot = flight.pilot
        if pilot:
            summary = pilot_summary[pilot]
            summary["count"] += 1
            summary["tow"] += costs["tow"] or 0
            summary["rental"] += costs["rental"] or 0
            summary["total"] += costs["total"] or 0

    # Who pays what?
    member_charges = defaultdict(
        lambda: {
            "tow": Decimal("0.00"),
            "rental": Decimal("0.00"),
            "towplane_rental": Decimal("0.00"),
            "misc_charges": Decimal("0.00"),
            "total": Decimal("0.00"),
        }
    )
    for flight, costs in flight_data:
        pilot = flight.pilot
        partner = flight.split_with
        split_type = flight.split_type
        tow = costs["tow"] or Decimal("0.00")
        rental = costs["rental"] or Decimal("0.00")
        total = costs["total"] or Decimal("0.00")

        if partner and split_type:
            if split_type == "even":
                # For 50/50 splits, divide both tow and rental costs equally
                # IMPORTANT: This logic is duplicated in manage_logsheet_finances.html (JavaScript)
                # If this calculation changes, update BOTH locations!
                half_tow = tow / 2
                half_rental = rental / 2
                member_charges[pilot]["tow"] += half_tow
                member_charges[pilot]["rental"] += half_rental
                member_charges[partner]["tow"] += half_tow
                member_charges[partner]["rental"] += half_rental
            elif split_type == "tow":
                member_charges[pilot]["rental"] += rental
                member_charges[partner]["tow"] += tow
            elif split_type == "rental":
                member_charges[pilot]["tow"] += tow
                member_charges[partner]["rental"] += rental
            elif split_type == "full":
                member_charges[partner]["tow"] += tow
                member_charges[partner]["rental"] += rental
        else:
            if pilot:
                member_charges[pilot]["tow"] += tow
                member_charges[pilot]["rental"] += rental

    # Add towplane rental costs to member charges
    for closeout, rental_cost in towplane_data:
        if closeout.rental_charged_to and rental_cost > 0:
            member_charges[closeout.rental_charged_to]["towplane_rental"] += Decimal(
                str(rental_cost)
            )

    # Add miscellaneous charges (Issue #66, #413)
    misc_charges_qs = MemberCharge.objects.filter(logsheet=logsheet).select_related(
        "member", "chargeable_item"
    )
    misc_charges_data = list(misc_charges_qs)  # Store for template display
    total_misc_charges = Decimal("0.00")
    for charge in misc_charges_data:
        member_charges[charge.member]["misc_charges"] += charge.total_price
        total_misc_charges += charge.total_price

    # Add combined totals
    for summary in member_charges.values():
        summary["total"] = (
            summary["tow"]
            + summary["rental"]
            + summary["towplane_rental"]
            + summary["misc_charges"]
        )

    # OPTIMIZATION: Bulk fetch existing payments to avoid N+1 queries
    existing_payments = {
        payment.member_id: payment
        for payment in LogsheetPayment.objects.filter(
            logsheet=logsheet, member__in=member_charges.keys()
        ).select_related("member")
    }

    # Create missing payments in bulk
    missing_payment_members = [
        member for member in member_charges.keys() if member.id not in existing_payments
    ]
    if missing_payment_members:
        new_payments = LogsheetPayment.objects.bulk_create(
            [
                LogsheetPayment(logsheet=logsheet, member=member)
                for member in missing_payment_members
            ]
        )
        # Add new payments to existing_payments dict
        for payment in new_payments:
            existing_payments[payment.member_id] = payment

    member_payment_data = []
    for member in member_charges:
        summary = member_charges[member]
        payment = existing_payments.get(member.id)
        member_payment_data.append(
            {
                "member": member,
                "amount": summary["total"],
                "payment_method": payment.payment_method if payment else None,
                "note": payment.note if payment else "",
            }
        )
    if request.method == "POST":
        if "finalize" in request.POST:
            # Check that all responsible members have a payment method
            responsible_members = set()

            for flight in flights:
                pilot = flight.pilot
                partner = flight.split_with
                split = flight.split_type

                if partner and split == "full":
                    responsible_members.add(partner)
                elif partner and split in ("even", "tow", "rental"):
                    responsible_members.update([pilot, partner])
                elif pilot:
                    responsible_members.add(pilot)

            # Add members responsible for towplane rental charges
            for closeout in towplane_closeouts:
                if closeout.rental_charged_to and closeout.rental_cost:
                    responsible_members.add(closeout.rental_charged_to)

            # Add members responsible for miscellaneous charges (Issue #66, #413)
            for charge in misc_charges_data:
                responsible_members.add(charge.member)

            missing = []
            for member in responsible_members:
                try:
                    payment = LogsheetPayment.objects.get(
                        logsheet=logsheet, member=member
                    )
                    if not payment.payment_method:
                        missing.append(member.full_display_name)
                except LogsheetPayment.DoesNotExist:
                    missing.append(member.full_display_name)

            if missing:
                messages.error(
                    request,
                    "Cannot finalize. Missing payment method for: "
                    + ", ".join(missing),
                )
                return redirect("logsheet:manage_logsheet_finances", pk=logsheet.pk)

            # Lock in costs
            for flight in flights:
                if flight.tow_cost_actual is None:
                    flight.tow_cost_actual = flight.tow_cost_calculated
                if flight.rental_cost_actual is None:
                    flight.rental_cost_actual = flight.rental_cost_calculated
                flight.save()

            logsheet.finalized = True
            logsheet.save()
            messages.success(
                request, "Logsheet has been finalized and all costs locked in."
            )
            return redirect("logsheet:manage", pk=logsheet.pk)

        else:
            # OPTIMIZATION: Bulk update payments to avoid N individual saves
            payment_updates = []
            for entry in member_payment_data:
                member = entry["member"]
                payment = existing_payments.get(member.id)
                if payment:
                    payment_method = request.POST.get(f"payment_method_{member.id}")
                    note = request.POST.get(f"note_{member.id}", "").strip()
                    payment.payment_method = payment_method or None
                    payment.note = note
                    payment_updates.append(payment)

            # Bulk update all payments
            if payment_updates:
                LogsheetPayment.objects.bulk_update(
                    payment_updates, ["payment_method", "note"]
                )

            messages.success(request, "Payment methods updated.")
            return redirect("logsheet:manage", pk=logsheet.pk)

    # Sort pilot_summary by pilot last name
    pilot_summary_sorted = sorted(
        pilot_summary.items(),
        key=lambda item: (item[0].last_name or "", item[0].first_name or ""),
    )
    # Sort member_charges by member last name
    member_charges_sorted = sorted(
        member_charges.items(),
        key=lambda item: (item[0].last_name or "", item[0].first_name or ""),
    )
    # Sort member_payment_data by member last name
    member_payment_data_sorted = sorted(
        member_payment_data,
        key=lambda row: (
            getattr(row["member"], "last_name", ""),
            getattr(row["member"], "first_name", ""),
        ),
    )
    # Sort flight_data by pilot last name (handle None pilot)
    flight_data_sorted = sorted(
        flight_data,
        key=lambda fc: (
            (fc[0].pilot.last_name if fc[0].pilot else ""),
            (fc[0].pilot.first_name if fc[0].pilot else ""),
        ),
    )

    # Check if towplane rentals are enabled (cache config query)
    config = SiteConfiguration.objects.first()
    rental_enabled = config.allow_towplane_rental if config else False

    context = {
        "logsheet": logsheet,
        "flight_data_sorted": flight_data_sorted,
        "flight_data": flight_data,  # Added for test compatibility
        "towplane_data": towplane_data,
        "total_tow": total_tow,
        "total_rental": total_rental,
        "total_towplane_rental": total_towplane_rental,
        "total_misc_charges": total_misc_charges,
        "total_sum": total_sum + total_misc_charges,
        "pilot_summary_sorted": pilot_summary_sorted,
        "member_charges_sorted": member_charges_sorted,
        "member_payment_data_sorted": member_payment_data_sorted,
        "misc_charges_data": misc_charges_data,
        "active_members": active_members,
        "inactive_members": inactive_members,
        "towplane_rental_enabled": rental_enabled,
    }

    return render(request, "logsheet/manage_logsheet_finances.html", context)


#################################################
# edit_logsheet_closeout
#
# Purpose:
# Allows active members to edit the closeout information for a specific logsheet.
# Updates include final duty crew assignments, towplane closeouts, and maintenance issues.
# Editing is blocked if the logsheet is finalized, unless the user is authorized.
#
# Behavior:
# - Ensures that each towplane used on the logsheet has a TowplaneCloseout record.
# - Displays forms for:
#   - Logsheet closeout information (essay, end-of-day notes, etc.)
#   - Duty crew updates (Duty Officer, Assistant, Instructor, etc.)
#   - Towplane closeouts (tach times, maintenance notes)
# - Processes POST submissions for all three form sections.
# - Saves updates and redirects to the logsheet management page on success.
#
# Args:
# - request (HttpRequest): The incoming HTTP request (GET or POST).
# - pk (int): Primary key of the logsheet to edit.
#
# Returns:
# - HttpResponse: Renders the closeout editing form page or redirects after successful save.
#################################################


@active_member_required
def edit_logsheet_closeout(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    closeout, _ = LogsheetCloseout.objects.get_or_create(logsheet=logsheet)
    maintenance_issues = MaintenanceIssue.objects.filter(
        logsheet=logsheet
    ).select_related("reported_by", "glider", "towplane")

    from logsheet.utils.permissions import can_edit_logsheet

    if not can_edit_logsheet(request.user, logsheet):
        return HttpResponseForbidden("This logsheet is finalized and cannot be edited.")

    # Get all relevant towplanes and create closeouts
    from logsheet.utils.towplane_utils import get_relevant_towplanes

    relevant_towplanes = get_relevant_towplanes(logsheet)
    # Materialize towplane IDs once to avoid redundant DB queries
    relevant_towplane_ids = list(relevant_towplanes.values_list("pk", flat=True))

    for towplane_id in relevant_towplane_ids:
        TowplaneCloseout.objects.get_or_create(
            logsheet=logsheet, towplane_id=towplane_id
        )

    # Build formset for towplane closeouts - include all closeouts for this logsheet
    # This keeps any existing (possibly stale) closeouts visible so they can be reviewed and adjusted
    # Run cleanup_virtual_towplane_closeouts management command to remove truly stale virtual towplane closeouts
    queryset = TowplaneCloseout.objects.filter(logsheet=logsheet)
    formset_class = TowplaneCloseoutFormSet
    formset = formset_class(queryset=queryset)

    if request.method == "POST":
        form = LogsheetCloseoutForm(request.POST, instance=closeout)
        duty_form = LogsheetDutyCrewForm(request.POST, instance=logsheet)
        formset = formset_class(request.POST, queryset=queryset)

        if form.is_valid() and duty_form.is_valid() and formset.is_valid():
            form.save()
            duty_form.save()
            formset.save()

            messages.success(request, "Closeout, duty crew, and towplane info updated.")
            return redirect("logsheet:manage", pk=logsheet.pk)

    else:
        form = LogsheetCloseoutForm(instance=closeout)
        duty_form = LogsheetDutyCrewForm(instance=logsheet)

    # Get towplanes available for manual addition (not already in closeouts)
    existing_closeout_towplanes = TowplaneCloseout.objects.filter(
        logsheet=logsheet
    ).values_list("towplane_id", flat=True)
    available_towplanes = (
        Towplane.objects.filter(is_active=True)
        .exclude(id__in=existing_closeout_towplanes)
        .order_by("n_number")
    )

    # Check if towplane rentals are enabled for UI display
    config = SiteConfiguration.objects.first()
    towplane_rental_enabled = config.allow_towplane_rental if config else False

    # Build tow pilot summary for this logsheet's flights
    # Shows tow count per pilot, per towplane, with total feet towed
    tow_pilot_summary = (
        Flight.objects.filter(logsheet=logsheet, tow_pilot__isnull=False)
        .values(
            "tow_pilot__first_name",
            "tow_pilot__last_name",
            "tow_pilot__id",
            "towplane__n_number",
        )
        .annotate(
            tow_count=Count("id"),
            total_feet=Sum("release_altitude"),
        )
        .order_by(
            Coalesce("tow_pilot__last_name", Value("")),
            Coalesce("tow_pilot__first_name", Value("")),
            "towplane__n_number",
        )
    )

    # Group by tow pilot for easier template rendering
    # Use pilot_id + name as key to prevent grouping multiple unnamed pilots together
    tow_pilots_data = {}
    for row in tow_pilot_summary:
        # Safely handle None/empty first_name or last_name
        pilot_name = " ".join(
            filter(
                None,
                [
                    (row.get("tow_pilot__first_name") or "").strip(),
                    (row.get("tow_pilot__last_name") or "").strip(),
                ],
            )
        )
        if not pilot_name:
            pilot_name = "Unknown Pilot"

        # Use pilot_id + name as unique key to prevent grouping unnamed pilots
        pilot_key = f"{row['tow_pilot__id']}:{pilot_name}"

        if pilot_key not in tow_pilots_data:
            tow_pilots_data[pilot_key] = {
                "name": pilot_name,
                "towplanes": [],
                "total_tows": 0,
                "total_feet": 0,
            }
        tow_pilots_data[pilot_key]["towplanes"].append(
            {
                "n_number": row["towplane__n_number"] or "Unknown",
                "tow_count": row["tow_count"],
                "total_feet": row["total_feet"] or 0,
            }
        )
        tow_pilots_data[pilot_key]["total_tows"] += row["tow_count"]
        tow_pilots_data[pilot_key]["total_feet"] += row["total_feet"] or 0

    return render(
        request,
        "logsheet/edit_closeout_form.html",
        {
            "logsheet": logsheet,
            "form": form,
            "duty_form": duty_form,
            "formset": formset,
            "gliders": Glider.objects.filter(club_owned=True, is_active=True).order_by(
                "n_number"
            ),
            "towplanes": Towplane.objects.filter(is_active=True).order_by("n_number"),
            "maintenance_issues": maintenance_issues,
            "available_towplanes": available_towplanes,
            "towplane_rental_enabled": towplane_rental_enabled,
            "tow_pilots_data": tow_pilots_data,
        },
    )


@active_member_required
def add_towplane_closeout(request, pk):
    """Add a towplane closeout manually for rental or other non-towing usage."""
    logsheet = get_object_or_404(Logsheet, pk=pk)

    from logsheet.utils.permissions import can_edit_logsheet

    if not can_edit_logsheet(request.user, logsheet):
        return HttpResponseForbidden("This logsheet is finalized and cannot be edited.")

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    towplane_id = request.POST.get("towplane")
    if towplane_id:
        towplane = get_object_or_404(Towplane, pk=towplane_id, is_active=True)

        # Create the towplane closeout if it doesn't exist
        closeout, created = TowplaneCloseout.objects.get_or_create(
            logsheet=logsheet, towplane=towplane
        )

        if created:
            messages.success(
                request,
                f"Added {towplane.name} ({towplane.n_number}) to closeout form. "
                f"You can now enter rental hours and other details.",
            )
        else:
            messages.info(
                request,
                f"{towplane.name} ({towplane.n_number}) is already in the closeout form.",
            )
    else:
        messages.error(request, "Please select a towplane to add.")

    return redirect("logsheet:edit_logsheet_closeout", pk=logsheet.pk)


#################################################
# view_logsheet_closeout
#
# Purpose:
# Displays the closeout summary for a specific logsheet in a read-only format.
# Provides details on duty crew assignments, towplane closeouts, and maintenance issues.
#
# Behavior:
# - Fetches the associated LogsheetCloseout if it exists.
# - Retrieves all TowplaneCloseout records linked to the logsheet.
# - Retrieves all MaintenanceIssue records linked to the logsheet.
# - Renders a summary page showing the final state of the day's operations.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
# - pk (int): Primary key of the logsheet to view.
#
# Returns:
# - HttpResponse: Renders the closeout summary page.
#################################################


@active_member_required
def view_logsheet_closeout(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    maintenance_issues = MaintenanceIssue.objects.filter(
        logsheet=logsheet
    ).select_related("reported_by", "glider", "towplane")
    closeout = getattr(logsheet, "closeout", None)
    towplanes = logsheet.towplane_closeouts.select_related(
        "towplane", "rental_charged_to"
    ).all()

    # Check if towplane rentals are enabled for conditional display
    config = SiteConfiguration.objects.first()
    towplane_rental_enabled = config.allow_towplane_rental if config else False

    return render(
        request,
        "logsheet/view_closeout.html",
        {
            "logsheet": logsheet,
            "closeout": closeout,
            "towplanes": towplanes,
            "maintenance_issues": maintenance_issues,
            "towplane_rental_enabled": towplane_rental_enabled,
        },
    )


#################################################
# add_maintenance_issue
#
# Purpose:
# Allows active members to submit a new maintenance issue during logsheet closeout.
# Issues must be associated with either a glider or a towplane.
#
# Behavior:
# - Accepts POST data from the MaintenanceIssueForm.
# - Validates the form and ensures a glider or towplane is selected.
# - Assigns the reporting member and associates the issue with the current logsheet.
# - Saves the issue and displays success or error messages.
# - Redirects back to the logsheet closeout editing page.
#
# Args:
# - request (HttpRequest): The incoming HTTP POST request containing maintenance issue data.
# - logsheet_id (int): Primary key of the logsheet to associate the issue with.
#
# Returns:
# - HttpResponseRedirect: Redirects to the edit closeout page after submission attempt.
#################################################


@require_POST
@active_member_required
def add_maintenance_issue(request, logsheet_id):
    logsheet = get_object_or_404(Logsheet, pk=logsheet_id)
    form = MaintenanceIssueForm(request.POST)

    # Support AJAX requests to avoid losing form data
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if form.is_valid():
        issue = form.save(commit=False)
        issue.reported_by = request.user
        issue.logsheet = logsheet
        issue.save()

        if is_ajax:
            return JsonResponse(
                {
                    "success": True,
                    "message": "Maintenance issue submitted successfully.",
                    "issue": {
                        "id": issue.id,
                        "glider": str(issue.glider) if issue.glider else None,
                        "towplane": str(issue.towplane) if issue.towplane else None,
                        "description": issue.description,
                        "grounded": issue.grounded,
                        "reported_by": issue.reported_by.full_display_name,
                    },
                }
            )
        messages.success(request, "Maintenance issue submitted successfully.")
    else:
        if is_ajax:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Form validation failed.",
                    "errors": form.errors.get_json_data(),
                },
                status=400,
            )
        messages.error(request, "Failed to submit maintenance issue.")

    return redirect("logsheet:edit_logsheet_closeout", pk=logsheet.id)


#################################################
# add_maintenance_issue_standalone
#
# Purpose:
# Allows active members to submit a new maintenance issue from the maintenance
# issues page (not tied to a specific logsheet).
#
# Behavior:
# - Accepts POST data from the MaintenanceIssueForm.
# - Validates the form and ensures a glider or towplane is selected.
# - Assigns the reporting member (no logsheet association).
# - Saves the issue and displays success or error messages.
# - Redirects back to the maintenance issues page.
#
# Args:
# - request (HttpRequest): The incoming HTTP POST request containing maintenance issue data.
#
# Returns:
# - HttpResponseRedirect: Redirects to the maintenance issues page after submission.
#################################################


@require_POST
@active_member_required
def add_maintenance_issue_standalone(request):
    form = MaintenanceIssueForm(request.POST)

    if form.is_valid():
        issue = form.save(commit=False)
        issue.reported_by = request.user
        # No logsheet association for standalone submissions
        issue.save()
        messages.success(request, "Maintenance issue submitted successfully.")
    else:
        messages.error(
            request, "Failed to submit maintenance issue. Please check the form."
        )

    return redirect("logsheet:maintenance_issues")


#################################################
# equipment_list
#
# Purpose:
# Displays a list of active, club-owned gliders and towplanes.
# Intended for member reference during flight operations and equipment checks.
#
# Behavior:
# - Fetches all active, club-owned gliders, sorted by N-number.
# - Fetches all active, club-owned towplanes, sorted by N-number.
# - Renders the equipment list page with separate sections for gliders and towplanes.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
#
# Returns:
# - HttpResponse: Renders the equipment list page.
#################################################


@active_member_required
def equipment_list(request):
    gliders = Glider.objects.filter(is_active=True, club_owned=True).order_by(
        "n_number"
    )
    towplanes = Towplane.objects.filter(is_active=True, club_owned=True).order_by(
        "n_number"
    )
    return render(
        request,
        "logsheet/equipment_list.html",
        {
            "gliders": gliders,
            "towplanes": towplanes,
        },
    )


#################################################
# maintenance_issues
#
# Purpose:
# Displays a list of all unresolved (open) maintenance issues.
# Intended for duty officers and maintenance personnel to review outstanding problems.
#
# Behavior:
# - Fetches all unresolved MaintenanceIssue records.
# - Prefetches related glider and towplane information for display efficiency.
# - Renders the maintenance issue list page.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
#
# Returns:
# - HttpResponse: Renders the maintenance issues list page.
#################################################


@active_member_required
def maintenance_issues(request):
    open_issues = MaintenanceIssue.objects.filter(resolved=False).select_related(
        "glider", "towplane"
    )
    # Get active club-owned aircraft for the "Add Issue" modal
    gliders = Glider.objects.filter(club_owned=True, is_active=True).order_by(
        "n_number"
    )
    towplanes = Towplane.objects.filter(club_owned=True, is_active=True).order_by(
        "n_number"
    )

    return render(
        request,
        "logsheet/maintenance_list.html",
        {
            "open_issues": open_issues,
            "gliders": gliders,
            "towplanes": towplanes,
        },
    )


#################################################
# maintenance_log
#
# Purpose:
# Displays a running log of all maintenance issues (both open and resolved)
# for all aircraft. This provides a historical view of all maintenance activity.
#
# Behavior:
# - Fetches all maintenance issues ordered by report_date (newest first).
# - Displays issues in a flat chronological list for all aircraft.
# - Shows both open and resolved issues with their full history.
# - Optionally filters by aircraft if specified in query params.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
#
# Returns:
# - HttpResponse: Renders the maintenance log page.
#################################################


@active_member_required
def maintenance_log(request):
    # Get filter parameters
    aircraft_type = request.GET.get("type")  # 'glider' or 'towplane'
    aircraft_id_str = request.GET.get("aircraft_id")

    # Base queryset with all issues
    issues = MaintenanceIssue.objects.select_related(
        "glider", "towplane", "reported_by", "resolved_by"
    ).order_by("-report_date", "-id")

    # Convert and apply filters if specified
    aircraft_id_int = None
    if aircraft_type == "glider" and aircraft_id_str:
        try:
            aircraft_id_int = int(aircraft_id_str)
            issues = issues.filter(glider_id=aircraft_id_int)
        except (ValueError, TypeError):
            aircraft_id_int = None  # Invalid ID, ignore filter
    elif aircraft_type == "towplane" and aircraft_id_str:
        try:
            aircraft_id_int = int(aircraft_id_str)
            issues = issues.filter(towplane_id=aircraft_id_int)
        except (ValueError, TypeError):
            aircraft_id_int = None  # Invalid ID, ignore filter

    # Get all aircraft for filter dropdowns
    gliders = Glider.objects.filter(is_active=True).order_by("n_number")
    towplanes = Towplane.objects.filter(is_active=True).order_by("n_number")

    # Calculate statistics using ORM aggregation to avoid loading all issues into memory
    stats = issues.aggregate(
        total=Count("id"),
        open_count=Count("id", filter=Q(resolved=False)),
        resolved_count=Count("id", filter=Q(resolved=True)),
        grounded=Count("id", filter=Q(resolved=False, grounded=True)),
    )

    return render(
        request,
        "logsheet/maintenance_log.html",
        {
            "issues": issues,
            "gliders": gliders,
            "towplanes": towplanes,
            "selected_type": aircraft_type,
            "selected_aircraft_id": aircraft_id_int,
            "total_issues": stats["total"],
            "open_issues_count": stats["open_count"],
            "resolved_issues_count": stats["resolved_count"],
            "grounded_count": stats["grounded"],
        },
    )


#################################################
# mark_issue_resolved
#
# Purpose:
# Allows authorized Aircraft Meisters to mark maintenance issues as resolved.
# Ensures only the assigned Meister for a glider or towplane can resolve its issues.
#
# Behavior:
# - Checks whether the logged-in member is an Aircraft Meister for the associated glider or towplane.
# - If authorized, marks the maintenance issue as resolved and clears any grounding status.
# - Displays success or error messages based on the outcome.
# - Redirects back to the maintenance issues list after completion.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
# - issue_id (int): Primary key of the MaintenanceIssue to resolve.
#
# Returns:
# - HttpResponseRedirect: Redirects to the maintenance issues list after attempting to resolve.
#################################################


@active_member_required
def mark_issue_resolved(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, pk=issue_id)

    # Check if this user is the AircraftMeister for the aircraft
    member = request.user
    if issue.glider:
        if not AircraftMeister.objects.filter(
            glider=issue.glider, meister=member
        ).exists():
            messages.error(
                request, "You are not authorized to resolve issues for this glider."
            )
            return redirect("logsheet:maintenance_issues")
    elif issue.towplane:
        if not AircraftMeister.objects.filter(
            towplane=issue.towplane, meister=member
        ).exists():
            messages.error(
                request, "You are not authorized to resolve issues for this towplane."
            )
            return redirect("logsheet:maintenance_issues")

    issue.resolved = True
    issue.grounded = False  # in case it was grounded
    issue.save()

    messages.success(request, "Maintenance issue marked as resolved.")
    return redirect("logsheet:maintenance_issues")


#################################################
# resolve_maintenance_modal
#
# Purpose:
# Renders a modal window for resolving a specific maintenance issue.
# Allows members to view issue details and enter resolution notes via a popup form.
#
# Behavior:
# - Fetches the targeted MaintenanceIssue by ID.
# - Renders the maintenance_resolve_modal.html template with the issue details.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
# - issue_id (int): Primary key of the MaintenanceIssue to resolve.
#
# Returns:
# - HttpResponse: Renders the modal popup template for maintenance resolution.
#################################################


@active_member_required
def resolve_maintenance_modal(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, id=issue_id)

    return render(request, "logsheet/maintenance_resolve_modal.html", {"issue": issue})


#################################################
# resolve_maintenance_issue
#
# Purpose:
# Processes a POST request to mark a maintenance issue as resolved.
# Allows members to add optional resolution notes during the resolution process.
#
# Behavior:
# - Fetches the MaintenanceIssue by ID.
# - (Permission checks assumed same as modal trigger; only active members allowed.)
# - Records the resolving member and the resolution date.
# - Saves resolution notes if provided, or applies a default note if none exist.
# - Marks the issue as resolved and saves the update.
# - Returns a JSON response signaling the frontend to reload.
#
# Args:
# - request (HttpRequest): The incoming HTTP POST request containing resolution notes.
# - issue_id (int): Primary key of the MaintenanceIssue to resolve.
#
# Returns:
# - JsonResponse: {"reload": True} to trigger a page or modal reload on the client side.
#################################################


@require_POST
@active_member_required
def resolve_maintenance_issue(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, id=issue_id)

    # (same permission checks as before)

    notes = request.POST.get("notes", "").strip()

    issue.resolved = True
    issue.resolved_by = request.user
    issue.resolved_date = timezone.now().date()
    if notes:
        issue.resolution_notes = notes
    elif not issue.resolution_notes:
        issue.resolution_notes = "Resolved via equipment page."

    issue.save()

    return JsonResponse({"reload": True})


#################################################
# maintenance_resolve_modal
#
# Purpose:
# Renders a modal window to display a maintenance issue's details for resolution.
# Used to present issue information and collect resolution notes from authorized users.
#
# Behavior:
# - Fetches the MaintenanceIssue by ID.
# - Renders the maintenance_resolve_modal.html template with the issue context.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
# - issue_id (int): Primary key of the MaintenanceIssue to resolve.
#
# Returns:
# - HttpResponse: Renders the maintenance resolution modal popup.
#################################################


@active_member_required
def maintenance_resolve_modal(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, id=issue_id)
    return render(request, "logsheet/maintenance_resolve_modal.html", {"issue": issue})


#################################################
# maintenance_mark_resolved
#
# Purpose:
# Processes a POST request to mark a maintenance issue as resolved, requiring resolution notes.
# Ensures that only authorized users can resolve the issue and enforces submission of notes.
#
# Behavior:
# - Fetches the MaintenanceIssue by ID.
# - Verifies that the user is authorized to resolve the issue using `can_be_resolved_by()`.
# - If unauthorized, returns an HTTP 403 Forbidden response.
# - Requires non-empty resolution notes; if missing, returns a 400 Bad Request JSON error.
# - Records the resolving user, date, and resolution notes.
# - Saves the issue and returns a JSON response to trigger frontend reload.
#
# Args:
# - request (HttpRequest): The incoming HTTP POST request.
# - issue_id (int): Primary key of the MaintenanceIssue to resolve.
#
# Returns:
# - JsonResponse:
#     - {"reload": True} if successfully resolved.
#     - {"error": "..."} with HTTP 400 if notes are missing.
# - HttpResponseForbidden: If the user is not authorized to resolve the issue.
#################################################


@require_POST
@active_member_required
def maintenance_mark_resolved(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, id=issue_id)

    if not issue.can_be_resolved_by(request.user):
        return HttpResponseForbidden("You're not allowed to resolve this issue.")

    resolution_notes = request.POST.get("resolution_notes", "").strip()
    if not resolution_notes:
        return JsonResponse({"error": "Resolution notes are required."}, status=400)

    issue.resolved = True
    issue.resolved_by = request.user
    issue.resolved_date = now().date()
    issue.resolution_notes = resolution_notes
    issue.save()

    return JsonResponse({"reload": True})


#################################################
# maintenance_deadlines
#
# Purpose:
# Displays a sorted list of upcoming maintenance deadlines for gliders and towplanes.
# Highlights overdue deadlines, deadlines due within 30 days, and future deadlines beyond 30 days.
#
# Behavior:
# - Fetches all MaintenanceDeadline records.
# - Sorts deadlines into three groups:
#   - Overdue (due before today)
#   - Due soon (within the next 30 days)
#   - Due later (more than 30 days out)
# - Within each group, sorts by due date ascending.
# - Renders the maintenance_deadlines.html template with the sorted deadlines.
#
# Args:
# - request (HttpRequest): The incoming HTTP request.
#
# Returns:
# - HttpResponse: Renders the maintenance deadlines list page.
#################################################


@active_member_required
def maintenance_deadlines(request):
    today = date.today()
    today_plus_30 = today + timedelta(days=30)

    all_deadlines = MaintenanceDeadline.objects.all().select_related(
        "glider", "towplane"
    )
    sorted_deadlines = sorted(
        all_deadlines,
        key=lambda d: (
            0 if d.due_date < today else 1 if (d.due_date - today).days <= 30 else 2,
            d.due_date,
        ),
    )

    # Determine which deadlines the user can update
    member = request.user
    is_webmaster = (
        member.is_superuser or member.groups.filter(name="Webmasters").exists()
    )

    # Get all aircraft this member is a meister for
    meister_gliders = set()
    meister_towplanes = set()
    if not is_webmaster:
        meister_records = AircraftMeister.objects.filter(member=member).select_related(
            "glider", "towplane"
        )
        for meister in meister_records:
            if meister.glider:
                meister_gliders.add(meister.glider.id)
            if meister.towplane:
                meister_towplanes.add(meister.towplane.id)

    # Flag to show update UI (webmaster, superuser, or has any meister assignments)
    can_update_deadlines = (
        is_webmaster or bool(meister_gliders) or bool(meister_towplanes)
    )

    return render(
        request,
        "logsheet/maintenance_deadlines.html",
        {
            "deadlines": sorted_deadlines,
            "today": today,
            "today_plus_30": today_plus_30,
            "is_webmaster": is_webmaster,
            "meister_gliders": meister_gliders,
            "meister_towplanes": meister_towplanes,
            "can_update_deadlines": can_update_deadlines,
        },
    )


#################################################
# update_maintenance_deadline
#
# Purpose:
# Allows maintenance officers (Aircraft Meisters) and webmasters to update
# the due date for maintenance deadlines via AJAX POST request.
#
# Behavior:
# - Validates that the user is either:
#   * A webmaster (member of "Webmasters" group), OR
#   * An Aircraft Meister for the specific aircraft
# - Updates the MaintenanceDeadline.due_date with the provided date
# - Returns JSON response with success/error status
#
# Args:
# - request (HttpRequest): The incoming HTTP POST request with 'due_date' parameter
# - deadline_id (int): Primary key of the MaintenanceDeadline to update
#
# Returns:
# - JsonResponse: {"success": true/false, "message": str, "new_due_date": str}
#################################################


@require_POST
@active_member_required
def update_maintenance_deadline(request, deadline_id):
    deadline = get_object_or_404(MaintenanceDeadline, pk=deadline_id)
    member = request.user

    # Check permissions: webmaster OR aircraft meister for this aircraft
    is_webmaster = (
        member.is_superuser or member.groups.filter(name="Webmasters").exists()
    )

    # Validate that deadline has either glider or towplane
    if not deadline.glider and not deadline.towplane:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid deadline: no aircraft associated.",
            },
            status=400,
        )

    is_meister = False
    if deadline.glider:
        is_meister = AircraftMeister.objects.filter(
            glider=deadline.glider, member=member
        ).exists()
    if deadline.towplane and not is_meister:
        is_meister = AircraftMeister.objects.filter(
            towplane=deadline.towplane, member=member
        ).exists()

    if not (is_webmaster or is_meister):
        return JsonResponse(
            {
                "success": False,
                "error": "You are not authorized to update this deadline.",
            },
            status=403,
        )

    # Get and validate the new due date
    new_due_date_str = request.POST.get("due_date")
    if not new_due_date_str:
        return JsonResponse(
            {"success": False, "error": "Due date is required."}, status=400
        )

    try:
        new_due_date = datetime.strptime(new_due_date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse(
            {"success": False, "error": "Invalid date format. Use YYYY-MM-DD."},
            status=400,
        )

    # Update the deadline
    old_due_date = deadline.due_date
    deadline.due_date = new_due_date
    deadline.save()

    aircraft_name = deadline.glider or deadline.towplane
    logger.info(
        f"Maintenance deadline updated by {member.username}: {aircraft_name} - "
        f"{deadline.description_label} changed from {old_due_date} to {new_due_date}"
    )

    return JsonResponse(
        {
            "success": True,
            "message": f"Deadline updated successfully to {new_due_date}.",
            "new_due_date": new_due_date.strftime("%Y-%m-%d"),
        }
    )


def _td_to_hours(td: timedelta | None) -> float:
    if not td:
        return 0.0
    # keep 2dp; template can round to 1
    return round(td.total_seconds() / 3600.0, 2)


def _daily_flight_rollup(
    queryset, date_field="logsheet__log_date", issues_by_day=None, deadlines_by_day=None
):
    """
    Return rows: day, logsheet_pk, flights, day_time, cum_time, plus
    pre-attached issues/deadlines and decimal-hour fields for display.
    """
    issues_by_day = issues_by_day or {}
    deadlines_by_day = deadlines_by_day or {}

    daily_qs = (
        queryset.values(day=F(date_field), logsheet_pk=F("logsheet_id"))
        .annotate(
            flights=Count("id"),
            day_time=Sum("duration", default=timedelta(0)),
        )
        .order_by("day", "logsheet_pk")
    )

    rows = list(daily_qs)

    # Collect all days with issues or deadlines, even if no flights
    extra_days = set(issues_by_day.keys()) | set(deadlines_by_day.keys())
    days_in_rows = set(r["day"] for r in rows)
    for day in extra_days - days_in_rows:
        rows.append(
            {
                "day": day,
                "logsheet_pk": None,
                "flights": 0,
                "day_time": timedelta(0),
                "cum_time": timedelta(0),
                "issues": issues_by_day.get(day, []),
                "deadlines": deadlines_by_day.get(day, []),
                "day_hours": 0.0,
                "cum_hours": 0.0,
            }
        )

    # Sort rows by day (and logsheet_pk for stability)
    rows.sort(key=lambda r: (r["day"], r["logsheet_pk"] or 0))

    # Running total + attach events + decimal hours
    running = timedelta(0)
    for r in rows:
        running += r["day_time"] or timedelta(0)
        r["cum_time"] = running
        r["issues"] = issues_by_day.get(r["day"], [])
        r["deadlines"] = deadlines_by_day.get(r["day"], [])
        r["day_hours"] = _td_to_hours(r["day_time"])
        r["cum_hours"] = _td_to_hours(r["cum_time"])

    # Mark year anchors and collect navigation list
    year_seen: set[int] = set()
    year_nav: list[dict] = []
    for r in rows:
        if isinstance(r["day"], date):
            y = r["day"].year
        else:
            y = r["day"].year  # if already a date

        if y not in year_seen:
            year_seen.add(y)
            r["year_anchor"] = f"y{y}"  # e.g., "y2025"
            year_nav.append({"year": y, "anchor": r["year_anchor"]})
        else:
            r["year_anchor"] = None

    return rows, sorted(year_nav, key=lambda x: x["year"], reverse=True)


def _issues_by_day_for_glider(glider):
    # Issues by report_date
    qs_report = (
        MaintenanceIssue.objects.filter(glider=glider)
        .values(
            "report_date",
            "id",
            "description",
            "resolved",
            "grounded",
            "resolved_date",
            "report_date",
        )
        .order_by("report_date", "id")
    )
    # Issues by resolved_date (for issues resolved on non-flight days)
    qs_resolved = (
        MaintenanceIssue.objects.filter(glider=glider, resolved=True)
        .exclude(resolved_date__isnull=True)
        .values(
            "resolved_date",
            "id",
            "description",
            "resolved",
            "grounded",
            "resolved_date",
            "report_date",
        )
        .order_by("resolved_date", "id")
    )
    bucket = {}
    for it in qs_report:
        it = dict(it)
        it["event_type"] = "reported"
        bucket.setdefault(it["report_date"], []).append(it)
    for it in qs_resolved:
        it = dict(it)
        it["event_type"] = "resolved"
        # Only add if not already present for this day (avoid double-listing if resolved same day as reported)
        if it["resolved_date"] != it["report_date"]:
            bucket.setdefault(it["resolved_date"], []).append(it)
    return bucket


def _deadlines_by_day_for_glider(glider):
    qs = (
        MaintenanceDeadline.objects.filter(glider=glider)
        .annotate(day=TruncDate("due_date"))
        .values("day", "id", "description", "due_date")
        .order_by("day", "id")
    )
    bucket = {}
    for dl in qs:
        bucket.setdefault(dl["day"], []).append(dl)
    return bucket


def glider_logbook(request, pk: int):
    glider = get_object_or_404(Glider, pk=pk)

    flights = (
        Flight.objects.select_related("logsheet")
        .filter(glider=glider)
        .order_by("-logsheet__log_date", "-logsheet_id")
    )

    issues_by_day = _issues_by_day_for_glider(glider)
    deadlines_by_day = _deadlines_by_day_for_glider(glider)

    daily, year_nav = _daily_flight_rollup(
        flights,
        date_field="logsheet__log_date",
        issues_by_day=issues_by_day,
        deadlines_by_day=deadlines_by_day,
    )

    # Add initial_hours to every day's cumulative hours
    if daily and hasattr(glider, "initial_hours"):
        for r in daily:
            r["cum_hours"] = round(
                float(r["cum_hours"]) + float(glider.initial_hours), 1
            )
    # Ensure the template's shared column uses a consistent key: glider_tows
    # For glider logbooks the rollup rows use 'flights' while the shared
    # equipment_logbook template expects 'glider_tows' (used by towplane code).
    # Populate 'glider_tows' from 'flights' so the column renders correctly.
    for r in daily:
        if "glider_tows" not in r:
            r["glider_tows"] = r.get("flights", 0)
    context = {
        "object": glider,
        "object_type": "glider",
        "daily": daily,
        "year_nav": year_nav,  # for bookmarks
    }
    return render(request, "logsheet/equipment_logbook.html", context)


def _issues_by_day_for_towplane(towplane):
    """
    Get maintenance issues by day for a towplane.

    Returns issues indexed by both report_date and resolved_date (if different),
    so issues show up when created AND when resolved.
    """
    # Issues by report_date
    qs_report = (
        MaintenanceIssue.objects.filter(towplane=towplane)
        .values(
            "report_date",
            "id",
            "description",
            "resolved",
            "grounded",
            "resolved_date",
        )
        .order_by("report_date", "id")
    )
    # Issues by resolved_date (for issues resolved on non-flight days)
    qs_resolved = (
        MaintenanceIssue.objects.filter(towplane=towplane, resolved=True)
        .exclude(resolved_date__isnull=True)
        .values(
            "resolved_date",
            "id",
            "description",
            "resolved",
            "grounded",
            "report_date",
        )
        .order_by("resolved_date", "id")
    )
    bucket = {}
    for it in qs_report:
        it = dict(it)
        it["event_type"] = "reported"
        bucket.setdefault(it["report_date"], []).append(it)
    for it in qs_resolved:
        it = dict(it)
        it["event_type"] = "resolved"
        # Only add if resolved on a different day than reported (avoid double-listing)
        if it["resolved_date"] != it["report_date"]:
            bucket.setdefault(it["resolved_date"], []).append(it)
    return bucket


def _deadlines_by_day_for_towplane(towplane):
    """Get maintenance deadlines by due_date for a towplane."""
    qs = (
        MaintenanceDeadline.objects.filter(towplane=towplane)
        .values("due_date", "id", "description")
        .order_by("due_date", "id")
    )
    bucket = {}
    for dl in qs:
        day = dl["due_date"]
        bucket.setdefault(day, []).append(dl)
    return bucket


def towplane_logbook(request, pk: int):
    """
    Display the logbook for a towplane.

    Performance optimized: Uses batch queries instead of per-day queries.
    For a towplane with 10+ years of data (potentially thousands of days),
    this reduces query count from O(days) to O(1) for major data fetches.
    """
    towplane = get_object_or_404(Towplane, pk=pk)

    # Get TowplaneCloseout records for this towplane, grouped by day
    closeouts = (
        TowplaneCloseout.objects.filter(towplane=towplane)
        .select_related("logsheet")
        .order_by("logsheet__log_date", "logsheet_id")
    )

    # OPTIMIZATION: Pre-fetch ALL flights for this towplane in a single query
    # instead of querying per-day (N+1 fix)
    all_flights = Flight.objects.filter(towplane=towplane).values(
        "logsheet__log_date", "tow_pilot", "guest_towpilot_name", "legacy_towpilot_name"
    )

    # Build per-day flight data: count and tow pilot IDs/names
    flights_by_day = {}  # day -> {"count": int, "towpilots": set}
    all_towpilot_ids = set()
    for f in all_flights:
        day = f["logsheet__log_date"]
        if day not in flights_by_day:
            flights_by_day[day] = {"count": 0, "towpilots": set()}
        flights_by_day[day]["count"] += 1

        if f["tow_pilot"]:
            flights_by_day[day]["towpilots"].add(f["tow_pilot"])
            all_towpilot_ids.add(f["tow_pilot"])
        elif f["guest_towpilot_name"]:
            flights_by_day[day]["towpilots"].add(f["guest_towpilot_name"])
        elif f["legacy_towpilot_name"]:
            flights_by_day[day]["towpilots"].add(f["legacy_towpilot_name"])

    # OPTIMIZATION: Pre-fetch ALL member names in a single query
    id_to_name = {}
    if all_towpilot_ids:
        for m in Member.objects.filter(id__in=all_towpilot_ids).only(
            "id", "first_name", "last_name", "username"
        ):
            id_to_name[m.id] = m.get_full_name() or m.username

    # OPTIMIZATION: Pre-fetch ALL issues and deadlines once (instead of re-querying per day)
    issues_by_day = _issues_by_day_for_towplane(towplane)
    deadlines_by_day = _deadlines_by_day_for_towplane(towplane)

    # Group closeouts by day
    # Note: When multiple closeouts exist for the same day (e.g., from different
    # logsheets), we use the first logsheet's PK encountered. The closeouts are
    # ordered by log_date and logsheet_id, so this is deterministic.
    daily_data = {}
    for c in closeouts:
        day = c.logsheet.log_date
        flight_info = flights_by_day.get(day, {"count": 0, "towpilots": set()})
        tow_count = flight_info["count"]

        if day not in daily_data:
            # Convert tow pilot IDs to names (only when creating new day entry)
            towpilot_names = []
            for ref in flight_info["towpilots"]:
                if isinstance(ref, int) and ref in id_to_name:
                    towpilot_names.append(id_to_name[ref])
                elif isinstance(ref, int):
                    # Orphaned member ID - member was deleted
                    towpilot_names.append(f"[Member ID {ref}]")
                else:
                    towpilot_names.append(ref)

            daily_data[day] = {
                "day": day,
                "logsheet_pk": c.logsheet.pk,
                "day_hours": float(c.tach_time or 0),
                "cum_hours": float(c.end_tach) if c.end_tach is not None else None,
                "glider_tows": tow_count,
                "towpilots": towpilot_names,
                "issues": issues_by_day.get(day, []),
                "deadlines": deadlines_by_day.get(day, []),
            }
        else:
            daily_data[day]["day_hours"] += float(c.tach_time or 0)
            # Only update cumulative hours when this closeout has a non-null end_tach.
            # This prevents later closeouts without an end_tach from overwriting a
            # previously recorded tach reading for the same day.
            if c.end_tach is not None:
                daily_data[day]["cum_hours"] = float(c.end_tach)
            # glider_tows is already set from flights_by_day

    # Issue #537: Add rows for days with maintenance issues/deadlines but no closeouts
    # This ensures maintenance events are visible even when the towplane wasn't used
    # For maintenance-only days, carry forward the last known tach reading up to that date.
    # If there is no prior closeout (no known tach yet), leave cum_hours as None so the
    # template can render a blank instead of an incorrect 0.0.
    extra_days = set(issues_by_day.keys()) | set(deadlines_by_day.keys())
    days_in_data = set(daily_data.keys())
    # Exclude days that have flights but no closeout (incomplete logsheets) from synthetic rows
    days_with_flights = set(flights_by_day.keys())
    remaining_days = sorted(extra_days - days_in_data - days_with_flights)
    closeout_timeline = [(c.logsheet.log_date, c.end_tach) for c in closeouts]
    last_tach = None
    timeline_index = 0
    num_closeouts = len(closeout_timeline)

    for day in remaining_days:
        # Advance through closeouts up to and including this day, updating last_tach
        while (
            timeline_index < num_closeouts
            and closeout_timeline[timeline_index][0] <= day
        ):
            _, end_tach = closeout_timeline[timeline_index]
            if end_tach is not None:
                last_tach = float(end_tach)
            timeline_index += 1

        daily_data[day] = {
            "day": day,
            "logsheet_pk": None,
            "day_hours": 0.0,
            "cum_hours": last_tach,
            "glider_tows": 0,
            "towpilots": [],
            "issues": issues_by_day.get(day, []),
            "deadlines": deadlines_by_day.get(day, []),
        }

    # Sort days and build final list
    daily = [daily_data[day] for day in sorted(daily_data.keys())]

    # Year navigation anchors
    year_seen = set()
    year_nav = []
    for row in daily:
        y = row["day"].year
        if y not in year_seen:
            year_seen.add(y)
            row["year_anchor"] = f"y{y}"
            year_nav.append({"year": y, "anchor": row["year_anchor"]})
        else:
            row["year_anchor"] = None

    context = {
        "object": towplane,
        "object_type": "towplane",
        "daily": daily,
        "year_nav": sorted(year_nav, key=lambda x: x["year"], reverse=True),
    }
    return render(request, "logsheet/equipment_logbook.html", context)
