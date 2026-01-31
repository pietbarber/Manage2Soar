"""Safety Reports Views - Officer Interface.

This module provides views for safety officers to manage safety reports
without needing Django admin access.

Related: Issue #585 - Create Safety Officer Interface for Viewing Safety Reports
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import safety_officer_required
from .forms import SafetyReportOfficerForm
from .models import SafetyReport


@safety_officer_required
def safety_report_list(request):
    """List all safety reports for safety officers.

    Provides filtering, sorting, and pagination.
    """
    reports = SafetyReport.objects.select_related("reporter", "reviewed_by")

    # Filtering
    status_filter = request.GET.get("status", "")
    if status_filter:
        reports = reports.filter(status=status_filter)

    # Sorting
    default_sort = "-created_at"
    sort_by = request.GET.get("sort")
    valid_sorts = [
        "created_at",
        "-created_at",
        "status",
        "-status",
        "observation_date",
        "-observation_date",
    ]
    if sort_by in valid_sorts:
        # Handle nullable observation_date with secondary sort
        if "observation_date" in sort_by:
            if sort_by == "-observation_date":
                reports = reports.order_by(
                    F("observation_date").desc(nulls_last=True), "-created_at"
                )
            else:
                reports = reports.order_by(
                    F("observation_date").asc(nulls_last=True), "-created_at"
                )
        else:
            reports = reports.order_by(sort_by)
    else:
        sort_by = default_sort
        reports = reports.order_by(default_sort)

    # Pagination
    paginator = Paginator(reports, 20)  # 20 reports per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Statistics for dashboard (single query optimization)
    stats = SafetyReport.objects.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status="new")),
        in_progress=Count("id", filter=Q(status="in_progress")),
        resolved=Count("id", filter=Q(status="resolved")),
    )

    context = {
        "page_obj": page_obj,
        "stats": stats,
        "status_filter": status_filter,
        "sort_by": sort_by,
        "status_choices": SafetyReport.STATUS_CHOICES,
    }
    return render(request, "members/safety_reports/list.html", context)


@safety_officer_required
def safety_report_detail(request, report_id):
    """View and manage a single safety report.

    Safety officers can:
    - View full report details
    - Add internal notes
    - Update status
    - Record actions taken
    """
    report = get_object_or_404(SafetyReport, pk=report_id)

    if request.method == "POST":
        form = SafetyReportOfficerForm(request.POST, instance=report)
        if form.is_valid():
            updated_report = form.save(commit=False)

            # Track who reviewed and when
            if not report.reviewed_by:
                updated_report.reviewed_by = request.user
                updated_report.reviewed_at = timezone.now()

            updated_report.save()
            messages.success(request, "Safety report updated successfully.")
            return redirect("members:safety_report_detail", report_id=report_id)
    else:
        form = SafetyReportOfficerForm(instance=report)

    context = {
        "report": report,
        "form": form,
    }
    return render(request, "members/safety_reports/detail.html", context)
