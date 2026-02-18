import logging
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.crypto import get_random_string
from tinymce.models import HTMLField

from utils.favicon import generate_favicon_from_logo
from utils.upload_entropy import upload_site_logo


class MailingListCriterion(models.TextChoices):
    """Available criteria for mailing list membership."""

    # Active member status (the base criterion)
    ACTIVE_MEMBER = "active_member", "Active Member"

    # Club roles from Member model boolean fields
    INSTRUCTOR = "instructor", "Instructor"
    TOWPILOT = "towpilot", "Tow Pilot"
    DUTY_OFFICER = "duty_officer", "Duty Officer"
    ASSISTANT_DUTY_OFFICER = "assistant_duty_officer", "Assistant Duty Officer"

    # Board & management roles
    DIRECTOR = "director", "Director"
    SECRETARY = "secretary", "Secretary"
    TREASURER = "treasurer", "Treasurer"
    WEBMASTER = "webmaster", "Webmaster"
    MEMBER_MANAGER = "member_manager", "Member Manager"
    ROSTERMEISTER = "rostermeister", "Rostermeister"
    SAFETY_OFFICER = "safety_officer", "Safety Officer"

    # Special computed criteria
    PRIVATE_GLIDER_OWNER = "private_glider_owner", "Private Glider Owner"


class MailingList(models.Model):
    """
    Configurable mailing list definitions for the club email system.

    Each mailing list has a name (e.g., "instructors", "board")
    and one or more criteria that determine who should be subscribed.
    Members matching ANY of the criteria are included (OR logic).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier for this list (e.g., 'instructors', 'board')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this mailing list's purpose",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive lists are not included in API responses",
    )
    bypass_whitelist = models.BooleanField(
        default=False,
        help_text="Allow this list to receive mail from ANYONE, not just whitelisted "
        "senders (still requires SPF PASS). Use for service accounts like treasurer@ "
        "or webmaster@ that need to receive verification emails from external services.",
    )
    criteria = models.JSONField(
        default=list,
        help_text="List of criteria codes that determine membership (OR logic)",
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        help_text="Sort order for display in admin (lower numbers first)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mailing List"
        verbose_name_plural = "Mailing Lists"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        """Validate that criteria contains valid criterion codes."""
        # Reject empty criteria - a mailing list must have at least one criterion
        if not self.criteria:
            raise ValidationError("At least one criterion must be selected.")

        valid_codes = {c[0] for c in MailingListCriterion.choices}
        invalid = [c for c in self.criteria if c not in valid_codes]
        if invalid:
            raise ValidationError(f"Invalid criteria codes: {', '.join(invalid)}")

    def get_criteria_display(self):
        """Return human-readable list of criteria."""
        criterion_map = dict(MailingListCriterion.choices)
        return [criterion_map.get(c, c) for c in self.criteria]

    def get_subscribers(self):
        """
        Return queryset of Member objects matching this list's criteria.
        Uses OR logic - members matching ANY criterion are included.
        """
        from members.models import Member

        if not self.criteria:
            return Member.objects.none()

        # Cache active statuses for all criteria (avoid repeated DB queries)
        active_statuses = list(MembershipStatus.get_active_statuses())

        # Build OR query for all criteria
        query = Q()
        for criterion in self.criteria:
            query |= self._criterion_to_query(criterion, active_statuses)

        return (
            Member.objects.filter(query).distinct().order_by("last_name", "first_name")
        )

    def _criterion_to_query(self, criterion, active_statuses):
        """Convert a criterion code to a Django Q object."""
        # Base filter: only active members with non-empty email addresses
        # Note: is_active=True is included for defensive programming since
        # Member.save() auto-syncs is_active with membership_status, but
        # edge cases (manual DB updates, signal failures) could cause drift.
        base_active = (
            Q(membership_status__in=active_statuses)
            & Q(is_active=True)
            & ~Q(email="")
            & ~Q(email__isnull=True)
        )

        if criterion == MailingListCriterion.ACTIVE_MEMBER:
            return base_active

        # Boolean role fields on Member model
        boolean_fields = {
            MailingListCriterion.INSTRUCTOR: "instructor",
            MailingListCriterion.TOWPILOT: "towpilot",
            MailingListCriterion.DUTY_OFFICER: "duty_officer",
            MailingListCriterion.ASSISTANT_DUTY_OFFICER: "assistant_duty_officer",
            MailingListCriterion.DIRECTOR: "director",
            MailingListCriterion.SECRETARY: "secretary",
            MailingListCriterion.TREASURER: "treasurer",
            MailingListCriterion.WEBMASTER: "webmaster",
            MailingListCriterion.MEMBER_MANAGER: "member_manager",
            MailingListCriterion.ROSTERMEISTER: "rostermeister",
            MailingListCriterion.SAFETY_OFFICER: "safety_officer",
        }

        if criterion in boolean_fields:
            field = boolean_fields[criterion]
            return base_active & Q(**{field: True})

        if criterion == MailingListCriterion.PRIVATE_GLIDER_OWNER:
            # Members who own active private (non-club-owned) gliders
            return base_active & Q(
                gliders_owned__isnull=False,
                gliders_owned__club_owned=False,
                gliders_owned__is_active=True,
            )

        return Q(pk__in=[])  # No matches for unknown criteria

    def get_subscriber_emails(self):
        """Return list of email addresses for all subscribers."""
        return list(self.get_subscribers().values_list("email", flat=True))

    def get_subscriber_count(self):
        """Return count of subscribers to this list."""
        return self.get_subscribers().count()


class SiteConfiguration(models.Model):
    club_name = models.CharField(max_length=200)
    domain_name = models.CharField(
        max_length=200, help_text="Primary domain name (e.g. example.org)"
    )
    canonical_url = models.URLField(
        max_length=255,
        blank=True,
        help_text=(
            "Canonical URL for all outbound email links (e.g., https://www.skylinesoaring.org). "
            "This ensures consistent URLs in emails regardless of which domain users access. "
            "Do NOT include trailing slash. Leave blank to use SITE_URL environment variable."
        ),
        verbose_name="Canonical Email URL",
    )
    club_abbreviation = models.CharField(
        max_length=20, help_text="Short abbreviation (e.g. SSS)"
    )
    club_logo = models.ImageField(upload_to=upload_site_logo, blank=True, null=True)
    club_nickname = models.CharField(
        max_length=40, blank=True, help_text="Nickname or short name (e.g. Skyline)"
    )

    # Contact information
    contact_welcome_text = models.TextField(
        blank=True,
        default="Interested in learning to fly gliders? Have questions about our club? We'd love to hear from you! Fill out the form below and one of our member managers will get back to you soon.",
        help_text="Welcome text displayed on the contact form page",
    )
    contact_response_info = models.TextField(
        blank=True,
        default="Our member managers will receive your message immediately\nWe typically respond within 24-48 hours\nFor urgent questions, feel free to visit us at the airfield during operations\nAll contact information is kept private and not shared with third parties",
        help_text="Information about what happens after contact form submission (one item per line)",
    )

    # Club location
    club_address_line1 = models.CharField(
        max_length=100, blank=True, help_text="Street address line 1"
    )
    club_address_line2 = models.CharField(
        max_length=100, blank=True, help_text="Street address line 2 (optional)"
    )
    club_city = models.CharField(max_length=50, blank=True, help_text="City")
    club_state = models.CharField(max_length=50, blank=True, help_text="State/Province")
    club_zip_code = models.CharField(
        max_length=20, blank=True, help_text="ZIP/Postal code"
    )
    club_country = models.CharField(
        max_length=50, blank=True, default="USA", help_text="Country"
    )

    # Contact methods
    club_phone = models.CharField(
        max_length=20, blank=True, help_text="Main club phone number (optional)"
    )
    operations_info = models.TextField(
        blank=True,
        default="We typically fly on weekends and some weekdays when weather permits. Check our calendar or contact us for current schedule information.",
        help_text="Information about club operations schedule",
    )

    # Scheduling options
    schedule_instructors = models.BooleanField(
        default=False, help_text="We schedule Instructors ahead of time"
    )
    schedule_tow_pilots = models.BooleanField(
        default=False, help_text="We schedule tow pilots ahead of time"
    )
    schedule_duty_officers = models.BooleanField(
        default=False, help_text="We schedule Duty Officers ahead of time"
    )
    schedule_assistant_duty_officers = models.BooleanField(
        default=False, help_text="We schedule Assistant Duty Officers ahead of time"
    )
    use_ortools_scheduler = models.BooleanField(
        default=False,
        verbose_name="Use OR-Tools Scheduler",
        help_text=(
            "Use OR-Tools constraint programming scheduler instead of legacy weighted-random algorithm. "
            "OR-Tools provides globally optimal solutions, deterministic output, and better constraint handling. "
            "Disable this flag to instantly roll back to legacy scheduler if needed."
        ),
    )

    # Duty Roster Announcement (Issue #333) - DEPRECATED as of Issue #551
    # Use DutyRosterMessage model in duty_roster app instead for rich HTML support
    duty_roster_announcement = models.TextField(
        blank=True,
        default="",
        help_text="DEPRECATED: Use the new Duty Roster Message editor at /duty_roster/message/edit/ instead. "
        "This field will be removed in a future release.",
    )

    # Terminology (customizable titles for all roles)
    duty_officer_title = models.CharField(
        max_length=40,
        default="Duty Officer",
        help_text="We refer to the position of Duty Officer as ...",
    )
    assistant_duty_officer_title = models.CharField(
        max_length=40,
        default="Assistant Duty Officer",
        help_text="We refer to the position of Assistant Duty Officer as ...",
    )
    towpilot_title = models.CharField(
        max_length=40,
        default="Tow Pilot",
        help_text="We refer to the position of Tow Pilot as ...",
    )
    surge_towpilot_title = models.CharField(
        max_length=40,
        default="Surge Tow Pilot",
        blank=True,
        help_text="We refer to the position of Surge Tow Pilot as ... (optional)",
    )
    instructor_title = models.CharField(
        max_length=40,
        default="Instructor",
        help_text="We refer to the position of Instructor as ...",
    )
    surge_instructor_title = models.CharField(
        max_length=40,
        default="Surge Instructor",
        blank=True,
        help_text="We refer to the position of Surge Instructor as ... (optional)",
    )

    # Surge thresholds (Issue #403)
    # Note: Both thresholds trigger AT or ABOVE the specified value (e.g., threshold=4 triggers at 4+)
    # This makes both thresholds semantically consistent. Previously, instruction used > 3 (triggering
    # at 4+), while tow used >= 6. Now both use >= logic for clarity and consistency.
    tow_surge_threshold = models.PositiveIntegerField(
        default=6,
        help_text="Surge alerts trigger when tow requests are AT or ABOVE this value (default: 6)",
    )
    instruction_surge_threshold = models.PositiveIntegerField(
        default=4,
        help_text="Surge alerts trigger when instruction requests are AT or ABOVE this value (default: 4)",
    )

    membership_manager_title = models.CharField(
        max_length=40,
        default="Membership Manager",
        help_text="We refer to the person who manages the membership as ...",
    )
    equipment_manager_title = models.CharField(
        max_length=40,
        default="Equipment Manager",
        help_text="We refer to the person who manages the equipment as ...",
    )

    # Reservation options
    allow_glider_reservations = models.BooleanField(
        default=False,
        help_text="We allow members to reserve club gliders ahead of time.",
    )
    allow_two_seater_reservations = models.BooleanField(
        default=False,
        help_text="We allow members to reserve club two seaters ahead of time.",
    )
    max_reservations_per_year = models.PositiveIntegerField(
        default=3,
        help_text="Maximum number of glider reservations a member can make per calendar year (default: 3). Set to 0 for unlimited.",
    )
    max_reservations_per_month = models.PositiveIntegerField(
        default=0,
        help_text="Maximum number of glider reservations a member can make per calendar month. Set to 0 for unlimited (default: 0).",
    )

    # Towplane rental options
    allow_towplane_rental = models.BooleanField(
        default=False,
        help_text="We allow towplanes to be rented for non-towing purposes (sightseeing flights, flight reviews, aircraft retrieval, etc.).",
    )

    # Retrieve flight fee waivers (Issue #66)
    waive_tow_fee_on_retrieve = models.BooleanField(
        default=False,
        help_text="Don't charge for the aerotow on retrieve flights (some clubs waive the tow fee when retrieving a landed-out glider).",
    )
    waive_rental_fee_on_retrieve = models.BooleanField(
        default=False,
        help_text="Don't charge for glider rental on retrieve flights (some clubs don't charge rental for the ferry flight back).",
    )

    # Quick altitude buttons for flight form (Issue #467)
    quick_altitude_buttons = models.CharField(
        max_length=100,
        default="300,1000,1500,2000,3000",
        help_text="Comma-separated list of altitude values (in feet) for quick-select buttons on flight forms. Example: 300,1000,1500,2000,3000",
    )

    # Notification dedupe: number of minutes to suppress duplicate redaction
    # notifications for the same member URL. Editable by the Webmaster in the
    # admin SiteConfiguration UI. If blank/zero, falls back to settings or
    # application default.
    redaction_notification_dedupe_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Dedupe window (minutes) for member redaction notifications.",
    )

    # Operational Calendar Configuration
    operations_start_period = models.CharField(
        max_length=100,
        blank=True,
        default="First weekend of May",
        help_text="When club operations typically start each year. Examples: 'First weekend of May', '1st weekend of Apr', 'Second weekend in March', 'Last weekend Oct'. Supports: first/1st, second/2nd, third/3rd, fourth/4th, last + full month names or abbreviations (Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec)",
    )
    operations_end_period = models.CharField(
        max_length=100,
        blank=True,
        default="Last weekend of October",
        help_text="When club operations typically end each year. Examples: 'Last weekend of October', '2nd weekend of Dec', 'Third weekend in November'. Leave both fields blank to include all dates year-round.",
    )

    # Visiting Pilot Configuration (Issue #209)
    visiting_pilot_enabled = models.BooleanField(
        default=False,
        help_text="Enable quick signup for visiting pilots via QR code",
    )
    visiting_pilot_status = models.CharField(
        max_length=50,
        default="Affiliate Member",
        help_text="Membership status assigned to visiting pilots after quick signup",
    )
    visiting_pilot_welcome_text = models.TextField(
        blank=True,
        default="Welcome, visiting pilot! Complete this quick form to get added to our system so you can fly with us today.",
        help_text="Welcome message displayed on visiting pilot signup page",
    )
    visiting_pilot_require_ssa = models.BooleanField(
        default=True,
        help_text="Require SSA membership number for visiting pilot signup",
    )
    visiting_pilot_require_rating = models.BooleanField(
        default=True,
        help_text="Require glider rating for visiting pilot signup",
    )
    visiting_pilot_auto_approve = models.BooleanField(
        default=True,
        help_text="Automatically approve visiting pilots (they can fly immediately after signup)",
    )
    visiting_pilot_token = models.CharField(
        max_length=20,
        blank=True,
        help_text="Security token for visiting pilot signup URLs (generated on-demand, expires when logsheet finalized)",
    )
    visiting_pilot_token_created = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the current visiting pilot token was created",
    )

    # Membership Application Settings
    membership_application_enabled = models.BooleanField(
        default=False,
        help_text="Enable the membership application form for new members",
    )
    membership_application_terms = HTMLField(
        blank=True,
        help_text="Terms and conditions text shown on membership application form",
    )
    membership_auto_approve = models.BooleanField(
        default=False,
        help_text="Automatically approve new membership applications (bypass manual review)",
    )

    # Mail Server Configuration
    manual_whitelist = models.TextField(
        blank=True,
        default="",
        help_text="Email addresses allowed to send to mailing lists (one per line). "
        "Use for trusted non-members like former members, vendors, or partners.",
    )

    def generate_visiting_pilot_token(self):
        """Generate a new secure token for visiting pilot URLs."""
        from django.utils import timezone

        self.visiting_pilot_token = get_random_string(
            12, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
        self.visiting_pilot_token_created = timezone.now()
        return self.visiting_pilot_token

    def refresh_visiting_pilot_token(self):
        """Generate and save a new visiting pilot token."""
        self.generate_visiting_pilot_token()
        self.save(
            update_fields=["visiting_pilot_token", "visiting_pilot_token_created"]
        )
        return self.visiting_pilot_token

    def get_or_create_daily_token(self):
        """Get existing token if created today, otherwise generate a new one."""
        from django.db import transaction
        from django.utils import timezone

        # Use select_for_update to prevent race conditions in distributed environments
        with transaction.atomic():
            # Refresh from database with row-level lock to prevent concurrent token generation
            config = SiteConfiguration.objects.select_for_update().get(id=self.id)

            today = timezone.now().date()
            token_date = (
                config.visiting_pilot_token_created.date()
                if config.visiting_pilot_token_created
                else None
            )

            # If no token exists or token is from a previous day, generate new one
            if not config.visiting_pilot_token or token_date != today:
                config.generate_visiting_pilot_token()
                config.save(
                    update_fields=[
                        "visiting_pilot_token",
                        "visiting_pilot_token_created",
                    ]
                )
                # Update current instance to reflect the changes
                self.visiting_pilot_token = config.visiting_pilot_token
                self.visiting_pilot_token_created = config.visiting_pilot_token_created

            return config.visiting_pilot_token

    def retire_visiting_pilot_token(self):
        """Retire the current visiting pilot token (usually called when logsheet finalized)."""
        self.visiting_pilot_token = ""
        self.visiting_pilot_token_created = None
        self.save(
            update_fields=["visiting_pilot_token", "visiting_pilot_token_created"]
        )

    def get_quick_altitude_list(self):
        """Return a list of (value, label) tuples for quick altitude buttons.

        Parses the comma-separated quick_altitude_buttons field and returns
        a list of tuples suitable for template rendering.
        Example: "2000,3000" -> [(2000, "2K"), (3000, "3K")]
        """
        altitudes = []
        for alt_str in self.quick_altitude_buttons.split(","):
            alt_str = alt_str.strip()
            if alt_str:
                try:
                    alt_val = int(alt_str)
                    # Format label: 2000 -> "2K", 300 -> "300", 1500 -> "1.5K"
                    if alt_val >= 1000 and alt_val % 1000 == 0:
                        label = f"{alt_val // 1000}K"
                    elif alt_val >= 1000:
                        label = f"{alt_val / 1000:.1f}K".replace(".0K", "K")
                    else:
                        label = str(alt_val)
                    altitudes.append((alt_val, label))
                except ValueError:
                    continue  # Skip invalid entries
        return altitudes

    def clean(self):
        if SiteConfiguration.objects.exclude(id=self.id).exists():
            raise ValidationError("Only one SiteConfiguration instance allowed.")

        # Validate surge thresholds are at least 1 (Issue #403)
        errors = {}
        if self.tow_surge_threshold is not None and self.tow_surge_threshold < 1:
            errors["tow_surge_threshold"] = "Tow surge threshold must be at least 1."
        if (
            self.instruction_surge_threshold is not None
            and self.instruction_surge_threshold < 1
        ):
            errors["instruction_surge_threshold"] = (
                "Instruction surge threshold must be at least 1."
            )

        # Validate quick altitude buttons (Issue #467)
        if self.quick_altitude_buttons:
            for alt_str in self.quick_altitude_buttons.split(","):
                alt_str = alt_str.strip()
                if alt_str:
                    try:
                        alt_val = int(alt_str)
                        if alt_val < 0:
                            errors["quick_altitude_buttons"] = (
                                f"Altitude values must be positive integers. Invalid value: {alt_str}"
                            )
                            break
                        if alt_val > 7000:
                            errors["quick_altitude_buttons"] = (
                                f"Altitude values must be 7000 feet or less (matching form field range). Invalid value: {alt_str}"
                            )
                            break
                    except ValueError:
                        errors["quick_altitude_buttons"] = (
                            f"Altitude values must be integers. Invalid value: {alt_str}"
                        )
                        break

        # Validate canonical_url is origin-only (no path/query/fragment)
        if self.canonical_url:
            from urllib.parse import urlparse

            parsed = urlparse(self.canonical_url)
            if parsed.path and parsed.path != "/":
                errors["canonical_url"] = (
                    "Canonical URL must be an origin only (e.g., https://www.example.org). "
                    "Do not include a path, query string, or fragment."
                )
            elif parsed.query or parsed.fragment:
                errors["canonical_url"] = (
                    "Canonical URL must be an origin only (e.g., https://www.example.org). "
                    "Do not include a query string or fragment."
                )

        if errors:
            raise ValidationError(errors)

        # Don't auto-generate tokens - they're created on-demand when duty officer needs them

        # Validate operational period formats
        # Local import to avoid circular dependency
        from duty_roster.operational_calendar import parse_operational_period

        if self.operations_start_period:
            try:
                parse_operational_period(self.operations_start_period)
            except ValueError as e:
                raise ValidationError(
                    {"operations_start_period": f"Invalid format: {e}"}
                )

        if self.operations_end_period:
            try:
                parse_operational_period(self.operations_end_period)
            except ValueError as e:
                raise ValidationError({"operations_end_period": f"Invalid format: {e}"})

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new_logo = False
        if self.pk:
            old = SiteConfiguration.objects.get(pk=self.pk)
            if old.club_logo != self.club_logo:
                is_new_logo = True
        else:
            is_new_logo = bool(self.club_logo)
        super().save(*args, **kwargs)

        # Clear cache when configuration changes
        from django.core.cache import cache

        from utils.favicon import PWA_CLUB_ICON_NAME, generate_pwa_icon_from_logo

        cache.delete("siteconfig_instance")

        # Generate favicon + PWA icon if logo was uploaded/changed
        if self.club_logo and is_new_logo:
            # Read the logo content once into memory so both generation calls
            # share the same in-memory buffer; seeking is cheaper and avoids
            # multiple network round-trips on GCS-backed storage.
            logo_data = None
            try:
                with self.club_logo.open("rb") as logo_file:
                    logo_data = BytesIO(logo_file.read())
            except Exception as e:
                logging.exception(f"Failed to read club_logo from storage: {e}")

            if logo_data is not None:
                # --- favicon.ico (16/32/48 px, .ico format) ---
                try:
                    logo_data.seek(0)
                    outbuf = BytesIO()
                    generate_favicon_from_logo(logo_data, outbuf)
                    outbuf.seek(0)
                    # Delete any previous version so the new one takes its place;
                    # some storage backends (e.g. GCS) generate a new name instead
                    # of overwriting, leaving the old file served indefinitely.
                    if default_storage.exists("favicon.ico"):
                        default_storage.delete("favicon.ico")
                    default_storage.save("favicon.ico", outbuf)
                except Exception as e:
                    logging.exception(
                        f"Failed to save favicon.ico to default_storage: {e}"
                    )

                # --- pwa-icon-club.png (192×192 PNG for PWA / Apple touch icon) ---
                try:
                    logo_data.seek(0)
                    outbuf = BytesIO()
                    generate_pwa_icon_from_logo(logo_data, outbuf)
                    outbuf.seek(0)
                    # Delete any previous version so the new one takes its place
                    if default_storage.exists(PWA_CLUB_ICON_NAME):
                        default_storage.delete(PWA_CLUB_ICON_NAME)
                    default_storage.save(PWA_CLUB_ICON_NAME, outbuf)
                    # Invalidate the cached icon URL so requests immediately pick
                    # up the new club-branded icon
                    cache.delete("pwa_club_icon_url")
                except Exception as e:
                    logging.exception(
                        f"Failed to save {PWA_CLUB_ICON_NAME} to default_storage: {e}"
                    )

        # Backfill: if a club logo already exists but the PWA icon was never
        # generated (e.g. pre-existing installations before this feature was
        # deployed), generate it now without requiring a re-upload.
        elif self.club_logo and not is_new_logo:
            if not default_storage.exists(PWA_CLUB_ICON_NAME):
                try:
                    with self.club_logo.open("rb") as logo_file:
                        logo_data = BytesIO(logo_file.read())
                    logo_data.seek(0)
                    outbuf = BytesIO()
                    generate_pwa_icon_from_logo(logo_data, outbuf)
                    outbuf.seek(0)
                    default_storage.save(PWA_CLUB_ICON_NAME, outbuf)
                    cache.delete("pwa_club_icon_url")
                except Exception as e:
                    logging.exception(
                        f"Failed to backfill {PWA_CLUB_ICON_NAME} to default_storage: {e}"
                    )

        # Logo removal: delete derived assets when the logo is cleared.
        elif not self.club_logo and is_new_logo:
            for _filename in ["favicon.ico", PWA_CLUB_ICON_NAME]:
                if default_storage.exists(_filename):
                    try:
                        default_storage.delete(_filename)
                    except Exception as e:
                        logging.exception(
                            "Failed to delete %s from default_storage: %s",
                            _filename,
                            e,
                        )
            cache.delete("pwa_club_icon_url")

    def delete(self, *args, **kwargs):
        """Override delete to clear cache."""
        from django.core.cache import cache

        cache.delete("siteconfig_instance")
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Site Configuration for {self.club_name}"


class MembershipStatus(models.Model):
    """
    Configurable membership statuses for the club.
    This replaces the hardcoded membership status lists in members.constants.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="The display name for this membership status (e.g., 'Full Member')",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether members with this status are considered 'active' and can access member features",
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        help_text="Sort order for display in dropdowns and lists (lower numbers appear first)",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this membership status means",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Membership Status"
        verbose_name_plural = "Membership Statuses"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion if members are using this status."""
        # Import here to avoid circular imports
        try:
            from django.core.exceptions import ValidationError

            from members.models import Member

            member_count = Member.objects.filter(membership_status=self.name).count()
            if member_count > 0:
                raise ValidationError(
                    f'Cannot delete membership status "{self.name}" - '
                    f"{member_count} members currently have this status. "
                    f"Change their status first, then delete this membership status."
                )
        except ImportError:
            # During migrations, Member model might not be available
            pass

        super().delete(*args, **kwargs)

    @classmethod
    def get_active_statuses(cls):
        """Get all membership statuses that are marked as active."""
        return cls.objects.filter(is_active=True).values_list("name", flat=True)

    @classmethod
    def get_all_status_choices(cls):
        """Get all membership statuses as Django field choices."""
        return [
            (status.name, status.name)
            for status in cls.objects.all().order_by("sort_order", "name")
        ]


class ChargeableItem(models.Model):
    """
    Catalog of purchasable items and service charges.

    Used for both merchandise (t-shirts, logbooks) and service charges
    (aerotow retrieves, instruction materials, etc.). Webmaster maintains
    the catalog; duty officers can add charges to members.

    Issue #66: Aerotow retrieve fees
    Issue #413: Miscellaneous charges
    """

    class UnitType(models.TextChoices):
        EACH = "each", "Each"
        HOUR = "hour", "Per Hour"

    name = models.CharField(
        max_length=100,
        help_text="Display name for the item (e.g., 'T-Shirt Large', 'Aerotow Retrieve')",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Unit price in dollars",
    )
    unit = models.CharField(
        max_length=10,
        choices=UnitType.choices,
        default=UnitType.EACH,
        help_text="Pricing unit - 'Each' for items, 'Per Hour' for time-based charges like retrieve tach time",
    )
    allows_decimal_quantity = models.BooleanField(
        default=False,
        help_text="Allow decimal quantities (e.g., 1.8 hours for tach time). Leave unchecked for whole-number items like t-shirts.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive items won't appear in the charge dropdown",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description or notes about this item",
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        help_text="Sort order for display (lower numbers appear first)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Chargeable Item"
        verbose_name_plural = "Chargeable Items"
        ordering = ["sort_order", "name"]

    def __str__(self):
        unit_display = "/hour" if self.unit == self.UnitType.HOUR else ""
        return f"{self.name} (${self.price:.2f}{unit_display})"
