from django.shortcuts import render
from members.decorators import active_member_required

@active_member_required
def index(request):
    return render(request, "logsheet/index.html")

from django.shortcuts import render, redirect
from .forms import CreateLogsheetForm
from .models import Logsheet
from django.contrib import messages

@active_member_required
def manage_logsheet(request, pk):
    return render(request, "logsheet/logsheet_manage.html", {
        "logsheet_id": pk
    })

@active_member_required
def create_logsheet(request):
    if request.method == "POST":
        form = CreateLogsheetForm(request.POST)
        if form.is_valid():
            logsheet = form.save(commit=False)
            logsheet.created_by = request.user  # Assuming request.user is linked to Member
            logsheet.save()
            messages.success(request, f"Logsheet created for {logsheet.log_date} at {logsheet.location}")
            return redirect("logsheet:manage", pk=logsheet.pk)  # Placeholder: needs a real manage view
    else:
        form = CreateLogsheetForm()

    return render(request, "logsheet/start_logsheet.html", {"form": form})

from django.shortcuts import get_object_or_404
from .models import Logsheet

@active_member_required
def manage_logsheet(request, pk):
    logsheet = get_object_or_404(Logsheet, pk=pk)
    return render(request, "logsheet/logsheet_manage.html", {
        "logsheet": logsheet,
    })

