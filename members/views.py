from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .models import Member, Biography
from .forms import MemberForm, BiographyForm, SetPasswordForm
from .decorators import active_member_required
import base64
from .utils.vcard_tools import generate_vcard_qr
from .forms import MemberProfilePhotoForm
from django.core.paginator import Paginator



def member_list(request):
    selected_statuses = request.GET.getlist("status")

    DEFAULT_ACTIVE_STATUSES = [
        "Charter Member",           # Article IV 1 (a)
        "Full Member",              # Article IV 1 (b)
        "Probationary Member",      # Article IV 1 (c)
        "FAST Member",              # Article IV 1 (d)(i)
        "Introductory Member",      # Article IV 1 (d)(ii)
        "Affiliate Member",         # Article IV 1 (d)(iii)
        "Family Member",            # Article IV 1 (d)(iv)
        "Service Member",           # Article IV 1 (d)(v)
        "Student Member",           # Article IV 1 (d)(vi)
        "Transient Member",         # Article IV 1 (d)(vii)
        "Emeritus Member",          # Article IV 1 (d)(ix)
        "Honorary Member",          # Article IV 1 (d)(x)
    ]

    if not selected_statuses:
        selected_statuses = ["Active", "Inactive", "Pending", "Non-Member"]
    if not selected_statuses:
        selected_statuses = DEFAULT_ACTIVE_STATUSES

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
def badge_board(request):
    members = Member.objects.prefetch_related("badges")
    badges = set(b for m in members for b in m.badges.all())
    return render(request, "members/badges.html", {"members": members, "badges": badges})


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

from .models import Badge

@active_member_required
def badge_board(request):
    badges = Badge.objects.prefetch_related('memberbadge_set__member').order_by('order')
    return render(request, "members/badges.html", {"badges": badges})



