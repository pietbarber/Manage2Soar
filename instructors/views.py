
import itertools
import json

from collections import defaultdict
from datetime import date, datetime, timedelta
from .decorators import instructor_required
from django.contrib import messages
from django.db.models import Q
from django.forms import formset_factory
from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.timezone import now
from instructors.decorators import member_or_instructor_required, instructor_required
from instructors.forms import (
    InstructionReportForm, LessonScoreSimpleForm, 
    LessonScoreSimpleFormSet, QualificationAssignForm, 
    GroundInstructionForm, GroundLessonScoreFormSet, 
    SyllabusDocumentForm
)
from instructors.models import (
    InstructionReport, LessonScore, GroundInstruction, 
    GroundLessonScore, TrainingLesson, SyllabusDocument, 
    TrainingPhase
)
from logsheet.models import Flight, Logsheet
from members.decorators import active_member_required
from members.models import Member
from django.contrib.auth.decorators import user_passes_test
from instructors.models import (
     InstructionReport, LessonScore, GroundInstruction, GroundLessonScore,
     TrainingLesson, SyllabusDocument, TrainingPhase
)
from django.db.models import Count, Max
from members.models import Member
from members.constants.membership import DEFAULT_ACTIVE_STATUSES



# Training Syllabus links available to the public, no instructor login required. 

def public_syllabus_overview(request):
    phases = TrainingPhase.objects.prefetch_related("lessons").all()
    header = SyllabusDocument.objects.filter(slug="header").first()
    materials = SyllabusDocument.objects.filter(slug="materials").first()

    return render(request, "instructors/syllabus_grouped.html", {
        "phases": phases,
        "header": header,
        "materials": materials,
        "public": True,
    })

def public_syllabus_detail(request, code):
    lesson = get_object_or_404(TrainingLesson, code=code)
    return render(request, "instructors/syllabus_detail.html", {
        "lesson": lesson,
        "public": True,
    })




# instructors/views.py
@instructor_required
def instructors_home(request):
    return render(request, "instructors/instructors_home.html")


@instructor_required
def syllabus_overview(request):
    lessons = TrainingLesson.objects.all().order_by("code")
    return render(request, "instructors/syllabus_overview.html", {"lessons": lessons})


@instructor_required
def syllabus_overview_grouped(request):
    phases = TrainingPhase.objects.prefetch_related("lessons").all()
    header = SyllabusDocument.objects.filter(slug="header").first()
    materials = SyllabusDocument.objects.filter(slug="materials").first()

    return render(request, "instructors/syllabus_grouped.html", {
        "phases": phases,
        "header": header,
        "materials": materials,
    })


@instructor_required
def syllabus_detail(request, code):
    lesson = get_object_or_404(TrainingLesson, code=code)
    return render(request, "instructors/syllabus_detail.html", {"lesson": lesson})


@instructor_required
def fill_instruction_report(request, student_id, report_date):
    try:
        report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponseBadRequest("Invalid report date format.")

    student = get_object_or_404(Member, pk=student_id)
    instructor = request.user

    report, created = InstructionReport.objects.get_or_create(
        student=student, instructor=instructor, report_date=report_date
    )

    if report_date > now().date():
        return HttpResponseBadRequest("Report date cannot be in the future.")

    lessons = TrainingLesson.objects.all().order_by("code")

    if request.method == "POST":
        report_form = InstructionReportForm(request.POST, instance=report)
        formset = LessonScoreSimpleFormSet(request.POST)

        if report_form.is_valid() and formset.is_valid():
            report_form.save()
            LessonScore.objects.filter(report=report).delete()

            for form in formset.cleaned_data:
                lesson = form.get("lesson")
                score = form.get("score")
                if lesson and score:
                    LessonScore.objects.create(report=report, lesson=lesson, score=score)

            messages.success(request, "Instruction report submitted successfully.")
            return redirect("instructors:member_instruction_record", member_id=student.id)
        else:
            messages.error(request, "There were errors in the form. Please review and correct them.")
            #print("Report form errors:", report_form.errors)
            #print("Formset errors:", formset.errors)

    else:
        # GET request
        report_form = InstructionReportForm(instance=report)
        initial_data = []
        lesson_objects = []

        for lesson in lessons:
            existing_score = LessonScore.objects.filter(report=report, lesson=lesson).first()
            initial_data.append({
                "lesson": lesson.id,
                "score": existing_score.score if existing_score else "",
            })
            lesson_objects.append(lesson)
        
        formset = LessonScoreSimpleFormSet(initial=initial_data)

        # Bundle each form with its lesson
        form_rows = list(zip(formset.forms, lesson_objects))


    return render(request, "instructors/fill_instruction_report.html", {
        "student": student,
        "report_form": report_form,
        "formset": formset,
        "form_rows": form_rows,
        "report_date": report_date,
    })


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
        logsheet__log_date__lte=today
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

def get_instructor_initials(member):
    initials = f"{member.first_name[0]}{member.last_name[0]}" if member.first_name and member.last_name else "??"
    return initials.upper()


def member_training_grid(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    reports = (
        InstructionReport.objects
        .filter(student=member)
        .order_by("report_date")
        .prefetch_related("lesson_scores__lesson", "instructor")
    )

    report_dates = [r.report_date for r in reports]
    lessons = TrainingLesson.objects.all().order_by("code")

    # Score lookup: (lesson_id, date) -> score
    scores_lookup = {
        (score.lesson_id, report.report_date): score.score
        for report in reports
        for score in report.lesson_scores.all()
    }

    # Flights per date for metadata
    all_flights = Flight.objects.filter(pilot=member, logsheet__log_date__in=report_dates).select_related("logsheet", "instructor")
    flights_by_date = defaultdict(list)
    today = now().date()

    for flight in all_flights:
        if not flight.instructor:
            continue
        log_date = flight.logsheet.log_date
        days_ago = (today - log_date).days
        initials = "".join([s[0] for s in flight.instructor.full_display_name.split() if s])
        #altitude = flight.release_altitude or ""
        flights_by_date[log_date].append({
            "days_ago": days_ago,
            "initials": initials,
            #"altitude": altitude,
            "full_name": flight.instructor.full_display_name,
        })

    # Build grid rows
    lesson_data = []
    for lesson in lessons:
        row = {
            "label": f"{lesson.code} – {lesson.title}",
            "phase": lesson.phase.name if lesson.phase else "Other",
            "scores": [],
            "max_score": ""
        }
        max_numeric = []
        altitudes=""

        for date_obj in report_dates:
            score = scores_lookup.get((lesson.id, date_obj), "")

            if score.isdigit():
                max_numeric.append(int(score))

            flights = flights_by_date.get(date_obj, [])
            if flights:
                #altitudes = " + ".join(str(f["altitude"]) for f in flights if f["altitude"])
                initials = flights[0]["initials"]
                tooltip = f"{flights[0]['full_name']} – {len(flights)} flight(s) – {flights[0]['days_ago']} days ago – {altitudes}"
                label = f"{initials}<br>{flights[0]['days_ago']}<br>{altitudes}"
            else:
                tooltip = ""
                label = ""

            row["scores"].append({
                "score": score,
                "tooltip": tooltip,
                "label": label,
            })

        row["max_score"] = str(max(max_numeric)) if max_numeric else ""
        lesson_data.append(row)

    # Build header info for each instruction date
    column_metadata = []
    for date_obj in report_dates:
        flights = flights_by_date.get(date_obj, [])
        if flights:
            initials = flights[0]['initials']
            days_ago = flights[0]['days_ago']
            #altitudes = " + ".join(str(f["altitude"]) for f in flights if f["altitude"])
        else:
            initials = ""
            days_ago = ""
            #altitudes = ""
        column_metadata.append({
            "date": date_obj,
            "initials": initials,
            "days_ago": days_ago,
            #"altitudes": altitudes,
        })

    context = {
        "member": member,
        "lesson_data": lesson_data,
        "report_dates": report_dates,
        "column_metadata": column_metadata,
    }

    return render(request, "shared/training_grid.html", context)
##########################################################

# instructors/views.py (partial)
@instructor_required
def log_ground_instruction(request):
    student_id = request.GET.get("student")
    student = get_object_or_404(Member, pk=student_id) if student_id else None

    lessons = TrainingLesson.objects.all().order_by("code")

    if request.method == "POST":
        #print("POST data:", request.POST)

        form = GroundInstructionForm(request.POST)
        formset = GroundLessonScoreFormSet(request.POST)
        formset.total_form_count()  # ✅ Critical for non-ModelForm formsets


        if form.is_valid() and formset.is_valid():
            session = form.save(commit=False)
            session.instructor = request.user
            session.student = student
            session.save()

            for form_data in formset.cleaned_data:
                lesson_id = form_data.get("lesson")
                score = form_data.get("score")
                if lesson_id and score:
                    lesson = TrainingLesson.objects.get(pk=lesson_id)
                    GroundLessonScore.objects.create(
                        session=session,
                        lesson=lesson,
                        score=score
                    )

            messages.success(request, "Ground instruction session logged successfully.")
            return redirect("instructors:member_instruction_record", member_id=student.id)
        else:
            #print("Form errors:", form.errors)
            #print("Formset errors:", formset.errors)
            messages.error(request, "Please correct the errors below.")
    else:
        form = GroundInstructionForm()
        initial_data = [{"lesson": lesson.id} for lesson in lessons]
        formset = GroundLessonScoreFormSet(initial=initial_data)

    form_rows = list(zip(formset.forms, lessons))

    return render(request, "instructors/log_ground_instruction.html", {
        "form": form,
        "formset": formset,
        "form_rows": form_rows,
        "student": student,
    })


def is_instructor(user):
    return user.is_authenticated and user.instructor

@active_member_required
@user_passes_test(is_instructor)
def assign_qualification(request, member_id):
    student = get_object_or_404(Member, pk=member_id)

    if request.method == 'POST':
        form = QualificationAssignForm(request.POST, instructor=request.user, student=student)
        if form.is_valid():
            form.save()
            return redirect('members:member_view', member_id=member_id)
    else:
        form = QualificationAssignForm(instructor=request.user, student=student)

    return render(request, 'instructors/assign_qualification.html', {
        'form': form,
        'student': student,
    })

@instructor_required
def instructors_home(request):
     return render(request, "instructors/instructors_home.html")

@instructor_required
def progress_dashboard(request):
    # 1) split “students” vs “rated” by glider_rating
    students_qs = (
        Member.objects
        .filter(
            membership_status__in=DEFAULT_ACTIVE_STATUSES,
            glider_rating='student'
        )
        .annotate(
            last_flight=Max('flights_as_pilot__logsheet__log_date'),
            report_count=Count('instruction_reports', distinct=True)
        )
        .order_by('last_name')
    )
    rated_qs = (
        Member.objects
        .filter(
            membership_status__in=DEFAULT_ACTIVE_STATUSES)
        .exclude(glider_rating='student')
        .annotate(
            last_flight=Max('flights_as_pilot__logsheet__log_date'),
            report_count=Count('instruction_reports', distinct=True)
        )
        .order_by('last_name')
    )

    # 2) figure out which lessons count for solo vs rating
    all_lessons = TrainingLesson.objects.all()
    solo_ids = {l.id for l in all_lessons if l.is_required_for_solo()}
    rating_ids = {l.id for l in all_lessons if l.is_required_for_private()}
    total_solo = len(solo_ids)
    total_rating = len(rating_ids)

    # 3) percentage helper
    def compute_progress(member):
        flight_done = set(
            LessonScore.objects
            .filter(report__student=member, score__in=['3','4'])
            .values_list('lesson_id', flat=True)
        )
        ground_done = set(
            GroundLessonScore.objects
            .filter(session__student=member, score__in=['3','4'])
            .values_list('lesson_id', flat=True)
        )
        completed = flight_done | ground_done

        solo_pct = int(len(completed & solo_ids) / total_solo * 100) if total_solo else 0
        rating_pct = int(len(completed & rating_ids) / total_rating * 100) if total_rating else 0
        return solo_pct, rating_pct

    # 4) build context lists
    students_data = []
    for m in students_qs:
        solo_pct, rating_pct = compute_progress(m)
        students_data.append({
            'member':      m,
            'report_count': m.report_count,      # ← pull in the annotated count
            'solo_pct':    solo_pct,
            'rating_pct':  rating_pct,
        })

    rated_data = []
    for m in rated_qs:
        solo_pct, rating_pct = compute_progress(m)
        rated_data.append({
            'member':      m,
            'report_count': m.report_count,
            'solo_pct':    solo_pct,
            'rating_pct':  rating_pct,
        })


    return render(request, 'instructors/progress_dashboard.html', {
        'students_data': students_data,
        'rated_data':   rated_data,
    })


@instructor_required
def edit_syllabus_document(request, slug):
    doc = get_object_or_404(SyllabusDocument, slug=slug)
    if request.method == 'POST':
        form = SyllabusDocumentForm(request.POST, instance=doc)
        if form.is_valid():
            form.save()
            messages.success(request, 'Syllabus document updated.')
            return redirect('instructors:syllabus_overview')
    else:
        form = SyllabusDocumentForm(instance=doc)

    return render(request, 'instructors/edit_syllabus_document.html', {
        'form': form,
        'doc': doc,
    })



def member_instruction_record(request, member_id):
    member = get_object_or_404(Member, pk=member_id)

    instruction_reports = (
        InstructionReport.objects
        .filter(student=member)
        .order_by("-report_date")
        .prefetch_related("lesson_scores__lesson")
    )

    ground_sessions = (
        GroundInstruction.objects
        .filter(student=member)
        .order_by("-date")
        .prefetch_related("lesson_scores__lesson")
    )

    # ── BUILD A TIMELINE OF ALL SESSIONS ──
    # 1) Grab all flight‐instruction reports and ground sessions
    flight_reports = list(
        InstructionReport.objects
            .filter(student=member)
            .order_by("report_date")
            .values_list("report_date", flat=True)
    )
    ground_reports = list(
        GroundInstruction.objects
            .filter(student=member)
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
        Flight.objects
        .filter(pilot=member, instructor__isnull=True)
        .order_by("logsheet__log_date")
        .values_list("logsheet__log_date", flat=True)
        .first()
    )
    first_solo_str = first_solo.strftime("%Y-%m-%d") if first_solo else ""

    # 5) Build the chart arrays
    chart_dates = []
    chart_solo = []
    chart_rating = []
    chart_anchors = []

    for sess in sessions:
        d = sess["date"]
        chart_dates.append(d.strftime("%Y-%m-%d"))
        chart_anchors.append(f"{sess['type']}-{d.strftime('%Y-%m-%d')}")
        # cumulative lesson_scores up to this date
        flight_done = set(
            LessonScore.objects
            .filter(report__student=member, report__report_date__lte=d, score__in=["3","4"])
            .values_list("lesson_id", flat=True)
        )
        ground_done = set(
            GroundLessonScore.objects
            .filter(session__student=member, session__date__lte=d, score__in=["3","4"])
            .values_list("lesson_id", flat=True)
        )
        completed = flight_done | ground_done
        chart_solo.append(int(len(completed & solo_ids) / total_solo * 100))
        chart_rating.append(int(len(completed & rating_ids) / total_rating * 100))




    blocks = []

    for report in instruction_reports:
        scores = report.lesson_scores.all()
        scores_by_code = defaultdict(list)

        for s in scores:
            #print("  - Score:", repr(s.score), "| Code:", repr(s.lesson.code))
            scores_by_code[str(s.score)].append(s.lesson.code)  # ✅ normalize as str

        flights = Flight.objects.filter(
            instructor=report.instructor,
            pilot=report.student,
            logsheet__log_date=report.report_date
        )
        scores_by_code = dict(scores_by_code)  # ✅ convert defaultdict to regular dict

        blocks.append({
            "type": "flight",
            "report": report,
            "days_ago": (timezone.now().date() - report.report_date).days,
            "flights": flights,
            "scores_by_code": scores_by_code,
        })

    for session in ground_sessions:
        scores_by_code = defaultdict(list)

        for s in session.lesson_scores.all():
            scores_by_code[str(s.score)].append(s.lesson.code)  # ✅ normalize as str

        scores_by_code = dict(scores_by_code)  # ✅ convert defaultdict to regular dict
        blocks.append({
            "type": "ground",
            "report": session,
            "days_ago": (timezone.now().date() - session.date).days,
            "flights": None,
            "scores_by_code": scores_by_code,
        })

    blocks.sort(
        key=lambda b: b["report"].report_date if b["type"] == "flight" else b["report"].date,
        reverse=True,
    )


    return render(request, "shared/member_instruction_record.html", {
        "member": member,
        "report_blocks": blocks,
        "chart_dates":     chart_dates,
        "chart_solo":      chart_solo,
        "chart_rating":    chart_rating,
        "chart_anchors":   chart_anchors,
        "first_solo_str":  first_solo_str,
        "chart_dates_json":   json.dumps(chart_dates),
        "chart_solo_json":    json.dumps(chart_solo),
        "chart_rating_json":  json.dumps(chart_rating),
        "chart_anchors_json": json.dumps(chart_anchors),

    })

