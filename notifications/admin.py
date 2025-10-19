from django.contrib import admin

from .models import Notification
from utils.admin_helpers import AdminHelperMixin


@admin.register(Notification)
class NotificationAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("user", "message_short", "created_at", "read", "dismissed")
    list_filter = ("read", "dismissed")
    search_fields = ("user__username", "message")
    list_select_related = ("user",)
    list_per_page = 50
    date_hierarchy = "created_at"

    def message_short(self, obj):
        return (obj.message[:100] + "...") if obj.message and len(obj.message) > 100 else obj.message

    message_short.short_description = "Message"

    # Short admin helper pointing to notifications docs if needed
    admin_helper_message = (
        "Notifications: system messages for users. Use filters to find unread or dismissed items."
    )
    # admin_helper_doc_url = "/docs/admin/notifications.md"
