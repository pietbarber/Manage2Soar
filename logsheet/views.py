from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .models import Logsheet, Flight
from .forms import CreateLogsheetForm, FlightForm
from members.decorators import active_member_required
from django.db.models import Q

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
    flights = logsheet.flights.select_related("pilot", "glider").all().order_by("launch_time")

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

        from logsheet.models import LogsheetPayment
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
                    missing.append(member)
            except LogsheetPayment.DoesNotExist:
                missing.append(member)

        if missing:
            messages.error(
                request,
                "Cannot finalize. Missing payment method for: " + ", ".join(str(m) for m in missing)
            )
            return redirect("logsheet:manage_logsheet_finances", pk=logsheet.pk)

        # Lock in cost values
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
    
    elif request.method == "POST":
        from .models import RevisionLog

        if "revise" in request.POST:
            if request.user.is_superuser:
                logsheet.finalized = False
                logsheet.save()
        
                RevisionLog.objects.create(
                    logsheet=logsheet,
                    revised_by=request.user,
                )

                messages.warning(request, "Logsheet has been reopened for revision.")
            else:
                return HttpResponseForbidden("Only superusers can revise a finalized logsheet.")
            return redirect("logsheet:manage", pk=logsheet.pk)

    context = {
        "logsheet": logsheet,
        "flights": flights,
        "can_edit": not logsheet.finalized or request.user.is_superuser,
    }
    return render(request, "logsheet/logsheet_manage.html", context)


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
    logsheets = Logsheet.objects.all()

    if query:
        logsheets = logsheets.filter(
            Q(log_date__icontains=query) |
            Q(location__icontains=query) |
            Q(created_by__username__icontains=query)
        )

    logsheets = logsheets.order_by("-log_date", "-created_at")
    return render(request, "logsheet/logsheet_list.html", {
        "logsheets": logsheets,
        "query": query,
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
                        missing.append(member)
                except LogsheetPayment.DoesNotExist:
                    missing.append(member)

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