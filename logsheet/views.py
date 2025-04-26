from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from datetime import timedelta, date
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.core.paginator import Paginator
from datetime import datetime
from django.shortcuts import get_object_or_404, render, redirect
from members.decorators import active_member_required
from .models import Glider, Logsheet, LogsheetCloseout, TowplaneCloseout, Towplane, LogsheetPayment, Flight, MaintenanceIssue, AircraftMeister, MaintenanceDeadline
from .forms import LogsheetCloseoutForm, LogsheetDutyCrewForm, TowplaneCloseoutFormSet, CreateLogsheetForm, FlightForm, MaintenanceIssueForm




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
            messages.success(request, f"Logsheet for {logsheet.log_date} at {logsheet.airfield} created.")
            return redirect("logsheet:manage", pk=logsheet.pk)
    else:
        form = CreateLogsheetForm()

    return render(request, "logsheet/start_logsheet.html", {"form": form})

#################################################
# manage_logsheet

# This view handles the management of a specific logsheet.
# 
# It allows active members to:
# - View all flights associated with the logsheet, with optional filtering by pilot or instructor name.
# - Add new flights to the logsheet (if not finalized).
# - Finalize the logsheet, locking in all calculated costs as actual costs.
# - Reopen a finalized logsheet for revision (superusers only).
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
    #flights = logsheet.flights.select_related("pilot", "glider").all().order_by("launch_time")
    flights = (
        logsheet.flights
        .select_related("pilot", "glider")
        .order_by("-landing_time", "-launch_time")
    )


    query = request.GET.get("q")
    if query:
        flights = flights.filter(
            Q(pilot__first_name__icontains=query) |
            Q(pilot__last_name__icontains=query) |
            Q(instructor__first_name__icontains=query) |
            Q(instructor__last_name__icontains=query)
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

        for flight in flights:
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
            if not flight.landing_time:
                invalid_flights.append(f"Flight #{flight.id} is missing a landing time.")
            if not flight.release_altitude:
                invalid_flights.append(f"Flight #{flight.id} is missing a release altitude.")
            if not flight.towplane:
                invalid_flights.append(f"Flight #{flight.id} is missing a tow plane.")
            if not flight.tow_pilot:
                invalid_flights.append(f"Flight #{flight.id} is missing a tow pilot.")
            if not flight.launch_time:
                invalid_flights.append(f"Flight #{flight.id} is missing a launch time.")

            # Enforce required duty crew before finalization
            required_roles = {
                "duty_officer": logsheet.duty_officer,
                "tow_pilot": logsheet.tow_pilot,
                "duty_instructor": logsheet.duty_instructor,
            }

            missing_roles = [label.replace("_", " ").title() for label, value in required_roles.items() if not value]

            if missing_roles:
                messages.error(
                    request,
                    "Cannot finalize. Missing duty crew: " + ", ".join(missing_roles)
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
                "Cannot finalize. Missing payment method for: " + ", ".join(str(m) for m in missing)
            )
            return redirect("logsheet:manage_logsheet_finances", pk=logsheet.pk)

        # Lock in cost values
        # That means take the temporary values we calculated for the costs 
        # and place them in these other variables that get perma-written to the database. 
        for flight in flights:
            if flight.tow_cost_actual is None:
                flight.tow_cost_actual = flight.tow_cost_calculated
            if flight.rental_cost_actual is None:
                flight.rental_cost_actual = flight.rental_cost_calculated
            flight.save()

        logsheet.finalized = True
        logsheet.save()
        from .models import RevisionLog  # if not already imported
        
        RevisionLog.objects.create(
            logsheet=logsheet,
            revised_by=request.user,
            note="Logsheet finalized"
        )
        
        messages.success(request, "Logsheet has been finalized and all costs locked in.")
        return redirect("logsheet:manage", pk=logsheet.pk)

    # If the logsheet is finalized, prevent adding new flights
    # This check is done here to ensure that only superusers can reopen finalized logbooks
    # If there is a "revise", then we'll remove the finalized status
    # and the logsheet can be returned to editing status.  
    elif request.method == "POST":
        from .models import RevisionLog

        if "revise" in request.POST:
            if request.user.is_superuser:
                logsheet.finalized = False
                logsheet.save()
        
                RevisionLog.objects.create(
                    logsheet=logsheet,
                    revised_by=request.user,
                    note="Logsheet returned to revised state"
                )

            else:
                return HttpResponseForbidden("Only superusers can revise a finalized logsheet.")
            return redirect("logsheet:manage", pk=logsheet.pk)

    revisions = logsheet.revisions.select_related("revised_by").order_by("-revised_at")
    context = {
        "logsheet": logsheet,
        "flights": flights,
        "can_edit": not logsheet.finalized or request.user.is_superuser,
        "revisions": revisions,

    }
     # Find previous logsheet
    previous_logsheet = Logsheet.objects.filter(
        log_date__lt=logsheet.log_date
    ).order_by('-log_date').first()
        
    # Find next logsheet
    next_logsheet = Logsheet.objects.filter(
        log_date__gt=logsheet.log_date
    ).order_by('log_date').first()
    
    # Add them to your context
    context["previous_logsheet"] = previous_logsheet
    context["next_logsheet"] = next_logsheet

    return render(request, "logsheet/logsheet_manage.html", context)



#################################################
# view_flight
# This view handles the viewing of a specific flight within a logsheet.
@active_member_required
def view_flight(request, pk):
    flight = get_object_or_404(Flight, pk=pk)

    return render(request, "logsheet/flight_view.html", {
        "flight": flight,
    })



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
    year = request.GET.get("year", str(datetime.now().year))  # Default to current year
    logsheets = Logsheet.objects.all()

    if year:
        logsheets = logsheets.filter(log_date__year=year)

    if query:
        logsheets = logsheets.filter(
            Q(airfield__identifier__icontains=query) |
            Q(airfield__name__icontains=query) |
            Q(created_by__username__icontains=query) |
            Q(duty_officer__last_name__icontains=query) |
            Q(tow_pilot__last_name__icontains=query) | 
            Q(duty_instructor__last_name__icontains=query) 
        )
    #logsheets = logsheets.filter(airfield__identifier__icontains="VG55")

    logsheets = logsheets.order_by("-log_date", "-created_at")

    paginator = Paginator(logsheets, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    from django.db.models.functions import ExtractYear

    available_years = (
        Logsheet.objects.annotate(year=ExtractYear("log_date"))
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
    )

    return render(request, "logsheet/logsheet_list.html", {
        "logsheets": page_obj.object_list,
        "query": query,
        "year": year,
        "page_obj": page_obj,
        "paginator": paginator,
        "available_years": available_years,
    })

#################################################
# edit_flight

# This view handles the editing of an existing flight within a specific logsheet.
# 
# It allows active members to:
# - Edit the details of a flight associated with a logsheet.
# - Prevent edits if the logsheet is finalized (unless the user is a superuser).
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

    # Only allow edits if not finalized
    if logsheet.finalized and not request.user.is_superuser:
        return HttpResponseForbidden("This logsheet is finalized and cannot be edited.")

    if request.method == "POST":
        form = FlightForm(request.POST, instance=flight)
        if form.is_valid():
            form.save()
            messages.success(request, "Flight updated.")
            return redirect("logsheet:manage", pk=logsheet.pk)
    else:
        form = FlightForm(instance=flight)

    return render(request, "logsheet/edit_flight_form.html", {
        "form": form,
        "flight": flight,
        "logsheet": logsheet
    })

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

    if request.method == "POST":
        form = FlightForm(request.POST)
        if form.is_valid():
            flight = form.save(commit=False)
            flight.logsheet = logsheet
            flight.save()
            return redirect("logsheet:manage", pk=logsheet.pk)
    else:
        form = FlightForm()

    return render(request, "logsheet/edit_flight_form.html", {
        "form": form,
        "logsheet": logsheet,
        "mode": "add",
    })

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

# This view handles the financial management of a specific logsheet.
# 
# It allows active members to:
# - View a detailed breakdown of flight costs for all flights in the logsheet.
# - Display costs based on whether the logsheet is finalized (actual costs) or not (calculated costs).
# - Summarize financial data per pilot, including the number of flights, tow costs, rental costs, and total costs.
# - Calculate and display charges for each member, considering cost-sharing arrangements (e.g., even splits, tow-only splits, rental-only splits, or full responsibility).
# - Update payment methods and notes for each member.
# - Finalize the logsheet, locking in all costs and ensuring all responsible members have a payment method.
# 
# Methods:
# - flight_costs(f): Determines the tow, rental, and total costs for a flight based on whether the logsheet is finalized.
# - POST handling:
#   - Finalize: Ensures all responsible members have payment methods, locks in costs, and finalizes the logsheet.
#   - Update payment methods: Saves payment methods and notes for each member.
# 
# Args:
#    request (HttpRequest): The HTTP request object containing metadata about the request.
#    pk (int): The primary key of the logsheet to manage finances for.
# 
# Returns:
#    HttpResponse: Renders the financial management page with detailed cost breakdowns, pilot summaries, and member charges.

@active_member_required
def manage_logsheet_finances(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    flights = logsheet.flights.all()

    # Use locked-in values if finalized, else use calculated
    def flight_costs(f):
        return {
            "tow": f.tow_cost_actual if logsheet.finalized else f.tow_cost_calculated,
            "rental": f.rental_cost_actual if logsheet.finalized else f.rental_cost_calculated,
            "total": f.total_cost if logsheet.finalized else (
                (f.tow_cost_calculated or 0) + (f.rental_cost_calculated or 0)
            )
        }

    flight_data = []
    total_tow = total_rental = total_sum = 0

    for flight in flights:
        costs = flight_costs(flight)
        flight_data.append((flight, costs))
        total_tow += costs["tow"] or 0
        total_rental += costs["rental"] or 0
        total_sum += costs["total"] or 0

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
    member_charges = defaultdict(lambda: {"tow": Decimal("0.00"), "rental": Decimal("0.00"), "total": Decimal("0.00")})
    for flight, costs in flight_data:
        pilot = flight.pilot
        partner = flight.split_with
        split_type = flight.split_type
        tow = costs["tow"] or Decimal("0.00")
        rental = costs["rental"] or Decimal("0.00")
        total = costs["total"] or Decimal("0.00")

        if partner and split_type:
            if split_type == "even":
                half = total / 2
                member_charges[pilot]["total"] += half
                member_charges[partner]["total"] += half
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

    # Add combined totals
    for summary in member_charges.values():
        summary["total"] = summary["tow"] + summary["rental"]

    member_payment_data = []
    for member in member_charges:
        summary = member_charges[member]
        payment, _ = LogsheetPayment.objects.get_or_create(logsheet=logsheet, member=member)
        member_payment_data.append({
            "member": member,
            "amount": summary["total"],
            "payment_method": payment.payment_method,
            "note": payment.note,
        })
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

            missing = []
            for member in responsible_members:
                try:
                    payment = LogsheetPayment.objects.get(logsheet=logsheet, member=member)
                    if not payment.payment_method:
                        missing.append(member.full_display_name)
                except LogsheetPayment.DoesNotExist:
                    missing.append(member.full_display_name)

            if missing:
                messages.error(
                    request,
                    "Cannot finalize. Missing payment method for: " + ", ".join(missing)
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
            messages.success(request, "Logsheet has been finalized and all costs locked in.")
            return redirect("logsheet:manage", pk=logsheet.pk)

        else:
            for entry in member_payment_data:
                member = entry["member"]
                payment, _ = LogsheetPayment.objects.get_or_create(logsheet=logsheet, member=member)
                payment_method = request.POST.get(f"payment_method_{member.id}")
                note = request.POST.get(f"note_{member.id}", "").strip()
                payment.payment_method = payment_method or None
                payment.note = note
                payment.save()

            messages.success(request, "Payment methods updated.")
            return redirect("logsheet:manage_logsheet_finances", pk=logsheet.pk)

    context = {
        "logsheet": logsheet,
        "flight_data": flight_data,
        "total_tow": total_tow,
        "total_rental": total_rental,
        "total_sum": total_sum,
        "pilot_summary": dict(pilot_summary),
        "member_charges": dict(member_charges),
        "member_payment_data": member_payment_data
    }

    return render(request, "logsheet/manage_logsheet_finances.html", context)


@active_member_required
def edit_logsheet_closeout(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    closeout, _ = LogsheetCloseout.objects.get_or_create(logsheet=logsheet)
    maintenance_issues = MaintenanceIssue.objects.filter(logsheet=logsheet).select_related("reported_by", "glider", "towplane")

    if logsheet.finalized and not request.user.is_superuser:
        return HttpResponseForbidden("This logsheet is finalized and cannot be edited.")

    # Identify towplanes used in this logsheet
    towplanes_used = Towplane.objects.filter(flight__logsheet=logsheet).distinct()

    # Make sure a TowplaneCloseout exists for each
    for towplane in towplanes_used:
        TowplaneCloseout.objects.get_or_create(logsheet=logsheet, towplane=towplane)

    # Build formset for towplane closeouts
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

    return render(request, "logsheet/edit_closeout_form.html", {
        "logsheet": logsheet,
        "form": form,
        "duty_form": duty_form,
        "formset": formset,
        "gliders": Glider.objects.filter(club_owned=True, is_active=True).order_by("n_number"),
        "towplanes": Towplane.objects.filter(is_active=True).order_by("n_number"),
        "maintenance_issues": maintenance_issues

    })

@active_member_required
def view_logsheet_closeout(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    maintenance_issues = MaintenanceIssue.objects.filter(logsheet=logsheet).select_related("reported_by", "glider", "towplane")
    closeout = getattr(logsheet, "closeout", None)
    towplanes = logsheet.towplane_closeouts.select_related("towplane").all()
    return render(request, "logsheet/view_closeout.html", {
        "logsheet": logsheet,
        "closeout": closeout,
        "towplanes": towplanes,
        "maintenance_issues": maintenance_issues
    })

@require_POST
@active_member_required
def add_maintenance_issue(request, logsheet_id):
    logsheet = get_object_or_404(Logsheet, pk=logsheet_id)
    form = MaintenanceIssueForm(request.POST)

    if form.is_valid():
        issue = form.save(commit=False)
        if not issue.glider and not issue.towplane:
            messages.error(request, "Please select either a glider or a towplane.")
            return redirect("logsheet:edit_logsheet_closeout", pk=logsheet_id)

        issue.reported_by = request.user
        issue.logsheet = logsheet
        issue.save()
        messages.success(request, "Maintenance issue submitted successfully.")
    else:
        messages.error(request, "Failed to submit maintenance issue.")
    return redirect("logsheet:edit_logsheet_closeout", pk=logsheet.id)


@active_member_required
def equipment_list(request):
    gliders = Glider.objects.filter(is_active=True, club_owned=True).order_by("n_number")
    towplanes = Towplane.objects.filter(is_active=True, club_owned=True).order_by("n_number")
    return render(request, "logsheet/equipment_list.html", {
        "gliders": gliders,
        "towplanes": towplanes,
    })

@active_member_required
def maintenance_issues(request):
    open_issues = MaintenanceIssue.objects.filter(resolved=False).select_related("glider", "towplane")
    return render(request, "logsheet/maintenance_list.html", {
        "open_issues": open_issues,
    })


@active_member_required
def mark_issue_resolved(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, pk=issue_id)

    # Check if this user is the AircraftMeister for the aircraft
    member = request.user
    if issue.glider:
        if not AircraftMeister.objects.filter(glider=issue.glider, meister=member).exists():
            messages.error(request, "You are not authorized to resolve issues for this glider.")
            return redirect("logsheet:maintenance_issues")
    elif issue.towplane:
        if not AircraftMeister.objects.filter(towplane=issue.towplane, meister=member).exists():
            messages.error(request, "You are not authorized to resolve issues for this towplane.")
            return redirect("logsheet:maintenance_issues")

    issue.resolved = True
    issue.grounded = False  # in case it was grounded
    issue.save()

    messages.success(request, "Maintenance issue marked as resolved.")
    return redirect("logsheet:maintenance_issues")




@active_member_required
def resolve_maintenance_modal(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, id=issue_id)

    return render(request, "logsheet/maintenance_resolve_modal.html", {
        "issue": issue
    })

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

@require_POST
@active_member_required
def maintenance_mark_resolved(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, id=issue_id)

    user = request.user
    if not issue.can_be_resolved_by(user):
        return HttpResponseForbidden("You're not authorized to resolve this issue.")

    issue.resolved = True
    issue.resolved_by = user
    issue.resolved_date = now().date()
    issue.save()

    return JsonResponse({"reload": True})

@active_member_required
def maintenance_resolve_modal(request, issue_id):
    issue = get_object_or_404(MaintenanceIssue, id=issue_id)
    return render(request, "logsheet/maintenance_resolve_modal.html", {"issue": issue})

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

@active_member_required
def maintenance_deadlines(request):
    today = date.today()
    today_plus_30 = today + timedelta(days=30)

    all_deadlines = MaintenanceDeadline.objects.all().select_related('glider', 'towplane')
    sorted_deadlines = sorted(
        all_deadlines,
        key=lambda d: (
            0 if d.due_date < today else 
            1 if (d.due_date - today).days <= 30 else 
            2,
            d.due_date
        )
    )

    return render(request, "logsheet/maintenance_deadlines.html", {
        "deadlines": sorted_deadlines,
        "today": today,
        "today_plus_30": today_plus_30,
    })
