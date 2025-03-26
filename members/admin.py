from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Member
from tinymce.widgets import TinyMCE
from django.db import models
from .models import Badge
from django.utils.html import format_html


class BadgeAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.TextField: {'widget': TinyMCE(attrs={'cols': 80, 'rows': 10})},
    }

admin.site.register(Badge, BadgeAdmin)

@admin.register(Member)
class MemberAdmin(UserAdmin):
    model = Member
    list_display = ("username", "email", "is_staff", "is_active")


from .models import Glider

@admin.register(Glider)
class GliderAdmin(admin.ModelAdmin):
    list_display = ('n_number', 'make', 'model', 'number_of_seats', 'rental_rate')
    search_fields = ('n_number', 'make', 'model', 'competition_number')

from .models import Badge, MemberBadge

admin.site.register(MemberBadge)

from django.contrib import admin
from .models import FlightLog, Towplane

@admin.register(Towplane)
class TowplaneAdmin(admin.ModelAdmin):
    list_display = ['name', 'registration', 'is_active']
    search_fields = ['name', 'registration']
    list_filter = ['is_active']
    readonly_fields = ['towplane_image_preview']

    def towplane_image_preview(self, obj):
        if obj.picture:
            return format_html('<img src="{}" style="max-height: 150px;" />', obj.picture.url)
        return "(No image uploaded)"
    towplane_image_preview.short_description = "Current Image"


@admin.register(FlightLog)
class FlightLogAdmin(admin.ModelAdmin):
    list_display = ['flight_date', 'pilot', 'glider', 'takeoff_time', 'landing_time', 'field']
    list_filter = ['flight_date', 'field', 'glider']
    search_fields = ['pilot__username', 'glider__n_number']
    autocomplete_fields = ['pilot', 'passenger', 'instructor', 'towpilot', 'glider', 'towplane', 'alternate_payer']

