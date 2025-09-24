from django.contrib import admin
from .models import SiteConfiguration


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # Only allow adding if no config exists
        return not SiteConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion
        return False

    def has_change_permission(self, request, obj=None):
        # Only allow Webmaster (superuser or group) to edit
        return request.user.is_superuser or request.user.groups.filter(name='Webmaster').exists()

    readonly_fields = ()
    fieldsets = (
        (None, {
            'fields': (
                'club_name', 'domain_name', 'club_abbreviation', 'club_logo', 'club_nickname',
                'schedule_instructors', 'schedule_tow_pilots', 'schedule_duty_officers', 'schedule_assistant_duty_officers',
                'duty_officer_title', 'assistant_duty_officer_title', 'membership_manager_title', 'equipment_manager_title',
                'allow_glider_reservations', 'allow_two_seater_reservations',
                'extra_config',
            )
        }),
    )
