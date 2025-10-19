from django.contrib import admin
from django.utils.html import format_html

from logsheet.models import AircraftMeister, MaintenanceDeadline, MaintenanceIssue

from .models import (
    Airfield,
    Flight,
    Glider,
    Logsheet,
    LogsheetCloseout,
    LogsheetPayment,
    RevisionLog,
    Towplane,
    TowplaneCloseout,
    TowRate,
)
from utils.admin_helpers import AdminHelperMixin
from django.utils import timezone
from datetime import timedelta


class RecentLogsheetFilter(admin.SimpleListFilter):
    title = "By logsheet"
    parameter_name = "recent_logsheet"

    def lookups(self, request, model_admin):
        # Show logsheets from the last two years only
        two_years_ago = timezone.now().date() - timedelta(days=365 * 2)
        from .models import Logsheet

        qs = Logsheet.objects.filter(log_date__gte=two_years_ago).order_by("-log_date")
        return [(str(l.id), l.log_date.strftime("%Y-%m-%d")) for l in qs]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(logsheet_id=value)
        return queryset


# Admin configuration for managing Towplane objects
# Use this to add more club tow planes.
# Each time we have a new tow plane, we need to add an object
# with the admin interface here.
@admin.register(Towplane)
class TowplaneAdmin(AdminHelperMixin, admin.ModelAdmin):

    list_display = (
        "name",
        "n_number",
        "is_active",
        "oil_change_interval",
        "next_oil_change_due",
        "requires_100hr_inspection",
        "next_100hr_due",
    )
    list_filter = ("is_active", "requires_100hr_inspection")
    search_fields = ("name", "n_number")
    fieldsets = (
        (None, {"fields": ("name", "n_number", "is_active", "club_owned")}),
        ("Oil Change", {"fields": ("oil_change_interval", "next_oil_change_due")}),
        (
            "100hr Inspection",
            {"fields": ("requires_100hr_inspection", "next_100hr_due")},
        ),
    )

    def get_search_results(self, request, queryset, search_term):
        queryset = queryset.filter(is_active=True)
        return super().get_search_results(request, queryset, search_term)

    admin_helper_message = (
        "Towplanes: manage club tow planes and their inspection schedule. "
        "Only active planes are shown by default in search."
    )


# Admin configuration for Glider objects.
# Use this to add more gliders to the system.
# If a new glider is acquired by the club, we need to add it here.
# If a member gets a new glider, it also needs to be added here.
# If the rental rate for any of our gliders change, those updates need to go here.


@admin.register(Glider)
class GliderAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "competition_number",
        "n_number",
        "model",
        "make",
        "seats",
        "club_owned",
        "is_active",
        "requires_100hr_inspection",
        "next_100hr_due",
    )
    list_filter = ("is_active", "requires_100hr_inspection")
    search_fields = ("n_number", "competition_number", "make", "model")
    ordering = ("-is_active", "-club_owned", "-seats", "competition_number")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "competition_number",
                    "n_number",
                    "model",
                    "make",
                    "seats",
                    "club_owned",
                    "is_active",
                    "rental_rate",
                    "max_rental_rate",
                )
            },
        ),
        (
            "100hr Inspection",
            {"fields": ("requires_100hr_inspection", "next_100hr_due")},
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Show all gliders in the Django admin
        if request.path.startswith("/admin/"):
            return qs
        # Elsewhere (like in forms), only show club-owned gliders
        return qs.filter(club_owned=True)

    admin_helper_message = (
        "Gliders: record club and member gliders. Use club-owned filters when configuring rentals."
    )


# The flight table is where most of the action for the logsheet lives.
# This is a stop-gap to edit the database directly from the admin interface,
# used only when there is a problem with the app that we can't fix.
# This is kind of an ugly view in admin, because if we have a zillion flights,
# they're all going to be listed here. I don't have any better solutions.
@admin.register(Flight)
class FlightAdmin(AdminHelperMixin, admin.ModelAdmin):
    # Keep list display small and use select_related to avoid N+1 queries
    list_display = (
        "logsheet",
        "launch_time",
        "landing_time",
        "pilot",
        "instructor",
        "glider",
        "towplane",
        "tow_pilot",
        "tow_cost_actual",
        "rental_cost_actual",
    )
    # Filter by related fields that are indexed; avoid expensive filters on non-indexed text
    list_filter = ("logsheet", "glider", "towplane", "instructor")
    search_fields = (
        "pilot__first_name",
        "pilot__last_name",
        "instructor__first_name",
        "instructor__last_name",
    )
    readonly_fields = ("tow_cost", "rental_cost", "total_cost_display")

    # Reduce rows per page so the admin page renders faster with large tables
    list_per_page = 50

    # Show a date drill-down if admins want to quickly jump by log date
    date_hierarchy = "logsheet__log_date"

    # Use select_related for FK fields used in list_display to avoid extra queries
    list_select_related = ("logsheet", "pilot", "instructor",
                           "glider", "towplane", "tow_pilot")

    # list_select_related is sufficient here; Django will apply the necessary
    # select_related on the changelist queryset. Keeping an explicit
    # get_queryset with the identical select_related call is redundant.

    def tow_cost(self, obj):
        return obj.tow_cost_display

    def rental_cost(self, obj):
        return obj.rental_cost_display

    def total_cost_display(self, obj):
        return obj.total_cost_display

    admin_helper_message = (
        "Flights: low-level flight records for debugging or data fixes. Not used by the public site. "
        "See docs/admin/flights.md for guidance."
    )


# Each time a member locks a flight log because it's finalized, no more changes can be done
# to that flight log.  Of course, mistakes happen, and the log sheet needs to be revised.
# A superuser can unlock the finalized boolean to allow edits to that logsheet again.
# But each time that happens, a log entry gets added into this RevisionLog model.
# The admin mode is here in case you need to scrub or edit any of those.  Maybe this
# entry in admin.py shouldn't even exist?


@admin.register(RevisionLog)
class RevisionLogAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("logsheet", "revised_by", "revised_at")
    list_filter = ("revised_by", "revised_at")

    admin_helper_message = (
        "Revision logs: audit entries when finalized logs are unlocked. Edit with care."
    )


# Each time the club operates at a new field for the first time, it needs to be added here.
# When we start a logsheet for the day, we need to indicate the airfield where the operations take place.
# If we as a club are starting an op at a new airfield, we need to add it here first. This is the only place
# to add it.


@admin.register(Airfield)
class AirfieldAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ["identifier", "name", "is_active"]
    search_fields = ["identifier", "name"]
    list_filter = ["is_active"]
    readonly_fields = ["airfield_image_preview"]

    def airfield_image_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-height: 150px;" />', obj.photo.url
            )
        return "(No photo uploaded)"

    airfield_image_preview.short_description = "Current Photo"

    admin_helper_message = (
        "Airfields: add or update fields where ops take place. Upload a photo to preview here."
    )


# The particulars of what day a logsheet happened, the airfield, who is on the duty roster for that day
# are all kept in teh Logsheet model. If a logsheet is finalized is kept in this entry too.
# One manual way to unfinalize a logsheet (open it up fo revisions) is to just flip the boolean in this
# table with this admin interface.  This isn't ideal.


@admin.register(Logsheet)
class LogsheetAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("log_date", "airfield", "created_by", "finalized", "created_at")
    list_filter = ("airfield", "finalized")
    search_fields = ("airfield__name", "created_by__username")

    admin_helper_message = (
        "Logsheets: daily operation records. Finalizing a log locks it from edits."
    )


# The prices for tows to different altitudes are stored here.
# Currently all tows are at the same rate for all tow planes, which could be a
# problem in the future if we have some other tow plane come tow for us,
# and they charge different rates. I'll have to think about it.
# Also unfortunately, the prices are recorded in 100 feet increments, which is not very user-friendly.
# There is a script in the logsheet/management that allows you to paste the output into
# a `./manage.py shell` command


@admin.register(TowRate)
class TowRateAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("altitude", "price")
    list_editable = ("price",)
    ordering = ("altitude",)

    admin_helper_message = (
        "Tow rates: edit prices for tow altitudes. Prices are shown in the booking UI."
    )


# Admin configuration for LogsheetCloseout objects
# Allows viewing and managing closeout reports for each logsheet,
# including safety issues, equipment issues, and operations summaries.
# Primarily used for reference; not commonly edited after creation.


@admin.register(LogsheetCloseout)
class LogsheetCloseoutAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("logsheet",)

    admin_helper_message = (
        "Closeouts: end-of-day summaries and safety notes. Typically read-only."
    )


# Admin configuration for TowplaneCloseout objects
# Used to manage end-of-day tachometer readings, fuel logs,
# and operational notes for each towplane per logsheet.
# Tach times and fuel records are recorded here.


@admin.register(TowplaneCloseout)
class TowplaneCloseoutAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("logsheet", "towplane")

    admin_helper_message = (
        "Towplane closeouts: record tach times and fuel usage per logsheet."
    )


# Admin configuration for LogsheetPayment objects
# Displays and manages payment methods associated with each member's flight charges.
# Useful for tracking which members paid by account, check, Zelle, or cash.


@admin.register(LogsheetPayment)
class LogsheetPaymentAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "member",
        "logsheet",
        "payment_method",
        "note",
    )
    # Limit the 'By logsheet' filter to recent logs to avoid huge choice lists
    list_filter = ("payment_method", RecentLogsheetFilter)
    search_fields = ("member__first_name", "member__last_name", "note")
    autocomplete_fields = ("member", "logsheet")
    # Avoid N+1 queries for member/logsheet lookups in the changelist
    list_select_related = ("member", "logsheet")
    # If you have lots of payments, limit rows per page for faster responses
    list_per_page = 50

    # list_select_related on this admin avoids the need for a custom get_queryset.

    admin_helper_message = (
        "Payments: attach payment methods to charges. Use autocomplete for members and logsheets."
    )


# RecentLogsheetFilter is defined above so it can be referenced directly by LogsheetPaymentAdmin


# Admin configuration for MaintenanceIssue objects
# Manages maintenance issues reported against gliders and towplanes.
# Displays whether the issue is grounded, resolved, and a short description.
# Allows filtering by status and searching by aircraft or description.
# Also restricts glider and towplane choices to active club-owned aircraft.


@admin.register(MaintenanceIssue)
class MaintenanceIssueAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "aircraft_display",
        "is_glider",
        "grounded",
        "resolved",
        "report_date",
        "description_short",
    )
    search_fields = ("glider__n_number", "towplane__n_number", "description")
    list_filter = ("grounded", "resolved")
    autocomplete_fields = ("glider", "towplane", "reported_by", "resolved_by")
    readonly_fields = ("report_date",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "glider":
            from logsheet.models import Glider

            kwargs["queryset"] = Glider.objects.filter(is_active=True, club_owned=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def aircraft_display(self, obj):
        return obj.glider or obj.towplane

    aircraft_display.short_description = "Aircraft"

    def is_glider(self, obj):
        return bool(obj.glider)

    is_glider.boolean = True
    is_glider.short_description = "Glider?"

    def description_short(self, obj):
        return obj.description[:50] + ("..." if len(obj.description) > 50 else "")

    admin_helper_message = (
        "Maintenance issues: record faults for aircraft. Use the grounded flag to block aircraft."
    )


# Admin configuration for MaintenanceDeadline objects
# Displays upcoming maintenance deadlines for gliders and towplanes.
# Used to manage and track important inspections like annuals, transponders, and parachute repacks.
# Allows filtering and searching by aircraft and deadline type.


@admin.register(MaintenanceDeadline)
class MaintenanceDeadlineAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("aircraft_n_number", "aircraft_type", "description", "due_date")
    list_filter = ("description", "due_date")
    search_fields = ("glider__n_number", "towplane__n_number")

    autocomplete_fields = ("glider", "towplane")

    def aircraft_n_number(self, obj):
        return obj.glider.n_number if obj.glider else obj.towplane.n_number

    aircraft_n_number.short_description = "N-Number"

    def aircraft_type(self, obj):
        return "Glider" if obj.glider else "Towplane"

    aircraft_type.short_description = "Type"

    admin_helper_message = (
        "Maintenance deadlines: track inspections and important aircraft deadlines."
    )


# Admin configuration for AircraftMeister objects
# Assigns members as Meisters (responsible caretakers) for specific gliders or towplanes.
# Meisters are authorized to resolve maintenance issues for their assigned aircraft.
# Allows quick lookup by aircraft or member.


@admin.register(AircraftMeister)
class AircraftMeisterAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("aircraft_display", "member")
    search_fields = ("glider__n_number", "towplane__n_number", "member__username")
    autocomplete_fields = ("glider", "towplane", "member")

    def aircraft_display(self, obj):
        return obj.glider or obj.towplane

    aircraft_display.short_description = "Aircraft"

    admin_helper_message = (
        "Meisters: assign members as caretakers for aircraft. Use carefully; impacts maintenance workflows."
    )
