from django.contrib import admin
from .models import DutyDay, DutySlot, MemberBlackout

@admin.register(DutyDay)
class DutyDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'notes')
    search_fields = ('notes',)
    ordering = ('date',)

@admin.register(DutySlot)
class DutySlotAdmin(admin.ModelAdmin):
    list_display = ('duty_day', 'role', 'member')
    list_filter = ('role',)
    search_fields = ('member__first_name', 'member__last_name')
    autocomplete_fields = ('member', 'duty_day')
    ordering = ('duty_day', 'role')

@admin.register(MemberBlackout)
class MemberBlackoutAdmin(admin.ModelAdmin):
    list_display = ('member', 'date', 'note')
    search_fields = ('member__first_name', 'member__last_name', 'note')
    list_filter = ('date',)
    autocomplete_fields = ('member',)
    ordering = ('date',)
