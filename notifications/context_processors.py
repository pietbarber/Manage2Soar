from .models import Notification


def _is_stale_overdue_spr_notification(user, notification):
    from instructors.utils import (
        get_instructor_overdue_spr_count,
        is_overdue_spr_notification_message,
    )

    if not is_overdue_spr_notification_message(notification.message):
        return False

    return get_instructor_overdue_spr_count(user) == 0


def notifications(request):
    if request.user.is_authenticated:
        notifications_qs = Notification.objects.filter(
            user=request.user, dismissed=False
        ).order_by("-created_at")

        notifications = list(notifications_qs)
        if notifications:
            notifications = [
                notification
                for notification in notifications
                if not _is_stale_overdue_spr_notification(request.user, notification)
            ]
    else:
        notifications = []
    return {"notifications": notifications}
