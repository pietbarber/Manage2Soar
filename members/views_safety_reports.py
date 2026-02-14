"""Safety Reports Views - Officer Interface.

This module provides views for safety officers to manage safety reports
without needing Django admin access.

Related: Issue #585 - Create Safety Officer Interface for Viewing Safety Reports
Related: Issue #622 - Safety Officers Dashboard with Ops Report Safety Sections
"""

import re
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import strip_tags

from logsheet.models import LogsheetCloseout

from .decorators import safety_officer_required
from .forms import SafetyReportOfficerForm
from .models import SafetyReport

# Regex pattern to identify "nothing to report" type entries
# Note: HTML is already stripped by strip_tags() before matching
NOTHING_TO_REPORT_PATTERN = re.compile(
    r"^\s*"  # Leading whitespace
    r"(?:"  # Non-capturing group for alternatives
    r"n/?a|none|nil|"  # Simple negatives
    r"nothing(?:\s+to\s+report)?|"  # "nothing" or "nothing to report"
    r"no\s+(?:safety\s+)?(?:issues?|reports?|concerns?|problems?|incidents?)(?:\s+to\s+report)?|"  # "no X" or "no X to report"
    r"all\s+(?:good|clear)"  # "all good/clear"
    r")"
    r"\.?\s*$",  # Optional trailing period and whitespace
    re.IGNORECASE,
)


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


def _is_nothing_to_report(html_content):
    """Check if HTML content is essentially a 'nothing to report' entry.

    Strips HTML tags and checks against common "nothing to report" phrases.
    Returns True if the content is effectively empty or a non-report.
    """
    if not html_content:
        return True
    text = strip_tags(html_content).strip()
    if not text:
        return True
    return bool(NOTHING_TO_REPORT_PATTERN.match(text))


@safety_officer_required
def safety_officer_dashboard(request):
    """Safety Officer Dashboard - consolidated view of all safety data.

    Combines:
    1. Safety suggestion box reports (SafetyReport model)
    2. Ops report safety sections from logsheet closeouts (last 12 months)

    Filters out trivial "nothing to report" entries from ops reports.

    Related: Issue #622
    """
    # --- Safety Suggestion Box Reports ---
    suggestion_reports = SafetyReport.objects.select_related(
        "reporter", "reviewed_by"
    ).order_by("-created_at")

    # Statistics for suggestion box reports
    suggestion_stats = SafetyReport.objects.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status="new")),
        in_progress=Count("id", filter=Q(status="in_progress")),
        resolved=Count("id", filter=Q(status="resolved")),
    )

    # Paginate suggestion box reports
    suggestion_paginator = Paginator(suggestion_reports, 10)
    suggestion_page = request.GET.get("suggestion_page")
    suggestion_page_obj = suggestion_paginator.get_page(suggestion_page)

    # --- Ops Report Safety Sections (last 12 months) ---
    twelve_months_ago = timezone.now().date() - timedelta(days=365)

    # Get closeouts with non-empty safety_issues from the last 12 months
    ops_safety_entries_qs = (
        LogsheetCloseout.objects.select_related("logsheet", "logsheet__airfield")
        .filter(
            logsheet__log_date__gte=twelve_months_ago,
            logsheet__finalized=True,
        )
        .exclude(safety_issues="")
        .order_by("-logsheet__log_date")
    )

    # Build counts and collect IDs for substantive entries in a single pass
    # This avoids materializing the entire queryset as Python model instances
    ops_total_count = 0
    ops_substantive_count = 0
    ops_substantive_ids = []

    for entry in ops_safety_entries_qs:
        ops_total_count += 1
        if not _is_nothing_to_report(entry.safety_issues):
            ops_substantive_count += 1
            ops_substantive_ids.append(entry.id)

    # Choose which set of entries to display based on show_all parameter
    show_all_ops = request.GET.get("show_all_ops") == "1"
    if show_all_ops:
        ops_safety_entries_qs_for_page = ops_safety_entries_qs
    else:
        # Filter by IDs of substantive entries while preserving original ordering
        ops_safety_entries_qs_for_page = ops_safety_entries_qs.filter(
            id__in=ops_substantive_ids
        )

    # Paginate ops safety entries
    ops_paginator = Paginator(ops_safety_entries_qs_for_page, 10)
    ops_page = request.GET.get("ops_page")
    ops_page_obj = ops_paginator.get_page(ops_page)

    context = {
        # Suggestion box data
        "suggestion_page_obj": suggestion_page_obj,
        "suggestion_stats": suggestion_stats,
        # Ops safety data
        "ops_page_obj": ops_page_obj,
        "ops_total_count": ops_total_count,
        "ops_substantive_count": ops_substantive_count,
        "show_all_ops": show_all_ops,
        # General
        "twelve_months_ago": twelve_months_ago,
    }
    return render(request, "members/safety_reports/dashboard.html", context)
