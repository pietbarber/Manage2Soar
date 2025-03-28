from django.shortcuts import render
from members.decorators import active_member_required

@active_member_required
def index(request):
    return render(request, "logsheet/index.html")

@active_member_required
def create_logsheet(request):
    return render(request, "logsheet/start_logsheet.html")