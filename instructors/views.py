import csv
import itertools
import json
import random
import re
from collections import OrderedDict, defaultdict, namedtuple
from datetime import date, datetime, time, timedelta
from io import BytesIO

import qrcode
from dateutil.relativedelta import relativedelta
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F, Max, Q, Sum, Value
from django.forms import formset_factory
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

# Intermediate loading page for logbook
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View as DjangoView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import FormView

from instructors.decorators import instructor_required, member_or_instructor_required
from instructors.forms import (
    GroundInstructionForm,
    GroundLessonScoreFormSet,
    InstructionReportForm,
    LessonScoreSimpleForm,
    LessonScoreSimpleFormSet,
    QualificationAssignForm,
    SyllabusDocumentForm,
)
from instructors.models import (
    GroundInstruction,
    GroundLessonScore,
    InstructionReport,
    LessonScore,
    StudentProgressSnapshot,
    SyllabusDocument,
    TrainingLesson,
    TrainingPhase,
)
from instructors.utils import get_flight_summary_for_member
from knowledgetest.forms import TestBuilderForm
from knowledgetest.models import (
    Question,
    QuestionCategory,
    WrittenTestAssignment,
    WrittenTestTemplate,
    WrittenTestTemplateQuestion,
)
from knowledgetest.views import get_presets
from logsheet.models import Flight, Logsheet
from members.constants.membership import DEFAULT_ACTIVE_STATUSES
from members.decorators import active_member_required
from members.models import Member
from notifications.models import Notification


@require_POST
@csrf_exempt
def logbook_loading(request):
    # Redirect to logbook with show_all_years=1
    target_url = reverse("instructors:member_logbook") + "?show_all_years=1"
    return render(
        request, "instructors/logbook_loading.html", {"target_url": target_url}
    )


####################################################
# public_syllabus_overview
#
# Renders a grouped view of all training phases and associated
# syllabus documents ('header', 'materials') for public access.
# No login required.
#
# Context:
# - phases: Queryset of TrainingPhase with prefetch 'lessons'.
# - header: SyllabusDocument with slug 'header'.
# - materials: SyllabusDocument with slug 'materials'.
####################################################


# Training Syllabus links available to the public, no instructor login required.


def public_syllabus_overview(request):
    phases = TrainingPhase.objects.prefetch_related("lessons").all()
    header = SyllabusDocument.objects.filter(slug="header").first()
    materials = SyllabusDocument.objects.filter(slug="materials").first()

    return render(
        request,
        "instructors/syllabus_grouped.html",
        {
            "phases": phases,
            "header": header,
            "materials": materials,
            "public": True,
        },
    )


####################################################
# public_syllabus_detail
#
# Displays detailed HTML content for a single lesson identified
# by its code. Accessible without authentication.
#
# Parameters:
# - code: TrainingLesson.code
#
# Context:
# - lesson: Retrieved TrainingLesson instance.
# - public: True flag for template logic.
####################################################


def public_syllabus_detail(request, code):
    lesson = get_object_or_404(TrainingLesson, code=code)
    # Get all lessons in code order
    lessons = list(TrainingLesson.objects.order_by("code"))
    idx = next((i for i, l in enumerate(lessons) if l.code == code), None)
    prev_lesson = lessons[idx - 1] if idx is not None and idx > 0 else None
    next_lesson = (
        lessons[idx + 1] if idx is not None and idx < len(lessons) - 1 else None
    )
    return render(
        request,
        "instructors/syllabus_detail.html",
        {
            "lesson": lesson,
            "public": True,
            "prev_lesson": prev_lesson,
            "next_lesson": next_lesson,
        },
    )


####################################################
# instructors_home
#
# Dashboard landing page for instructors.
# Requires instructor login.
####################################################


@instructor_required
def instructors_home(request):
    return render(request, "instructors/instructors_home.html")


####################################################
# syllabus_overview
#
# Lists all TrainingLesson entries in code order.
# For authenticated instructors.
####################################################


@instructor_required
def syllabus_overview(request):
    lessons = TrainingLesson.objects.all().order_by("code")
    return render(request, "instructors/syllabus_overview.html", {"lessons": lessons})


####################################################
# syllabus_overview_grouped
#
# Grouped syllabus view by phase, includes header/materials.
# For authenticated instructors.
####################################################


@instructor_required
def syllabus_overview_grouped(request):
    phases = TrainingPhase.objects.prefetch_related("lessons").all()
    header = SyllabusDocument.objects.filter(slug="header").first()
    materials = SyllabusDocument.objects.filter(slug="materials").first()

    return render(
        request,
        "instructors/syllabus_grouped.html",
        {
            "phases": phases,
            "header": header,
            "materials": materials,
        },
    )


####################################################
# syllabus_detail
#
# Shows HTML content for a specific lesson code.
# Accessible to instructors only.
####################################################


@instructor_required
def syllabus_detail(request, code):
    lesson = get_object_or_404(TrainingLesson, code=code)
    return render(request, "instructors/syllabus_detail.html", {"lesson": lesson})


####################################################
# fill_instruction_report
#
# GET: Presents a form for an existing or new InstructionReport
#       for a student on a given date.
# POST: Validates and saves report and associated LessonScores.
#
# Parameters:
# - student_id: Member PK of the student.
# - report_date: String YYYY-MM-DD.
#
# Template: instructors/fill_instruction_report.html
####################################################


@instructor_required
def fill_instruction_report(request, student_id, report_date):
    try:
        report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponseBadRequest("Invalid report date format.")

    student = get_object_or_404(Member, pk=student_id)
    instructor = request.user

    # 1) On GET: only retrieve, do NOT create a stub
    try:
        report = InstructionReport.objects.get(
            student=student, instructor=instructor, report_date=report_date
        )
        created = False
    except InstructionReport.DoesNotExist:
        report = None
        created = False

    if report_date > now().date():
        return HttpResponseBadRequest("Report date cannot be in the future.")

    lessons = TrainingLesson.objects.all().order_by("code")

    if request.method == "POST":
        # 2) Now *create* if it didn’t exist
        if report is None:
            report = InstructionReport(
                student=student, instructor=instructor, report_date=report_date
            )

        report_form = InstructionReportForm(request.POST, instance=report)
        formset = LessonScoreSimpleFormSet(request.POST)

        if report_form.is_valid() and formset.is_valid():
            # save the InstructionReport (new or existing)
            report = report_form.save()

            # clear & recreate the LessonScores
            LessonScore.objects.filter(report=report).delete()
            for form in formset.cleaned_data:
                lesson = form.get("lesson")
                score = form.get("score")
                if lesson and score:
                    LessonScore.objects.create(
                        report=report, lesson=lesson, score=score
                    )

            messages.success(request, "Instruction report submitted successfully.")
            return redirect(
                "instructors:member_instruction_record", member_id=student.id
            )
        else:
            messages.error(
                request,
                "There were errors in the form. Please review and correct them.",
            )
    else:
        # GET: build empty form/formset (report may be None)
        report_form = InstructionReportForm(instance=report)
        initial_data = []
        for lesson in lessons:
            if report:
                existing = LessonScore.objects.filter(
                    report=report, lesson=lesson
                ).first()
                val = existing.score if existing else ""
            else:
                val = ""
            initial_data.append({"lesson": lesson.id, "score": val})

        formset = LessonScoreSimpleFormSet(initial=initial_data)
        form_rows = list(zip(formset.forms, lessons))

    return render(
        request,
        "instructors/fill_instruction_report.html",
        {
            "student": student,
            "report_form": report_form,
            "formset": formset,
            "form_rows": form_rows,
            "report_date": report_date,
        },
    )


####################################################
# select_instruction_date
#
# Displays dates of recent flights (last 30 days) for selecting
# an instruction report to fill. Requires active member status.
####################################################


@active_member_required
def select_instruction_date(request, student_id):
    instructor = request.user
    student = get_object_or_404(Member, pk=student_id)
    today = timezone.now().date()
    cutoff = today - timedelta(days=30)  # ✨ Only show flights in last 30 days

    recent_flights = Flight.objects.filter(
        instructor=instructor,
        pilot=student,
        logsheet__log_date__gte=cutoff,  # 💥 date filtering here
        logsheet__log_date__lte=today,
    ).select_related("logsheet")

    # Group by date
    flights_by_date = defaultdict(list)
    for flight in recent_flights:
        flights_by_date[flight.logsheet.log_date].append(flight)

    sorted_dates = sorted(flights_by_date.items(), reverse=True)

    context = {
        "student": student,
        "flights_by_date": sorted_dates,
        "today": today,
    }
    return render(request, "instructors/select_instruction_date.html", context)


# instructors/views.py (continued)

####################################################
# get_instructor_initials
#
# Utility function to derive two-letter uppercase initials
# from a Member's first and last names. Returns '??' if
# either name part is missing.
#
# Parameters:
# - member: Member instance
#
# Returns:
# - String of two uppercase letters or '??'
####################################################


def get_instructor_initials(member):
    # Remove suffixes from last name (e.g., Jr, Sr, III)
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    first = member.first_name.split()[0] if member.first_name else ""
    last_parts = member.last_name.split() if member.last_name else []
    last = ""
    for part in last_parts:
        if part.lower().strip(".,") not in suffixes:
            last = part
            break
    if first and last:
        initials = f"{first[0]}{last[0]}"
    else:
        initials = "??"
    return initials.upper()


####################################################
# member_training_grid
#
# Displays a grid of lesson progress for a given student,
# combining flight-based InstructionReport data and ground
# instruction sessions into a unified training grid.
#
# Requires the requester to be the student or an instructor.
#
# Parameters:
# - request: HttpRequest
# - member_id: PK of the student Member
#
# Context:
# - member: Member instance whose grid is shown
# - lesson_data: List of dicts with 'label', 'phase', 'scores',
#   'max_score', 'lesson_id', 'num_flights'
# - report_dates: Ordered list of dates for grid columns
# - column_metadata: List of dicts with 'date', 'initials', 'days_ago'
####################################################


@active_member_required
def member_training_grid(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    # Fetch all reports and prefetch lesson scores and instructors
    reports = (
        InstructionReport.objects.filter(student=member)
        .order_by("report_date")
        .prefetch_related("lesson_scores__lesson", "instructor")
    )
    if request.user != member and not request.user.instructor:
        raise PermissionDenied

    # Extract sorted report dates
    report_dates = [r.report_date for r in reports]
    lessons = TrainingLesson.objects.all().order_by("code")

    # Build lookup for scores by (lesson_id, date)
    scores_lookup = {
        (sc.lesson_id, rep.report_date): sc.score
        for rep in reports
        for sc in rep.lesson_scores.all()
    }

    # Fetch flights for metadata (instructor initials, days ago)
    flights = Flight.objects.filter(
        pilot=member, logsheet__log_date__in=report_dates
    ).select_related("logsheet", "instructor")
    ground_sessions = GroundInstruction.objects.filter(
        student=member, date__in=report_dates
    ).select_related("instructor")
    flights_by_date = defaultdict(list)
    ground_by_date = {g.date: g for g in ground_sessions}
    today = now().date()
    for f in flights:
        if not f.instructor:
            continue
        d = f.logsheet.log_date
        initials = "".join(
            [n[0] for n in str(f.instructor.full_display_name or "").split()]
        )
        full_name = str(f.instructor.full_display_name or "")
        flights_by_date[d].append(
            {
                "days_ago": (today - d).days,
                "initials": initials,
                "full_name": full_name,
            }
        )

        # Compose instructor initials/name for each date (flight or ground)
        def get_instructor_meta_for_date(d):
            # Prefer flight instructor if present
            metas = flights_by_date.get(d, [])
            if metas:
                initials = metas[0]["initials"]
                full_name = metas[0]["full_name"]
            elif d in ground_by_date:
                ground_instr = ground_by_date[d].instructor
                initials = get_instructor_initials(ground_instr)
                full_name = str(ground_instr.full_display_name or "")
            else:
                report = reports.filter(report_date=d).first()
                if report and report.instructor:
                    initials = get_instructor_initials(report.instructor)
                    full_name = report.instructor.full_display_name
                else:
                    initials = ""
                    full_name = ""
            return {
                "initials": initials,
                "full_name": full_name,
                "days_ago": (today - d).days,
            }

    # Compose grid rows per lesson
    lesson_data = []
    for lesson in lessons:
        row = {
            "label": f"{lesson.code} – {lesson.title}",
            "phase": lesson.phase.name if lesson.phase else "Other",
            "scores": [],
            "max_score": "",
            "lesson_id": lesson.id,
            "code": lesson.code,
        }
        max_scores = []
        for d in report_dates:
            score = scores_lookup.get((lesson.id, d), "")
            if score.isdigit():
                max_scores.append(int(score))
            meta = flights_by_date.get(d, [])
            if meta:
                info = meta[0]
                label = f"{info['initials']}<br>{info['days_ago']}"
                tooltip = f"{info['full_name']} – {info['days_ago']} days ago"
            else:
                label = tooltip = ""
            row["scores"].append({"score": score, "label": label, "tooltip": tooltip})
        row["max_score"] = str(max(max_scores)) if max_scores else ""
        lesson_data.append(row)

    # Build column metadata for template headers using get_instructor_meta_for_date
    column_metadata = []
    for d in report_dates:
        flights_on_day = flights.filter(logsheet__log_date=d)
        num_flights = flights_on_day.count()
        # Build tooltip string
        tooltip_lines = [f"{num_flights} flight{'s' if num_flights != 1 else ''}"]
        for f in flights_on_day:
            tow = (
                f.release_altitude
                if hasattr(f, "release_altitude") and f.release_altitude
                else None
            )
            duration = f.duration if hasattr(f, "duration") and f.duration else None
            tow_str = f"{tow:,}" if tow else "?"
            # Format duration as H:MM
            if duration:
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                duration_str = f"{hours}:{minutes:02d}"
            else:
                duration_str = "?"
            tooltip_lines.append(f"{tow_str} feet, {duration_str}")
        flights_tooltip = "\n".join(tooltip_lines)
        meta = get_instructor_meta_for_date(d)
        column_metadata.append(
            {
                "date": d,
                "initials": meta.get("initials", ""),
                "days_ago": meta.get("days_ago", ""),
                "instructor_name": meta.get("full_name", ""),
                "num_flights": num_flights,
                "flights_tooltip": flights_tooltip,
            }
        )

    return render(
        request,
        "shared/training_grid.html",
        {
            "member": member,
            "lesson_data": lesson_data,
            "report_dates": report_dates,
            "column_metadata": column_metadata,
        },
    )


####################################################
# log_ground_instruction
#
# Presents a form to record a ground instruction session and its scores,
# then saves the session and associated lesson scores.
#
# GET: Shows blank formset for each lesson.
# POST: Validates and saves GroundInstruction and GroundLessonScore.
#
# Context:
# - form: GroundInstructionForm
# - formset: GroundLessonScoreFormSet
# - form_rows: paired list of (form, lesson) tuples for rendering
# - student: Member instance (or None)
####################################################


@instructor_required
def log_ground_instruction(request):
    student_id = request.GET.get("student")
    student = get_object_or_404(Member, pk=student_id) if student_id else None
    lessons = TrainingLesson.objects.all().order_by("code")

    if request.method == "POST":
        form = GroundInstructionForm(request.POST)
        formset = GroundLessonScoreFormSet(request.POST)
        formset.total_form_count()  # ensures management form counts

        if form.is_valid() and formset.is_valid():
            session = form.save(commit=False)
            session.instructor = request.user
            session.student = student
            session.save()
            # Create scores for each submitted lesson
            for entry in formset.cleaned_data:
                lid = entry.get("lesson")
                sc = entry.get("score")
                if lid and sc:
                    lesson = TrainingLesson.objects.get(pk=lid)
                    GroundLessonScore.objects.create(
                        session=session, lesson=lesson, score=sc
                    )
            messages.success(request, "Ground instruction session logged successfully.")
            if student is not None:
                return redirect(
                    "instructors:member_instruction_record", member_id=student.id
                )
            else:
                messages.error(request, "No student selected.")
                return redirect("instructors:log_ground_instruction")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = GroundInstructionForm()
        initial = [{"lesson": l.id} for l in lessons]
        formset = GroundLessonScoreFormSet(initial=initial)

    form_rows = list(zip(formset.forms, lessons))
    return render(
        request,
        "instructors/log_ground_instruction.html",
        {
            "form": form,
            "formset": formset,
            "form_rows": form_rows,
            "student": student,
        },
    )


####################################################
# is_instructor
#
# Test function to determine if a user has instructor privileges.
# Used with @user_passes_test for view access control.
#
# Parameters:
# - user: Django User instance
#
# Returns:
# - Boolean: True if authenticated and user.instructor flag is set
####################################################


def is_instructor(user):
    return user.is_authenticated and user.instructor


####################################################
# assign_qualification
#
# Assigns or revokes a club qualification for a given member.
# Accessible only to active members who are instructors.
#
# URL Parameters:
# - member_id: PK of the Member to assign qualification
#
# POST Behavior:
# - Validates QualificationAssignForm with instructor and student context
# - Saves form and redirects to member view on success
#
# GET Behavior:
# - Instantiates empty form prepopulated with instructor and student
# - Renders 'assign_qualification.html'
#
# Context:
# - form: QualificationAssignForm instance
# - student: Member instance being qualified
####################################################


@active_member_required
@user_passes_test(is_instructor)
def assign_qualification(request, member_id):
    student = get_object_or_404(Member, pk=member_id)

    if request.method == "POST":
        form = QualificationAssignForm(
            request.POST, instructor=request.user, student=student
        )
        if form.is_valid():
            form.save()
            return redirect("members:member_view", member_id=member_id)
    else:
        form = QualificationAssignForm(instructor=request.user, student=student)

    return render(
        request,
        "instructors/assign_qualification.html",
        {
            "form": form,
            "student": student,
        },
    )


####################################################
# progress_dashboard
#
# Renders the instructor dashboard showing two sections:
#  - Active student members ('student')
#  - Active rated pilots (non-students)
#
# The view fetches snapshots of precomputed progress, combining
# solo and checkride percentages and session counts.
# Also lists any pending reports in the last 30 days.
#
# Context:
# - pending_reports: List of dicts with 'pilot', 'date', 'report_url'
# - students_data: List of dicts with per-student 'solo_pct', 'rating_pct', 'sessions', 'solo_url', 'checkride_url'
# - rated_data: Same as students_data but for rated members
####################################################


@instructor_required
def progress_dashboard(request):
    # ————————————————————————————————
    # 1) split “students” vs “rated” by glider_rating
    students_qs = (
        Member.objects.filter(
            membership_status__in=DEFAULT_ACTIVE_STATUSES, glider_rating="student"
        )
        .annotate(
            last_flight=Max("flights_as_pilot__logsheet__log_date"),
        )
        .order_by("last_name")
    )

    rated_qs = (
        Member.objects.filter(membership_status__in=DEFAULT_ACTIVE_STATUSES)
        .exclude(glider_rating="student")
        .annotate(
            last_flight=Max("flights_as_pilot__logsheet__log_date"),
        )
        .order_by("last_name")
    )

    # ————————————————————————————————
    # 2) Bulk‐fetch all snapshots for those members
    member_ids = list(students_qs.values_list("pk", flat=True)) + list(
        rated_qs.values_list("pk", flat=True)
    )
    snapshots = StudentProgressSnapshot.objects.filter(
        student_id__in=member_ids
    ).select_related("student")
    snapshot_map = {snap.student_id: snap for snap in snapshots}

    # ————————————————————————————————
    # 3) Build context lists using the snapshots
    students_data = []
    for m in students_qs:
        snap = snapshot_map.get(m.pk)
        solo_pct = int((snap.solo_progress or 0.0) * 100) if snap else 0
        rating_pct = int((snap.checkride_progress or 0.0) * 100) if snap else 0
        sessions = snap.sessions if snap else 0

        students_data.append(
            {
                "member": m,
                "solo_pct": solo_pct,
                "rating_pct": rating_pct,
                "sessions": sessions,
                "solo_url": reverse("instructors:needed_for_solo", args=[m.pk]),
                "checkride_url": reverse(
                    "instructors:needed_for_checkride", args=[m.pk]
                ),
            }
        )

    rated_data = []
    for m in rated_qs:
        snap = snapshot_map.get(m.pk)
        solo_pct = int((snap.solo_progress or 0.0) * 100) if snap else 0
        rating_pct = int((snap.checkride_progress or 0.0) * 100) if snap else 0
        sessions = snap.sessions if snap else 0

        rated_data.append(
            {
                "member": m,
                "solo_pct": solo_pct,
                "rating_pct": rating_pct,
                "sessions": sessions,
            }
        )

    # ————————————————————————————————
    # 4) Pending reports (unchanged)
    cutoff = date.today() - timedelta(days=30)
    flights_qs = Flight.objects.filter(
        instructor=request.user, logsheet__log_date__gte=cutoff
    ).select_related("pilot", "logsheet")

    seen = set()
    pending_reports = []
    for f in flights_qs:
        key = (f.pilot_id, f.logsheet.log_date)
        if key in seen:
            continue
        seen.add(key)
        already = InstructionReport.objects.filter(
            student=f.pilot, instructor=request.user, report_date=f.logsheet.log_date
        ).exists()
        if already:
            continue

        pending_reports.append(
            {
                "pilot": f.pilot,
                "date": f.logsheet.log_date,
                "report_url": reverse(
                    "instructors:fill_instruction_report",
                    args=[f.pilot.pk, f.logsheet.log_date],
                ),
            }
        )

    # ————————————————————————————————
    return render(
        request,
        "instructors/progress_dashboard.html",
        {
            "pending_reports": pending_reports,
            "students_data": students_data,
            "rated_data": rated_data,
        },
    )


####################################################
# edit_syllabus_document
#
# Allows instructors to edit a SyllabusDocument identified by slug.
# GET: Shows form with existing content. POST: Saves updates.
#
# Context:
# - form: SyllabusDocumentForm instance
# - doc: SyllabusDocument instance
####################################################


@instructor_required
def edit_syllabus_document(request, slug):
    doc = get_object_or_404(SyllabusDocument, slug=slug)
    if request.method == "POST":
        form = SyllabusDocumentForm(request.POST, instance=doc)
        if form.is_valid():
            form.save()
            messages.success(request, "Syllabus document updated.")
            return redirect("instructors:syllabus_overview")
    else:
        form = SyllabusDocumentForm(instance=doc)

    return render(
        request,
        "instructors/edit_syllabus_document.html",
        {
            "form": form,
            "doc": doc,
        },
    )


####################################################
# member_instruction_record
#
# Displays a detailed timeline and summary of all instruction
# (flight reports and ground sessions) for a student.
# Includes flight summaries, chart data for progress over time,
# and blocks of session detail.
#
# Context:
# - member: Member instance
# - flights_summary: Output of get_flight_summary_for_member
# - report_blocks: List of dicts describing each session block
# - chart_dates, chart_solo, chart_rating, chart_anchors: Lists for charting
# - first_solo_str: Date string of first solo flight
# - *_json: JSON-encoded chart data for frontend JS
####################################################


def member_instruction_record(request, member_id):
    # Build a mapping of lesson code to lesson title for tooltips
    lesson_titles = {
        lesson.code: lesson.title for lesson in TrainingLesson.objects.all()
    }
    member = get_object_or_404(
        Member.objects.prefetch_related(
            "badges__badge", "memberqualification_set__qualification"
        ),
        pk=member_id,
    )

    # ── Flying summary by glider ──
    flights = Flight.objects.filter(pilot=member).select_related("logsheet", "aircraft")

    flights_summary = get_flight_summary_for_member(member)

    instruction_reports = (
        InstructionReport.objects.filter(student=member)
        .order_by("-report_date")
        .prefetch_related("lesson_scores__lesson")
    )

    ground_sessions = (
        GroundInstruction.objects.filter(student=member)
        .order_by("-date")
        .prefetch_related("lesson_scores__lesson")
    )

    # ── BUILD A TIMELINE OF ALL SESSIONS ──
    # 1) Grab all flight‐instruction reports and ground sessions
    flight_reports = list(
        InstructionReport.objects.filter(student=member)
        .order_by("report_date")
        .values_list("report_date", flat=True)
    )
    ground_reports = list(
        GroundInstruction.objects.filter(student=member)
        .order_by("date")
        .values_list("date", flat=True)
    )
    # 2) Merge into a single sorted list of dates with tags
    sessions = []
    for d in flight_reports:
        sessions.append({"date": d, "type": "flight"})
    for d in ground_reports:
        sessions.append({"date": d, "type": "ground"})
    sessions.sort(key=lambda x: x["date"])

    # 3) Precompute solo‐required vs rating‐required lesson IDs
    lessons = TrainingLesson.objects.all()
    solo_ids = {L.id for L in lessons if L.is_required_for_solo()}
    rating_ids = {L.id for L in lessons if L.is_required_for_private()}
    total_solo = len(solo_ids) or 1
    total_rating = len(rating_ids) or 1

    # 4) Find the date of first true “solo” (flight with no instructor)
    first_solo = (
        Flight.objects.filter(pilot=member, instructor__isnull=True)
        .order_by("logsheet__log_date")
        .values_list("logsheet__log_date", flat=True)
        .first()
    )
    first_solo_str = first_solo.strftime("%Y-%m-%d") if first_solo else ""

    # 5) Build the chart arrays with independent solo (3 or 4) vs rating (4 only)
    chart_dates = []
    chart_solo = []
    chart_rating = []
    chart_anchors = []

    for sess in sessions:
        d = sess["date"]
        # record the date+anchor
        chart_dates.append(d.strftime("%Y-%m-%d"))
        chart_anchors.append(f"{sess['type']}-{d.strftime('%Y-%m-%d')}")

        # solo‐standard completed (score 3 or 4)
        flight_solo = set(
            LessonScore.objects.filter(
                report__student=member, report__report_date__lte=d, score__in=["3", "4"]
            ).values_list("lesson_id", flat=True)
        )
        ground_solo = set(
            GroundLessonScore.objects.filter(
                session__student=member, session__date__lte=d, score__in=["3", "4"]
            ).values_list("lesson_id", flat=True)
        )
        solo_done = flight_solo | ground_solo

        # rating‐standard completed (score 4 only)
        flight_rating = set(
            LessonScore.objects.filter(
                report__student=member, report__report_date__lte=d, score="4"
            ).values_list("lesson_id", flat=True)
        )
        ground_rating = set(
            GroundLessonScore.objects.filter(
                session__student=member, session__date__lte=d, score="4"
            ).values_list("lesson_id", flat=True)
        )
        rating_done = flight_rating | ground_rating

        # compute percentages against their own totals
        chart_solo.append(int(len(solo_done & solo_ids) / total_solo * 100))
        chart_rating.append(int(len(rating_done & rating_ids) / total_rating * 100))

    blocks = []

    # ── Flight‐instruction reports ──
    for report in instruction_reports:
        d = report.report_date
        # cumulative “solo” (3 or 4) up to date d
        flight_solo = set(
            LessonScore.objects.filter(
                report__student=member, report__report_date__lte=d, score__in=["3", "4"]
            ).values_list("lesson_id", flat=True)
        )
        ground_solo = set(
            GroundLessonScore.objects.filter(
                session__student=member, session__date__lte=d, score__in=["3", "4"]
            ).values_list("lesson_id", flat=True)
        )
        solo_done = flight_solo | ground_solo

        # cumulative “rating” (4 only) up to date d
        flight_rate = set(
            LessonScore.objects.filter(
                report__student=member, report__report_date__lte=d, score="4"
            ).values_list("lesson_id", flat=True)
        )
        ground_rate = set(
            GroundLessonScore.objects.filter(
                session__student=member, session__date__lte=d, score="4"
            ).values_list("lesson_id", flat=True)
        )
        rating_done = flight_rate | ground_rate

        solo_pct = int(len(solo_done & solo_ids) / total_solo * 100)
        rating_pct = int(len(rating_done & rating_ids) / total_rating * 100)

        missing_solo = TrainingLesson.objects.filter(
            id__in=solo_ids - solo_done
        ).order_by("code")
        missing_rating = TrainingLesson.objects.filter(
            id__in=rating_ids - rating_done
        ).order_by("code")

        # Group lesson codes by score for this report
        scores_by_code = defaultdict(list)
        for s in report.lesson_scores.all():
            scores_by_code[str(s.score)].append(s.lesson.code)
        blocks.append(
            {
                "type": "flight",
                "report": report,
                "days_ago": (timezone.now().date() - d).days,
                "flights": Flight.objects.filter(
                    instructor=report.instructor,
                    pilot=report.student,
                    logsheet__log_date=d,
                ),
                "scores_by_code": dict(scores_by_code),
                "solo_pct": solo_pct,
                "rating_pct": rating_pct,
                "missing_solo": missing_solo,
                "missing_rating": missing_rating,
            }
        )

    # ── Ground‐instruction sessions ──
    for session in ground_sessions:
        d = session.date
        flight_solo = set(
            LessonScore.objects.filter(
                report__student=member, report__report_date__lte=d, score__in=["3", "4"]
            ).values_list("lesson_id", flat=True)
        )
        ground_solo = set(
            GroundLessonScore.objects.filter(
                session__student=member, session__date__lte=d, score__in=["3", "4"]
            ).values_list("lesson_id", flat=True)
        )
        solo_done = flight_solo | ground_solo

        flight_rate = set(
            LessonScore.objects.filter(
                report__student=member, report__report_date__lte=d, score="4"
            ).values_list("lesson_id", flat=True)
        )
        ground_rate = set(
            GroundLessonScore.objects.filter(
                session__student=member, session__date__lte=d, score="4"
            ).values_list("lesson_id", flat=True)
        )
        rating_done = flight_rate | ground_rate

        solo_pct = int(len(solo_done & solo_ids) / total_solo * 100)
        rating_pct = int(len(rating_done & rating_ids) / total_rating * 100)

        missing_solo = TrainingLesson.objects.filter(
            id__in=solo_ids - solo_done
        ).order_by("code")
        missing_rating = TrainingLesson.objects.filter(
            id__in=rating_ids - rating_done
        ).order_by("code")

        # Group lesson codes by score for this ground session
        scores_by_code = defaultdict(list)
        for s in session.lesson_scores.all():
            scores_by_code[str(s.score)].append(s.lesson.code)
        blocks.append(
            {
                "type": "ground",
                "report": session,
                "days_ago": (timezone.now().date() - d).days,
                "flights": None,
                "scores_by_code": dict(scores_by_code),
                "solo_pct": solo_pct,
                "rating_pct": rating_pct,
                "missing_solo": missing_solo,
                "missing_rating": missing_rating,
            }
        )

    blocks.sort(
        key=lambda b: (
            b["report"].report_date if b["type"] == "flight" else b["report"].date
        ),
        reverse=True,
    )

    # Group blocks by date for template
    from collections import OrderedDict

    daily_blocks = OrderedDict()
    for block in blocks:
        date_key = (
            block["report"].report_date
            if block["type"] == "flight"
            else block["report"].date
        )
        if date_key not in daily_blocks:
            daily_blocks[date_key] = []
        daily_blocks[date_key].append(block)
    daily_blocks = [
        {"date": date, "blocks": blist} for date, blist in daily_blocks.items()
    ]

    return render(
        request,
        "shared/member_instruction_record.html",
        {
            "member": member,
            "flights_summary": flights_summary,
            "report_blocks": blocks,  # for summary/progress alert logic
            "daily_blocks": daily_blocks,  # for grouped display
            "chart_dates": chart_dates,
            "chart_solo": chart_solo,
            "chart_rating": chart_rating,
            "chart_anchors": chart_anchors,
            "first_solo_str": first_solo_str,
            "chart_dates_json": json.dumps(chart_dates),
            "chart_solo_json": json.dumps(chart_solo),
            "chart_rating_json": json.dumps(chart_rating),
            "chart_anchors_json": json.dumps(chart_anchors),
            "lesson_titles": lesson_titles,
        },
    )


####################################################
# public_syllabus_qr
#
# Generates and returns a QR code PNG that links to the
# public detail view of a given syllabus lesson code.
#
# Parameters:
# - request: HttpRequest
# - code: TrainingLesson.code string
####################################################


def public_syllabus_qr(request, code):
    url = request.build_absolute_uri(reverse("public_syllabus_detail", args=[code]))
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, "PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


####################################################
# public_syllabus_full
#
# Displays the full syllabus for public consumption, including
# header, materials, and all lessons in code order.
#
# Parameters:
# - request: HttpRequest
####################################################


@require_GET
def public_syllabus_full(request):
    # grab header/materials as before
    phases = TrainingPhase.objects.prefetch_related("lessons").all()
    header = SyllabusDocument.objects.filter(slug="header").first()
    materials = SyllabusDocument.objects.filter(slug="materials").first()
    # all lessons in order
    lessons = TrainingLesson.objects.order_by("code").all()

    return render(
        request,
        "instructors/syllabus_full.html",
        {
            "phases": phases,
            "header": header,
            "materials": materials,
            "lessons": lessons,
        },
    )


####################################################
# member_logbook
#
# Renders a combined logbook timeline for the current user,
# merging flight events and ground instruction into pages
# with minutes, counts, and event details.
#
# Parameters:
# - request: HttpRequest
####################################################


@active_member_required
def member_logbook(request):

    def format_hhmm(duration):
        if not duration:
            return ""
        total_minutes = int(duration.total_seconds() // 60)
        h, m = divmod(total_minutes, 60)
        return f"{h}:{m:02d}"

    member = request.user
    # Determine which years to show

    import datetime

    today = datetime.date.today()
    # Find all years with any flights or ground instruction for this member
    flight_years_qs = Flight.objects.filter(
        Q(pilot=member) | Q(instructor=member) | Q(passenger=member)
    ).values_list("logsheet__log_date", flat=True)
    ground_years_qs = GroundInstruction.objects.filter(student=member).values_list(
        "date", flat=True
    )
    all_years = set()
    for dt in flight_years_qs:
        if dt:
            all_years.add(dt.year)
    for dt in ground_years_qs:
        if dt:
            all_years.add(dt.year)
    all_years = sorted(all_years, reverse=True)

    # Years requested to load
    show_all_years = request.GET.get("show_all_years")
    show_years = request.GET.getlist("year")
    if show_all_years:
        years_to_load = all_years
    elif show_years:
        years_to_load = [int(y) for y in show_years if y.isdigit()]
    else:
        # Default: last 12 months
        years_to_load = [today.year, today.year - 1]

    flights = (
        Flight.objects.filter(
            (Q(pilot=member) | Q(instructor=member) | Q(passenger=member))
            & Q(logsheet__log_date__year__in=years_to_load)
        )
        .select_related("glider", "instructor", "passenger", "airfield", "logsheet")
        .order_by("logsheet__log_date")
    )

    # Compute cumulative flight offset for numbering
    earliest_loaded_date = None
    if flights:
        earliest_loaded_date = flights[0].logsheet.log_date
    flight_offset = 0
    if earliest_loaded_date:
        flight_offset = Flight.objects.filter(
            (Q(pilot=member) | Q(instructor=member)),
            logsheet__log_date__lt=earliest_loaded_date,
        ).count()
    grounds = (
        GroundInstruction.objects.filter(student=member, date__year__in=years_to_load)
        .prefetch_related("lesson_scores__lesson")
        .order_by("date")
    )

    # 3) Use actual private_glider_checkride_date if available
    rating_date = getattr(member, "private_glider_checkride_date", None)

    # 4) Flatten flights & grounds into a single timeline of events, capturing time
    events = []
    for f in flights:
        events.append(
            {
                "type": "flight",
                "obj": f,
                "date": f.logsheet.log_date,
                "time": f.launch_time or time(0, 0),
            }
        )
    for g in grounds:
        events.append(
            {
                "type": "ground",
                "obj": g,
                "date": g.date,
                # ground sessions have no takeoff time; sort them first
                "time": time(0, 0),
            }
        )
    # sort by date then time
    events.sort(key=lambda e: (e["date"], e["time"]))

    # 5) Build one row per event, formatting all times as H:MM
    rows = []
    flight_no = 0

    for ev in events:
        if ev["type"] == "flight":
            f = ev["obj"]
            flight_id = f.id
            date = ev["date"]

            # Roles
            is_pilot = f.pilot_id == member.id
            is_instructor = f.instructor_id == member.id
            is_passenger = f.passenger_id == member.id

            # Always initialize report_id
            report_id = None

            # 5a) Flight #: increment for pilot OR instructor
            if is_pilot or is_instructor:
                flight_no += 1
                display_flight_no = flight_no + flight_offset
            else:
                display_flight_no = ""

            # Raw minutes
            dur_m = int(f.duration.total_seconds() // 60) if f.duration else 0
            dual_m = solo_m = pic_m = inst_m = 0
            comments = ""

            # 5b) Pilot logic: instruction received vs lesson codes
            if is_pilot:
                if f.instructor:
                    # Received dual / PIC
                    if rating_date and date >= rating_date:
                        pic_m += dur_m
                    else:
                        dual_m += dur_m

                    # Look up the instructor report
                    rpt = InstructionReport.objects.filter(
                        student=member, instructor=f.instructor, report_date=date
                    ).first()

                    if rpt:
                        codes = [ls.lesson.code for ls in rpt.lesson_scores.all()]
                        comments = (
                            f"{', '.join(codes)} /s/ {f.instructor.full_display_name}"
                        )
                        report_id = rpt.id
                    else:
                        comments = "instruction received"
                        report_id = None
                else:
                    # Solo flight (only if no passenger)
                    if not f.passenger and not f.passenger_name:
                        solo_m += dur_m
                    pic_m += dur_m
                    if f.passenger:
                        comments = f"{f.passenger.full_display_name}"
                    elif f.passenger_name:
                        comments = f"{f.passenger_name}"

            # 6) Passenger logic: show "Pilot (You)"
            elif is_passenger:
                comments = (
                    f"{f.pilot.full_display_name} (<i>{member.full_display_name}</i>)"
                )

            # 7) Instructor logic: inst_given + PIC
            elif is_instructor:
                inst_m += dur_m
                pic_m += dur_m
                student = f.pilot or f.passenger
                if student:
                    comments = student.full_display_name

            # Build the row
            instructor_cert = ""
            if f.instructor and hasattr(f.instructor, "pilot_certificate_number"):
                instructor_cert = f.instructor.pilot_certificate_number or ""
            # Build signature_html for template
            signature_html = ""
            if "/s/" in comments:
                pre, post = comments.split("/s/", 1)
                # Only the instructor name and cert get cursive, not the /s/
                post = post.strip()
                # Split post into name and (optional) cert
                if "," in post:
                    name, rest = post.split(",", 1)
                    name = name.strip()
                    rest = rest.strip()
                else:
                    name = post
                    rest = ""
                cert_part = f", {instructor_cert}CFI" if instructor_cert else ""
                signature_html = (
                    f"{pre.strip()} "
                    f"/s/ <span style=\"font-family: 'Lucida Handwriting', 'Comic Sans MS', 'Dancing Script', cursive, sans-serif; font-size: 1.1em;\">{name}</span>"
                    f"{cert_part}"
                )
            else:
                signature_html = comments
            row = {
                "flight_id": flight_id,
                "date": date,
                "flight_no": display_flight_no,
                "model": f.glider.model if f.glider else "",
                "n_number": f.glider.n_number if f.glider else "Private",
                "is_passenger": is_passenger,
                "A": (1 if f.launch_method == "tow" else 0) if not is_passenger else 0,
                "G": (
                    (1 if f.launch_method == "winch" else 0) if not is_passenger else 0
                ),
                "S": (1 if f.launch_method == "self" else 0) if not is_passenger else 0,
                "release": f.release_altitude or "",
                "maxh": "",  # always blank
                "airfield": f.airfield.identifier if f.airfield else "",
                "ground_inst": "",  # flight row
                "dual_received": format_hhmm(timedelta(minutes=dual_m)),
                "solo": format_hhmm(timedelta(minutes=solo_m)),
                "pic": format_hhmm(timedelta(minutes=pic_m)),
                "inst_given": format_hhmm(timedelta(minutes=inst_m)),
                "total": format_hhmm(timedelta(minutes=dur_m)),
                # raw-minute keys for page/run totals
                "ground_inst_m": 0,
                "dual_received_m": dual_m if not is_passenger else 0,
                "solo_m": solo_m if not is_passenger else 0,
                "pic_m": pic_m if not is_passenger else 0,
                "inst_given_m": inst_m if not is_passenger else 0,
                "total_m": dur_m if not is_passenger else 0,
                "report_id": report_id,
                "comments": comments,
                "instructor_certificate_number": instructor_cert,
                "signature_html": signature_html,
            }
            rows.append(row)

        else:  # ground instruction
            g = ev["obj"]
            gm = int(g.duration.total_seconds() // 60) if g.duration else 0
            # build the lesson list + instructor tag
            codes = [ls.lesson.code for ls in g.lesson_scores.all()]
            comments = ", ".join(codes)
            instructor_cert = ""
            if g.instructor and hasattr(g.instructor, "pilot_certificate_number"):
                instructor_cert = g.instructor.pilot_certificate_number or ""
            if g.instructor:
                comments += f" /s/ {g.instructor.full_display_name}"

            row = {
                "date": date,
                "flight_no": "",
                "model": "",
                "n_number": "",
                "is_passenger": False,
                "A": 0,
                "G": 0,
                "S": 0,
                "release": "",
                "maxh": "",
                "location": g.location or "",
                "comments": comments,
                "ground_inst": format_hhmm(timedelta(minutes=gm)),
                "dual_received": "",
                "solo": "",
                "pic": "",
                "inst_given": "",
                "total": "",
                "comments": ", ".join(ls.lesson.code for ls in g.lesson_scores.all()),
                # raw-minute fields (all zero except ground_inst_m)
                "ground_inst_m": gm,
                "dual_received_m": 0,
                "solo_m": 0,
                "pic_m": 0,
                "inst_given_m": 0,
                "total_m": 0,
                "instructor_certificate_number": instructor_cert,
            }
            rows.append(row)

    # 8) Extract year information for navigation
    years = []
    year_page_map = {}  # Maps year to page index where that year starts

    if rows:
        current_year = None
        for idx, row in enumerate(rows):
            row_date = row["date"]
            row_year = row_date.year
            if row_year != current_year:
                current_year = row_year
                years.append(row_year)
                # Calculate which page this year starts on (0-indexed)
                page_idx = idx // 10
                year_page_map[row_year] = page_idx

    # 9) Paginate into 10-row pages with per-page totals
    pages = []
    cumulative_m = {
        k: 0
        for k in (
            "ground_inst_m",
            "dual_received_m",
            "solo_m",
            "pic_m",
            "inst_given_m",
            "total_m",
            "A",
            "G",
            "S",
        )
    }

    for idx in range(0, len(rows), 10):
        chunk = rows[idx : idx + 10]
        page_number = idx // 10

        # Always set year_start for every page
        year_start = None
        if chunk:
            first_row_year = chunk[0]["date"].year
            year_start = first_row_year

        # filter out passenger‐only rows once
        non_passenger = [r for r in chunk if not r["is_passenger"]]

        # now sum across that filtered list
        sums_m = {
            "ground_inst_m": sum(r["ground_inst_m"] for r in non_passenger),
            "dual_received_m": sum(r["dual_received_m"] for r in non_passenger),
            "solo_m": sum(r["solo_m"] for r in non_passenger),
            "pic_m": sum(r["pic_m"] for r in non_passenger),
            "inst_given_m": sum(r["inst_given_m"] for r in non_passenger),
            "total_m": sum(r["total_m"] for r in non_passenger),
            "A": sum(r["A"] for r in non_passenger),
            "G": sum(r["G"] for r in non_passenger),
            "S": sum(r["S"] for r in non_passenger),
        }

        # update running raw‐minute totals
        for k, v in sums_m.items():
            cumulative_m[k] += v

        # format for display…
        sums = {
            "ground_inst": format_hhmm(timedelta(minutes=sums_m["ground_inst_m"])),
            "dual_received": format_hhmm(timedelta(minutes=sums_m["dual_received_m"])),
            "solo": format_hhmm(timedelta(minutes=sums_m["solo_m"])),
            "pic": format_hhmm(timedelta(minutes=sums_m["pic_m"])),
            "inst_given": format_hhmm(timedelta(minutes=sums_m["inst_given_m"])),
            "total": format_hhmm(timedelta(minutes=sums_m["total_m"])),
            "A": sums_m["A"],
            "G": sums_m["G"],
            "S": sums_m["S"],
        }

        cumulative = {
            "ground_inst": format_hhmm(
                timedelta(minutes=cumulative_m["ground_inst_m"])
            ),
            "dual_received": format_hhmm(
                timedelta(minutes=cumulative_m["dual_received_m"])
            ),
            "solo": format_hhmm(timedelta(minutes=cumulative_m["solo_m"])),
            "pic": format_hhmm(timedelta(minutes=cumulative_m["pic_m"])),
            "inst_given": format_hhmm(timedelta(minutes=cumulative_m["inst_given_m"])),
            "total": format_hhmm(timedelta(minutes=cumulative_m["total_m"])),
            "A": cumulative_m["A"],
            "G": cumulative_m["G"],
            "S": cumulative_m["S"],
        }
        pages.append(
            {
                "rows": chunk,
                "sums": sums,
                "cumulative": cumulative,
                "year_start": year_start,
                "page_number": page_number,
            }
        )

    # Annotate first page for each year for template anchors
    years_seen = set()
    for page in pages:
        if page.get("year_start") and page["year_start"] not in years_seen:
            page["is_first_for_year"] = True
            years_seen.add(page["year_start"])
        else:
            page["is_first_for_year"] = False

    return render(
        request,
        "instructors/logbook.html",
        {
            "member": member,
            "pages": pages,
            "years": years,
            "year_page_map": year_page_map,
            "all_years": all_years,
        },
    )


####################################################
# _build_signoff_records
#
# Internal helper to assemble the latest sign-off date and instructor
# for each lesson required under a given standard (solo or rating).
#
# Parameters:
# - student: Member instance
# - threshold_scores: list of score strings to include
# - requirement_check: callable(lesson) -> bool
####################################################


def _build_signoff_records(student, threshold_scores, requirement_check):
    records = []

    for lesson in TrainingLesson.objects.order_by("phase", "code"):
        # 1) Skip lessons not required
        if not requirement_check(lesson):
            continue

        # 2) Fetch latest flight-based signoff
        flight_entry = (
            LessonScore.objects.filter(
                report__student=student, lesson=lesson, score__in=threshold_scores
            )
            .select_related("report__instructor", "report")
            .order_by("-report__report_date")
            .first()
        )

        # 3) Fetch latest ground-based signoff
        ground_entry = (
            GroundLessonScore.objects.filter(
                session__student=student, lesson=lesson, score__in=threshold_scores
            )
            .select_related("session__instructor", "session")
            .order_by("-session__date")
            .first()
        )

        # 4) Pick whichever has the newer date
        best_date = None
        best_instr = None

        if flight_entry and ground_entry:
            if flight_entry.report.report_date >= ground_entry.session.date:
                best_date = flight_entry.report.report_date
                best_instr = flight_entry.report.instructor
            else:
                best_date = ground_entry.session.date
                best_instr = ground_entry.session.instructor
        elif flight_entry:
            best_date = flight_entry.report.report_date
            best_instr = flight_entry.report.instructor
        elif ground_entry:
            best_date = ground_entry.session.date
            best_instr = ground_entry.session.instructor

        records.append(
            {
                "lesson": lesson,
                "date": best_date,
                "instructor": best_instr,
            }
        )

    return records


####################################################
# needed_for_solo
#
# Displays the list of lessons a student still needs to achieve
# solo standard (score 3 or 4) along with existing sign-offs.
#
# Parameters:
# - request: HttpRequest
# - member_id: PK of the student Member
####################################################


@active_member_required
def needed_for_solo(request, member_id):
    student = get_object_or_404(Member, pk=member_id)

    # Solo standard is score of 3 or 4
    threshold = ["3", "4"]
    records = _build_signoff_records(
        student,
        threshold_scores=threshold,
        requirement_check=lambda l: l.is_required_for_solo(),
    )

    return render(
        request,
        "instructors/needed_for_solo.html",
        {
            "student": student,
            "records": records,
            "required_score": 3,
        },
    )


####################################################
# needed_for_checkride
#
# Shows lessons and flight-hour metrics required for a private
# checkride, including two-calendar-month window and thresholds.
#
# Parameters:
# - request: HttpRequest
# - member_id: PK of the student Member
####################################################


@active_member_required
def needed_for_checkride(request, member_id):
    student = get_object_or_404(Member, pk=member_id)

    # 1) Build the sign-off records as before
    threshold = ["4"]
    records = _build_signoff_records(
        student,
        threshold_scores=threshold,
        requirement_check=lambda l: l.is_required_for_private(),
    )

    # 2) Compute the 2-calendar-month window
    today = date.today()
    first_of_month = today.replace(day=1)
    window_start = first_of_month - relativedelta(months=2)

    # 3) Fetch all this student's glider flights
    flights = Flight.objects.filter(pilot=student)

    # 4) Total flight hours (sum launch→landing)
    total_hours = 0.0
    for f in flights:
        if f.launch_time and f.landing_time:
            delta = datetime.combine(
                f.logsheet.log_date, f.landing_time
            ) - datetime.combine(f.logsheet.log_date, f.launch_time)
            total_hours += delta.total_seconds() / 3600.0

    total_flights = flights.count()

    # 5) Solo flights/hours
    solo_qs = flights.filter(instructor__isnull=True)
    solo_flights = solo_qs.count()
    solo_hours = sum(
        (
            (
                datetime.combine(f.logsheet.log_date, f.landing_time)
                - datetime.combine(f.logsheet.log_date, f.launch_time)
            ).total_seconds()
            / 3600.0
        )
        for f in solo_qs
        if f.launch_time and f.landing_time
    )

    # 6) Instructor-led flights in last 2 calendar months
    instr_qs = flights.filter(
        instructor__isnull=False, logsheet__log_date__gte=window_start
    )

    instr_recent = instr_qs.count()
    # Grab the distinct dates, newest first
    instr_recent_dates = list(
        instr_qs.order_by("-logsheet__log_date")
        .values_list("logsheet__log_date", flat=True)
        .distinct()
    )

    # 7) Decide which block applies
    Metrics = namedtuple(
        "Metrics",
        [
            "block",  # 'A' for <40h, 'B' for ≥40h
            "total_hours",
            "total_flights",
            "total_time",
            "solo_hours",
            "solo_flights",
            "instr_recent",
            "instr_recent_dates",
            "required",
        ],
    )

    if total_hours >= 40:
        # Block B: ≥40h heavier-than-air → need 10 solo flights + 3 recent training flights
        required = {
            "total_time": 3,  # need 3 h total glider time
            "solo_flights": 10,
            "instr_recent": 3,
        }
        metrics = Metrics(
            block="B",
            total_hours=total_hours,
            total_flights=total_flights,
            total_time=total_hours,  # current total time
            solo_hours=solo_hours,
            solo_flights=solo_flights,
            instr_recent=instr_recent,
            instr_recent_dates=instr_recent_dates,
            required=required,
        )

    else:
        # Block A: <40h → need 20 flights, incl 3 recent training; and 2h solo +10 launches
        required = {
            "total_time": 10,  # need 10 h total glider time
            "total_flights": 20,
            "instr_recent": 3,
            "solo_hours": 2,
            "solo_flights": 10,
        }
        metrics = Metrics(
            block="A",
            total_hours=total_hours,
            total_flights=total_flights,
            total_time=total_hours,  # current total time
            solo_hours=solo_hours,
            solo_flights=solo_flights,
            instr_recent=instr_recent,
            instr_recent_dates=instr_recent_dates,
            required=required,
        )

    return render(
        request,
        "instructors/needed_for_checkride.html",
        {
            "student": student,
            "records": records,
            "required_score": 4,
            "flight_metrics": metrics,
            "window_start": window_start,
        },
    )


####################################################
# instruction_report_detail
#
# Returns an HTML fragment listing all the LessonScores for a given
# InstructionReport, used for AJAX detail panels.
#
# Parameters:
# - request: HttpRequest
# - report_id: PK of the InstructionReport
####################################################


def instruction_report_detail(request, report_id):
    """
    Returns a fragment listing the lessons & scores for a given InstructionReport.
    """
    rpt = get_object_or_404(
        InstructionReport.objects.prefetch_related("lesson_scores__lesson"),
        pk=report_id,
    )
    return render(
        request,
        "instructors/_instruction_detail_fragment.html",
        {
            "report": rpt,
        },
    )


@method_decorator(instructor_required, name="dispatch")
class CreateWrittenTestView(FormView):
    template_name = "written_test/create.html"
    form_class = TestBuilderForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        preset_key = self.request.GET.get("preset")
        if preset_key:
            kw["preset"] = get_presets().get(preset_key.upper())
        else:
            kw["preset"] = None
        return kw

    def get_context_data(self, **ctx):
        ctx = super().get_context_data(**ctx)
        ctx["presets"] = get_presets().keys()
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        # 1. Pull weights & must_include
        must = []
        if data["must_include"]:
            import re

            must = [int(n) for n in re.findall(r"\d+", data["must_include"])]
        weights = {
            code: data[f"weight_{code}"]
            for code in QuestionCategory.objects.values_list("code", flat=True)
            if data[f"weight_{code}"] > 0
        }
        MAX_QUESTIONS = 50
        import random

        if sum(weights.values()) + len(must) > MAX_QUESTIONS:
            must = list(dict.fromkeys(must))
            if len(must) >= MAX_QUESTIONS:
                must = must[:MAX_QUESTIONS]
                weights = {}
            else:
                pool = []
                for code, cnt in weights.items():
                    pool.extend(
                        list(
                            Question.objects.filter(category__code=code).exclude(
                                qnum__in=must
                            )
                        )
                        * cnt
                    )
                pool = list({q.qnum: q for q in pool}.values())
                needed = MAX_QUESTIONS - len(must)
                chosen = random.sample(pool, min(needed, len(pool)))
                weights = {}
                for q in chosen:
                    weights.setdefault(q.category.code, 0)
                    weights[q.category.code] += 1
        with transaction.atomic():
            tmpl = WrittenTestTemplate.objects.create(
                name=f"Test by {self.request.user} on {timezone.now().date()}",
                description=data.get("description", ""),
                pass_percentage=data["pass_percentage"],
                created_by=self.request.user,
            )
        # Only assign the test if the student is not the instructor
        if data["student"] != self.request.user:
            assignment = WrittenTestAssignment.objects.create(
                template=tmpl, student=data["student"], instructor=self.request.user
            )
            # Create notification for the student
            try:
                notif = Notification.objects.create(
                    user=data["student"],
                    message=f"You have been assigned a new written test: {tmpl.name}",
                    url=reverse("knowledgetest:quiz-pending"),
                )
            except Exception as e:
                print(f"Failed to create notification: {e}")
        order = 1
        # 3. First, include forced questions
        for qnum in must:
            try:
                q = Question.objects.get(pk=qnum)
                WrittenTestTemplateQuestion.objects.create(
                    template=tmpl, question=q, order=order
                )
                order += 1
            except Question.DoesNotExist:
                continue

        # 4. Then, for each category, randomly choose unanswered ones
        import random

        for code, cnt in weights.items():
            pool = list(
                Question.objects.filter(category__code=code).exclude(qnum__in=must)
            )
            chosen = random.sample(pool, min(cnt, len(pool)))
            for q in chosen:
                WrittenTestTemplateQuestion.objects.create(
                    template=tmpl, question=q, order=order
                )
                order += 1

        # 5. Redirect to the instructor review page
        return redirect(
            reverse("knowledgetest:quiz-review", args=[tmpl.pk, data["student"].pk])
        )


# Instructor test review page (not for taking the test)


class WrittenTestReviewView(DjangoView):
    template_name = "written_test/review.html"

    def get(self, request, pk, student_pk):
        from knowledgetest.models import Member, Question, WrittenTestTemplate

        tmpl = get_object_or_404(WrittenTestTemplate, pk=pk)
        student = get_object_or_404(Member, pk=student_pk)
        questions = tmpl.questions.all()
        return render(
            request,
            self.template_name,
            {
                "template": tmpl,
                "student": student,
                "questions": questions,
            },
        )


@active_member_required
def export_member_logbook_csv(request):
    """Export the member's logbook as CSV for Excel/Google Sheets with explicit instructor, pilot, passenger columns and constructed comments."""
    member = request.user

    def format_hhmm(duration):
        if not duration:
            return ""
        total_minutes = int(duration.total_seconds() // 60)
        h, m = divmod(total_minutes, 60)
        return f"{h}:{m:02d}"

    flights = (
        Flight.objects.filter(
            Q(pilot=member) | Q(instructor=member) | Q(passenger=member)
        )
        .select_related(
            "glider", "instructor", "pilot", "passenger", "airfield", "logsheet"
        )
        .order_by("logsheet__log_date")
    )
    grounds = (
        GroundInstruction.objects.filter(student=member)
        .prefetch_related("lesson_scores__lesson")
        .order_by("date")
    )

    rating_date = getattr(member, "private_glider_checkride_date", None)
    events = []
    for f in flights:
        events.append(
            {
                "type": "flight",
                "obj": f,
                "date": f.logsheet.log_date,
                "time": f.launch_time or time(0, 0),
            }
        )
    for g in grounds:
        events.append({"type": "ground", "obj": g, "date": g.date, "time": time(0, 0)})
    events.sort(key=lambda e: (e["date"], e["time"]))

    rows = []
    flight_no = 0
    for ev in events:
        if ev["type"] == "flight":
            f = ev["obj"]
            date = ev["date"]
            is_pilot = f.pilot_id == member.id
            is_instructor = f.instructor_id == member.id
            is_passenger = f.passenger_id == member.id
            if is_pilot or is_instructor:
                flight_no += 1
            dur_m = int(f.duration.total_seconds() // 60) if f.duration else 0
            dual_m = solo_m = pic_m = inst_m = 0
            comments = ""
            # Construct comments as in logbook.html: lesson codes for instruction, otherwise blank
            if is_pilot and f.instructor:
                rpt = InstructionReport.objects.filter(
                    student=member, instructor=f.instructor, report_date=date
                ).first()
                if rpt:
                    codes = [ls.lesson.code for ls in rpt.lesson_scores.all()]
                    if codes:
                        comments = ", ".join(codes)
            row = {
                "Date": date,
                "Flight #": flight_no if (is_pilot or is_instructor) else "",
                "Model": f.glider.model if f.glider else "",
                "N-Number": f.glider.n_number if f.glider else "Private",
                "A": (1 if f.launch_method == "tow" else 0) if not is_passenger else 0,
                "G": (
                    (1 if f.launch_method == "winch" else 0) if not is_passenger else 0
                ),
                "S": (1 if f.launch_method == "self" else 0) if not is_passenger else 0,
                "Release": f.release_altitude or "",
                "Location": f.airfield.identifier if f.airfield else "",
                "Ground Inst": "",
                "Dual": format_hhmm(timedelta(minutes=dual_m)),
                "Solo": format_hhmm(timedelta(minutes=solo_m)),
                "PIC": format_hhmm(timedelta(minutes=pic_m)),
                "Inst": format_hhmm(timedelta(minutes=inst_m)),
                "Total": format_hhmm(timedelta(minutes=dur_m)),
                "Instructor": f.instructor.full_display_name if f.instructor else "",
                "Pilot": f.pilot.full_display_name if f.pilot else "",
                "Passenger": (
                    f.passenger.full_display_name
                    if f.passenger
                    else (f.passenger_name or "")
                ),
                "Comments": comments,
            }
            rows.append(row)
        else:
            g = ev["obj"]
            gm = int(g.duration.total_seconds() // 60) if g.duration else 0
            codes = [ls.lesson.code for ls in g.lesson_scores.all()]
            comments = ", ".join(codes)
            if g.instructor and hasattr(g.instructor, "full_display_name"):
                instructor_name = g.instructor.full_display_name
            else:
                instructor_name = ""
            row = {
                "Date": g.date,
                "Flight #": "",
                "Model": "",
                "N-Number": "",
                "A": 0,
                "G": 0,
                "S": 0,
                "Release": "",
                "Location": g.location or "",
                "Ground Inst": format_hhmm(timedelta(minutes=gm)),
                "Dual": "",
                "Solo": "",
                "PIC": "",
                "Inst": "",
                "Total": "",
                "Instructor": instructor_name,
                "Pilot": member.full_display_name,
                "Passenger": "",
                "Comments": comments,
            }
            rows.append(row)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="logbook_{member.username}.csv"'
    )
    writer = csv.DictWriter(
        response,
        fieldnames=[
            "Date",
            "Flight #",
            "Model",
            "N-Number",
            "A",
            "G",
            "S",
            "Release",
            "Location",
            "Ground Inst",
            "Dual",
            "Solo",
            "PIC",
            "Inst",
            "Total",
            "Instructor",
            "Pilot",
            "Passenger",
            "Comments",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return response
