from django.shortcuts import render
from .decorators import instructor_required
from .models import TrainingLesson

# instructors/views.py
@instructor_required
def instructors_home(request):
    return render(request, "instructors/instructors_home.html")


@instructor_required
def syllabus_overview(request):
    lessons = TrainingLesson.objects.all().order_by("code")
    return render(request, "instructors/syllabus_overview.html", {"lessons": lessons})
