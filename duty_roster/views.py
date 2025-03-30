from django.shortcuts import render
from members.decorators import active_member_required



@active_member_required
def index(request):
    return render(request, "duty_roster/index.html")
