from django.contrib import admin
from .models import Towplane

@admin.register(Towplane)
class TowplaneAdmin(admin.ModelAdmin):
    list_display = ("name", "registration", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "registration")
