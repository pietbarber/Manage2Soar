from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import SetPasswordForm
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.shortcuts import render, get_object_or_404, redirect
from .forms import MemberForm
from .forms import MemberProfilePhotoForm
from members.decorators import active_member_required
from .models import Member


def is_instructor(user):
    return user.is_authenticated and user.is_instructor

def home(request):
    return render(request, "home.html")

@active_member_required
def duty_roster(request):
    return render(request, 'members/duty_roster.html')

@active_member_required
@user_passes_test(is_instructor)
def instructors_only(request):
    return render(request, 'members/instructors.html')

@active_member_required
def members_list(request):
    return render(request, 'members/members.html')

@active_member_required
def log_sheets(request):
    return render(request, 'members/log_sheets.html')

@active_member_required
def member_list(request):
    members = Member.objects.order_by('last_name', 'first_name')
    return render(request, "members/member_list.html", {"members": members})

@active_member_required
def member_edit(request, pk):
    member = get_object_or_404(Member, pk=pk)

    if not (request.user.is_staff or request.user == member):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = MemberForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            return redirect("member_list")
        else:
            print("Form errors:", form.errors)  # 🔍 Debug!
    else:
        form = MemberForm(instance=member)
    print("FILES received:", request.FILES)
    return render(request, "members/member_edit.html", {"form": form})

from django.http import HttpResponse
from .utils.vcard_tools import generate_vcard_qr
import base64

@active_member_required
def member_view(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    is_self = request.user == member
    qr_png = generate_vcard_qr(member)
    qr_base64 = base64.b64encode(qr_png).decode('utf-8')
    can_edit = request.user == member or request.user.is_superuser

    if is_self and request.method == "POST":
        form = MemberProfilePhotoForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            return redirect("member_view", member_id=member.id)
    else:
        form = MemberProfilePhotoForm(instance=member) if is_self else None

    return render(request, "members/member_view.html", {
        "member": member,
        "qr_base64": qr_base64,
        "form": form,
        "is_self": is_self,
        "can_edit": can_edit
    })


def custom_permission_denied_view(request, exception=None):
    return render(request, "403.html", status=403)

from .models import Badge

@active_member_required
def badge_board(request):
    badges = Badge.objects.prefetch_related('memberbadge_set__member').order_by('order')
    return render(request, "members/badges.html", {"badges": badges})

@active_member_required

def set_password(request):
    if request.method == 'POST':
        form = SetPasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your password has been set. You can now log in with it.")
            return redirect('member_view', member_id=request.user.id)
    else:
        form = SetPasswordForm(user=request.user)
    return render(request, 'members/set_password.html', {'form': form})

# members/views.py

from .models import Biography
from .forms import BiographyForm

@active_member_required
def biography_view(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    biography, _ = Biography.objects.get_or_create(member=member)

    can_edit = request.user == member or request.user.is_superuser

    if request.method == "POST" and can_edit:
        form = BiographyForm(request.POST, request.FILES, instance=biography)
        if form.is_valid():
            form.save()
            return redirect("member_view", member_id=member.id)
    else:
        form = BiographyForm(instance=biography)

    return render(request, "members/biography.html", {
        "form": form,
        "biography": biography,
        "member": member,
        "can_edit": can_edit
    })

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import os
from django.conf import settings

@csrf_exempt
def tinymce_image_upload(request):
    if request.method == 'POST' and request.FILES.get('file'):
        upload = request.FILES['file']
        username = request.user.username or "anonymous"
        safe_username = "".join(c for c in username if c.isalnum() or c in ('-', '_')).rstrip()
        upload_dir = os.path.join(settings.MEDIA_ROOT, "biography", safe_username)
        os.makedirs(upload_dir, exist_ok=True)

        # Save file with original name
        file_path = os.path.join(upload_dir, upload.name)
        with open(file_path, 'wb+') as dest:
            for chunk in upload.chunks():
                dest.write(chunk)

        media_url = f"{settings.MEDIA_URL}biography/{safe_username}/{upload.name}"
        return JsonResponse({'location': media_url})

    return JsonResponse({'error': 'Invalid request'}, status=400)
