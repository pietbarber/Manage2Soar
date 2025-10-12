from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import Notification


@login_required
def notifications_list(request):
    notifications = Notification.objects.filter(
        user=request.user, dismissed=False).order_by('-created_at')
    return render(request, 'notifications/notifications_list.html', {'notifications': notifications})


@login_required
def dismiss_notification(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.dismissed = True
    notification.save()
    return redirect(request.META.get('HTTP_REFERER', '/'))
