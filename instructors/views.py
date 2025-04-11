from django.shortcuts import render
from instructors.decorators import instructor_required

# instructors/views.py
@instructor_required
def instructors_home(request):
    return render(request, "instructors/instructors_home.html")
