from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render

def is_instructor(user):
    return user.is_authenticated and user.is_instructor

@login_required
def duty_roster(request):
    return render(request, 'members/duty_roster.html')

@login_required
@user_passes_test(is_instructor)
def instructors_only(request):
    return render(request, 'members/instructors.html')

@login_required
def members_list(request):
    return render(request, 'members/members.html')

@login_required
def log_sheets(request):
    return render(request, 'members/log_sheets.html')

