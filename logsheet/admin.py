from django.contrib import admin
from .models import Glider, Towplane, Logsheet, Flight, RevisionLog


@admin.register(Towplane)
class TowplaneAdmin(admin.ModelAdmin):
    list_display = ("name", "registration", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "registration")

from django.contrib import admin
from .models import Glider

@admin.register(Glider)
class GliderAdmin(admin.ModelAdmin):
    list_display = ("competition_number", "n_number", "model", "make", "seats")
    search_fields = ("competition_number", "n_number", "model", "make")

@admin.register(Logsheet)
class LogsheetAdmin(admin.ModelAdmin):
    list_display = ("log_date", "location", "created_by", "created_at", "finalized")
    list_filter = ("finalized", "location")
    search_fields = ("location", "created_by__username")

@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = ("logsheet", "launch_time", "landing_time", "pilot", "instructor", "glider", "towplane", "tow_pilot")
    list_filter = ("logsheet", "glider", "towplane", "instructor")
    search_fields = ("pilot__first_name", "pilot__last_name", "instructor__first_name", "instructor__last_name")

@admin.register(RevisionLog)
class RevisionLogAdmin(admin.ModelAdmin):
    list_display = ("logsheet", "revised_by", "revised_at")
    list_filter = ("revised_by", "revised_at")
