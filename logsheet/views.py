from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .models import Logsheet, Flight
from .forms import CreateLogsheetForm, FlightForm
from members.decorators import active_member_required
from django.db.models import Q

@active_member_required
def index(request):
    return render(request, "logsheet/index.html")


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


@active_member_required
def manage_logsheet(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)

    query = request.GET.get("q", "").strip()
    flights = logsheet.flights.all()

    if query:
        flights = flights.filter(
            Q(pilot__first_name__icontains=query) |
            Q(pilot__last_name__icontains=query) |
            Q(instructor__first_name__icontains=query) |
            Q(instructor__last_name__icontains=query)
        )

    if request.method == "POST":
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

    if request.method == "POST":
        if "finalize" in request.POST:
            if logsheet.finalized:
                messages.info(request, "This logsheet has already been finalized.")
                return redirect("logsheet:manage", pk=logsheet.pk)
    
            for flight in logsheet.flights.all():
                if flight.tow_cost_actual is None:
                    flight.tow_cost_actual = flight.tow_cost_calculated
                if flight.rental_cost_actual is None:
                    flight.rental_cost_actual = flight.rental_cost_calculated
                flight.save()
    
            logsheet.finalized = True
            logsheet.save()
            messages.success(request, "Logsheet has been finalized and all costs locked in.")
            return redirect("logsheet:manage", pk=logsheet.pk)
    
        form = FlightForm(request.POST)
        if form.is_valid():
            if logsheet.finalized:
                messages.error(request, "This logsheet is finalized and cannot accept new flights.")
            else:
                flight = form.save(commit=False)
                flight.logsheet = logsheet
                flight.save()
                messages.success(request, "Flight added successfully.")
                return redirect("logsheet:manage", pk=logsheet.pk)
    else:
        form = FlightForm(initial={"field": logsheet.airfield})


    return render(request, "logsheet/logsheet_manage.html", {
        "logsheet": logsheet,
        "flights": flights,
        "form": form,
        "query": query,
    })


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


@active_member_required
def edit_flight(request, logsheet_pk, flight_pk):
    logsheet = get_object_or_404(Logsheet, pk=logsheet_pk)
    flight = get_object_or_404(Flight, pk=flight_pk, logsheet=logsheet)

    # Optional: Only allow edits if not finalized
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

    context = {
        "logsheet": logsheet,
        "flight_data": flight_data,
        "total_tow": total_tow,
        "total_rental": total_rental,
        "total_sum": total_sum,
        "pilot_summary": dict(pilot_summary),
    }

    return render(request, "logsheet/manage_logsheet_finances.html", context)


