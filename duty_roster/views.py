from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from .models import MemberBlackout
from .forms import MemberBlackoutForm
from members.decorators import active_member_required

# Create your views here.
from django.http import HttpResponse

def roster_home(request):
    return HttpResponse("Duty Roster Home")


@active_member_required
def blackout_manage(request):
    member = request.user
    existing = MemberBlackout.objects.filter(member=member)

    if request.method == "POST":
        form = MemberBlackoutForm(request.POST, member=member)
        if form.is_valid():
            form.save()
            return redirect("duty_roster:blackout_manage")
    else:
        form = MemberBlackoutForm(member=member)

    return render(request, "duty_roster/blackout_manage.html", {
        "form": form,
        "existing": existing,
        "today": now().date(),
    })
