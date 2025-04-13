from django.shortcuts import render
from .decorators import instructor_required
from .models import TrainingLesson, SyllabusDocument, TrainingPhase
from members.decorators import active_member_required


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

from django.shortcuts import render, get_object_or_404

@instructor_required
def syllabus_detail(request, code):
    lesson = get_object_or_404(TrainingLesson, code=code)
    return render(request, "instructors/syllabus_detail.html", {"lesson": lesson})


from datetime import datetime
from collections import defaultdict
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.utils.timezone import now
from django.http import HttpResponseBadRequest
from django.forms import formset_factory

from instructors.decorators import instructor_required
from instructors.forms import InstructionReportForm, LessonScoreSimpleForm, LessonScoreSimpleFormSet
from instructors.models import InstructionReport, LessonScore, TrainingLesson
from members.models import Member

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
            print("Report form errors:", report_form.errors)
            print("Formset errors:", formset.errors)

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


from django.shortcuts import render, get_object_or_404
from logsheet.models import Flight, Logsheet
from members.models import Member
from datetime import timedelta
from django.utils import timezone
from collections import defaultdict
from datetime import timedelta

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

from django.shortcuts import get_object_or_404, render
from instructors.models import InstructionReport, LessonScore, TrainingLesson
from members.models import Member
from collections import defaultdict

from datetime import date
from django.utils.timezone import now
from collections import defaultdict
from members.models import Member
from logsheet.models import Flight


def get_instructor_initials(member):
    initials = f"{member.first_name[0]}{member.last_name[0]}" if member.first_name and member.last_name else "??"
    return initials.upper()

from django.utils.timezone import now
from collections import defaultdict
from django.shortcuts import get_object_or_404, render
from .models import InstructionReport, LessonScore, TrainingLesson
from logsheet.models import Flight

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

# instructors/views.py

from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from collections import defaultdict
from instructors.decorators import member_or_instructor_required
from instructors.models import InstructionReport, LessonScore
from logsheet.models import Flight
from members.models import Member

@member_or_instructor_required
def member_instruction_record(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    today = now().date()

    reports = (
        InstructionReport.objects
        .filter(student=member)
        .order_by("-report_date")
        .prefetch_related("lesson_scores__lesson", "instructor")
    )

    # Map report_date -> list of flights
    flights_by_date = defaultdict(list)
    all_flights = (
        Flight.objects
        .filter(pilot=member)
        .select_related("logsheet", "glider", "instructor")
    )

    for flight in all_flights:
        log_date = flight.logsheet.log_date if flight.logsheet else None
        if not log_date:
            continue
        flights_by_date[log_date].append(flight)

    # Organize report blocks
    report_blocks = []
    for report in reports:
        scores_by_code = defaultdict(list)
        for score in report.lesson_scores.all():
            scores_by_code[score.score].append(score.lesson.code)

        # Group flights for this day
        flights = flights_by_date.get(report.report_date, [])
        flights.sort(key=lambda f: f.launch_time or f.id)

        days_ago = (today - report.report_date).days

        report_blocks.append({
            "report": report,
            "scores_by_code": dict(scores_by_code),
            "flights": flights,
            "days_ago": days_ago,
        })

    context = {
        "member": member,
        "report_blocks": report_blocks,
    }
    return render(request, "shared/member_instruction_record.html", context)

# instructors/views.py (partial)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required

from instructors.forms import GroundInstructionForm, GroundLessonScoreFormSet
from instructors.models import GroundInstruction, GroundLessonScore, TrainingLesson
from instructors.decorators import instructor_required
from members.models import Member

@instructor_required
def log_ground_instruction(request):
    student_id = request.GET.get("student")
    student = get_object_or_404(Member, pk=student_id) if student_id else None

    lessons = TrainingLesson.objects.all().order_by("code")

    if request.method == "POST":
        print("POST data:", request.POST)

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
            print("Form errors:", form.errors)
            print("Formset errors:", formset.errors)
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
