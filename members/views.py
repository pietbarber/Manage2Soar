from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .models import Member, Biography
from .forms import MemberForm, BiographyForm, SetPasswordForm
from .decorators import active_member_required
import io
import base64
import qrcode
from .utils.vcard_tools import generate_vcard_qr



@active_member_required
def member_list(request):
    members = Member.objects.order_by('last_name', 'first_name')
    return render(request, "members/member_list.html", {"members": members})

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

    # vCard + QR Code logic
    vcard_text = generate_vcard_qr(member)
    qr = qrcode.make(vcard_text)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    qr_png = buffer.getvalue()
    qr_base64 = base64.b64encode(qr_png).decode("utf-8")

    # biography editing permission
    is_owner_or_superuser = request.user == member or request.user.is_superuser
    biography = getattr(member, "biography", None)

    return render(
        request,
        "members/member_view.html",
        {
            "member": member,
            "qr_base64": qr_base64,
            "biography": biography,
            "can_edit_bio": is_owner_or_superuser,
        },
    )


@active_member_required
def badge_board(request):
    members = Member.objects.prefetch_related("badges")
    badges = set(b for m in members for b in m.badges.all())
    return render(request, "members/badges.html", {"members": members, "badges": badges})

@active_member_required
def biography_view(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    try:
        bio = member.biography
    except Biography.DoesNotExist:
        bio = None
    return render(request, "members/biography.html", {"member": member, "biography": bio})

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

