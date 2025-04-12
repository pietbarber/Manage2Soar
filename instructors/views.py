from django.shortcuts import render
from .decorators import instructor_required
from .models import TrainingLesson, SyllabusDocument, TrainingPhase

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

from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelformset_factory
from django.utils.timezone import now
from .models import Member, InstructionReport, LessonScore, TrainingLesson
from .forms import InstructionReportForm, LessonScoreFormSet
from .decorators import instructor_required
from .forms import LessonScoreForm


@instructor_required
def fill_instruction_report(request, student_id):
    student = get_object_or_404(Member, pk=student_id)
    instructor = request.user
    report_date = now().date()

    report, created = InstructionReport.objects.get_or_create(
        student=student, instructor=instructor, report_date=report_date
    )

    LessonScoreFormSet = modelformset_factory(LessonScore, form=LessonScoreForm, extra=0)
    lessons = TrainingLesson.objects.all().order_by("code")

    if request.method == "POST":
        report_form = InstructionReportForm(request.POST, instance=report)
        formset = LessonScoreFormSet(request.POST, queryset=LessonScore.objects.filter(report=report))

        if report_form.is_valid() and formset.is_valid():
            report_form.save()
            scores = formset.save(commit=False)
            for score in scores:
                score.report = report
                score.save()
            return redirect("instructors:syllabus_overview")
    else:
        report_form = InstructionReportForm(instance=report)
        formset = LessonScoreFormSet(queryset=LessonScore.objects.filter(report=report))

    return render(request, "instructors/fill_instruction_report.html", {
        "student": student,
        "report_form": report_form,
        "formset": formset,
        "report_date": report_date,
    })