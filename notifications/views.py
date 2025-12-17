from django.shortcuts import get_object_or_404, redirect, render

from members.decorators import active_member_required
from utils.security import get_safe_redirect_url

from .models import Notification


@active_member_required
def notifications_list(request):
    notifications = Notification.objects.filter(
        user=request.user, dismissed=False
    ).order_by("-created_at")
    return render(
        request,
        "notifications/notifications_list.html",
        {"notifications": notifications},
    )


@active_member_required
def dismiss_notification(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.dismissed = True
    notification.save()
    # Validate referer header to prevent open redirect attacks
    referer = request.headers.get("referer")
    return redirect(get_safe_redirect_url(referer, default="/", request=request))
