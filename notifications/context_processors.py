from .models import Notification


def _is_stale_overdue_spr_notification(notification, overdue_spr_count):
    from instructors.utils import (
        is_overdue_spr_notification_message,
    )

    if not is_overdue_spr_notification_message(notification.message):
        return False

    return overdue_spr_count == 0


def notifications(request):
    if request.user.is_authenticated:
        from instructors.utils import (
            get_instructor_overdue_spr_count,
            is_overdue_spr_notification_message,
        )

        notifications_qs = Notification.objects.filter(
            user=request.user, dismissed=False
        ).order_by("-created_at")

        notifications = list(notifications_qs)
        if notifications:
            has_overdue_spr_notifications = any(
                is_overdue_spr_notification_message(notification.message)
                for notification in notifications
            )
            overdue_spr_count = (
                get_instructor_overdue_spr_count(request.user)
                if has_overdue_spr_notifications
                else None
            )

            notifications = [
                notification
                for notification in notifications
                if not _is_stale_overdue_spr_notification(
                    notification,
                    overdue_spr_count,
                )
            ]
    else:
        notifications = []
    return {"notifications": notifications}
