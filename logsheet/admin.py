from django.contrib import admin
from .models import Glider, Towplane, Logsheet, Flight, RevisionLog
from django.utils.html import format_html


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


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = ("logsheet", "launch_time", "landing_time", "pilot", "instructor", 
                    "glider", "towplane", "tow_pilot", "tow_cost_actual", "rental_cost_actual")
    list_filter = ("logsheet", "glider", "towplane", "instructor")
    search_fields = ("pilot__first_name", "pilot__last_name", "instructor__first_name", "instructor__last_name")
    readonly_fields = ("tow_cost", "rental_cost", "total_cost_display")
    def tow_cost(self, obj):
        return obj.tow_cost_display

    def rental_cost(self, obj):
        return obj.rental_cost_display

    def total_cost_display(self, obj):
        return obj.total_cost_display

@admin.register(RevisionLog)
class RevisionLogAdmin(admin.ModelAdmin):
    list_display = ("logsheet", "revised_by", "revised_at")
    list_filter = ("revised_by", "revised_at")


from .models import Airfield
@admin.register(Airfield)
class AirfieldAdmin(admin.ModelAdmin):
    list_display = ['identifier', 'name', 'is_active']
    search_fields = ['identifier', 'name']
    list_filter = ['is_active']
    readonly_fields = ['airfield_image_preview']

    def airfield_image_preview(self, obj):
        if obj.photo:
            return format_html('<img src="{}" style="max-height: 150px;" />', obj.photo.url)
        return "(No photo uploaded)"
    airfield_image_preview.short_description = "Current Photo"

    from .models import Logsheet

@admin.register(Logsheet)
class LogsheetAdmin(admin.ModelAdmin):
    list_display = ("log_date", "airfield", "created_by", "finalized", "created_at")
    list_filter = ("airfield", "finalized")
    search_fields = ("airfield__name", "created_by__username")

from django.contrib import admin
from .models import TowRate

@admin.register(TowRate)
class TowRateAdmin(admin.ModelAdmin):
    list_display = ("altitude", "price")
    list_editable = ("price",)
    ordering = ("altitude",)
