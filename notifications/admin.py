from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "created_at", "read", "dismissed")
    list_filter = ("read", "dismissed", "created_at")
    search_fields = ("user__username", "message")
