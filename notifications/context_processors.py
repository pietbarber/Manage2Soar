from .models import Notification


def _is_stale_overdue_spr_notification(notification, has_overdue_sprs):
    from instructors.utils import is_overdue_spr_notification_message

    if not is_overdue_spr_notification_message(notification.message):
        return False

    return not has_overdue_sprs


def notifications(request):
    if request.user.is_authenticated:
        from instructors.utils import (
            get_instructor_has_overdue_sprs,
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
            has_overdue_sprs = (
                get_instructor_has_overdue_sprs(request.user)
                if has_overdue_spr_notifications
                else False
            )

            notifications = [
                notification
                for notification in notifications
                if not _is_stale_overdue_spr_notification(
                    notification,
                    has_overdue_sprs,
                )
            ]
    else:
        notifications = []
    return {"notifications": notifications}
