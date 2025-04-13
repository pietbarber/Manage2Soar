from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from .models import Member, Biography
from .forms import MemberForm, BiographyForm, SetPasswordForm
from .decorators import active_member_required
import base64
from .utils.vcard_tools import generate_vcard_qr
from .forms import MemberProfilePhotoForm
from django.core.paginator import Paginator
from members.constants.membership import DEFAULT_ACTIVE_STATUSES, STATUS_ALIASES
from django.db.models import Prefetch


def member_list(request):
    selected_statuses = request.GET.getlist("status")

    raw_statuses = request.GET.getlist("status")

    # If no status selected, default to "Active"
    if not raw_statuses:
        raw_statuses = ["active"]

    selected_statuses = []
    for s in raw_statuses:
        selected_statuses.extend(STATUS_ALIASES.get(s, [s]))

    members = Member.objects.filter(membership_status__in=selected_statuses)

    selected_roles = request.GET.getlist("role")
    if 'towpilot' in selected_roles:
        members = members.filter(towpilot=True)
    if 'instructor' in selected_roles:
        members = members.filter(instructor=True)
    if 'director' in selected_roles:
        members = members.filter(director=True)
    if 'dutyofficer' in selected_roles:
        members = members.filter(duty_officer=True)

    members = members.order_by("last_name", "first_name")

    paginator = Paginator(members, 150)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "members/member_list.html", {
        "page_obj": page_obj,
        "paginator": paginator,
        "members": page_obj.object_list,
        "selected_statuses": selected_statuses,
        "selected_roles": selected_roles,
    })

@active_member_required
def member_edit(request, pk):
    member = get_object_or_404(Member, pk=pk)
    if not request.user.is_staff and request.user != member.user:
        messages.error(request, "You do not have permission to edit this member.")
        return redirect('members:member_list')

    if request.method == "POST":
        form = MemberForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Member information updated.")
            return redirect('members:member_list')
    else:
        form = MemberForm(instance=member)

    return render(request, "members/member_edit.html", {"form": form, "member": member})



@active_member_required
def member_view(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    is_self = request.user == member
    can_edit = is_self or request.user.is_superuser
        # Biography logic (if you have one)
    biography = getattr(member, "biography", None)

    # QR code generation
    qr_png = generate_vcard_qr(member)
    qr_base64 = base64.b64encode(qr_png).decode("utf-8")


    if is_self and request.method == "POST":
        form = MemberProfilePhotoForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile photo updated.")
            return redirect("members:member_view", member_id=member.id)
    else:
        form = MemberProfilePhotoForm(instance=member) if is_self else None
    return render(
        request,
        "members/member_view.html",
        {
            "member": member,
            "qr_base64": qr_base64,
            "form": form,
            "is_self": is_self,
            "can_edit": can_edit,
            "biography": biography,
        },
    )


@active_member_required

def biography_view(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    biography, _ = Biography.objects.get_or_create(member=member)

    can_edit = request.user == member or request.user.is_superuser

    if request.method == "POST" and can_edit:
        form = BiographyForm(request.POST, request.FILES, instance=biography)
        if form.is_valid():
            form.save()
            return redirect("members:member_view", member_id=member.id)
    else:
        form = BiographyForm(instance=biography)

    return render(request, "members/biography.html", {
        "form": form,
        "biography": biography,
        "member": member,
        "can_edit": can_edit
    })
from django.shortcuts import render

def home(request):
    return render(request, "home.html")


@active_member_required
def duty_roster(request):
    return render(request, "members/duty_roster.html")

@active_member_required
def set_password(request):
    member = request.user
    if request.method == "POST":
        form = SetPasswordForm(request.POST)
        if form.is_valid():
            member.set_password(form.cleaned_data["new_password1"])
            member.save()
            messages.success(request, "Password changed successfully.")
            return redirect('members:member_list')
    else:
        form = SetPasswordForm()
    return render(request, "members/set_password.html", {"form": form})

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import os
from django.conf import settings

@csrf_exempt
def tinymce_image_upload(request):
    if request.method == 'POST' and request.FILES.get('file'):
        f = request.FILES['file']
        path = os.path.join(settings.MEDIA_ROOT, 'tinymce', f.name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb+') as destination:
            for chunk in f.chunks():
                destination.write(chunk)
        url = os.path.join(settings.MEDIA_URL, 'tinymce', f.name)
        return JsonResponse({'location': url})
    return JsonResponse({'error': 'Invalid request'}, status=400)

from .models import Badge, MemberBadge

@active_member_required
def badge_board(request):
    active_members = Member.objects.filter(membership_status__in=DEFAULT_ACTIVE_STATUSES)

    badges = Badge.objects.prefetch_related(
        Prefetch(
            'memberbadge_set',
            queryset=MemberBadge.objects.filter(
                member__in=active_members
            ).select_related('member').order_by('member__last_name', 'member__first_name'),
            to_attr='filtered_memberbadges'
        )
    ).order_by('order')

    return render(request, "members/badges.html", {
        "badges": badges
    })

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from instructors.models import InstructionReport, LessonScore, TrainingLesson

@active_member_required
def my_training_progress(request):
    member = request.user
    reports = InstructionReport.objects.filter(student=member).order_by("report_date").prefetch_related("lesson_scores__lesson")
    lessons = TrainingLesson.objects.all().order_by("code")

    report_dates = [r.report_date for r in reports]
    lesson_data = []

    for lesson in lessons:
        score_map = {}
        for report in reports:
            score = report.lesson_scores.filter(lesson=lesson).first()
            score_map[report.report_date] = score.score if score else ""

        max_score = max((s for s in score_map.values() if s.isdigit()), default="")
        lesson_data.append({
            "label": f"{lesson.code} – {lesson.title}",
            "scores": [score_map[d] for d in report_dates],
            "max_score": max_score
        })

    return render(request, "shared/training_grid.html", {
        "member": member,
        "lesson_data": lesson_data,
        "report_dates": report_dates,
    })
