from django.conf import settings
from django.db import models
from django.utils.text import slugify
from tinymce.models import HTMLField

from utils.upload_document_obfuscated import upload_document_obfuscated
from utils.upload_entropy import upload_homepage_gallery

# --- CMS Arbitrary Page and Document Models ---


class PageRolePermission(models.Model):
    """
    Defines which member roles can access a CMS page.
    Only applies to private pages (is_public=False).
    """

    # Role choices based on Member model boolean fields
    ROLE_CHOICES = [
        ("instructor", "Instructor"),
        ("towpilot", "Towpilot"),
        ("duty_officer", "Duty Officer"),
        ("assistant_duty_officer", "Assistant Duty Officer"),
        ("secretary", "Secretary"),
        ("treasurer", "Treasurer"),
        ("webmaster", "Webmaster"),
        ("director", "Director"),
        ("member_manager", "Member Manager"),
        ("rostermeister", "Rostermeister"),
    ]

    page = models.ForeignKey(
        "Page", on_delete=models.CASCADE, related_name="role_permissions"
    )
    role_name = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        help_text="Member role required to access this page",
    )

    class Meta:
        unique_together = ("page", "role_name")
        verbose_name = "Page Role Permission"
        verbose_name_plural = "Page Role Permissions"

    def __str__(self):
        return f"{self.page.title} - {self.get_role_name_display()}"


class Page(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL path for this page, e.g. 'club-documents', 'bylaws', etc.",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
        help_text="Parent directory (for subdirectories)",
    )
    content = HTMLField(blank=True)
    is_public = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "CMS Page"
        verbose_name_plural = "CMS Pages"
        unique_together = ("parent", "slug")

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        if self.parent:
            return f"/cms/{self.parent.slug}/{self.slug}/"
        return f"/cms/{self.slug}/"

    def clean(self):
        """Validate that public pages cannot have role restrictions."""
        from django.core.exceptions import ValidationError

        # Only check if this is an update (has pk) since M2M relations don't exist on create
        if self.pk and self.is_public and self.role_permissions.exists():
            raise ValidationError(
                "Public pages cannot have role restrictions. "
                "Set 'is_public' to False to enable role-based access control."
            )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        self.clean()
        super().save(*args, **kwargs)

    def has_role_restrictions(self):
        """Return True if this page has any role restrictions."""
        return self.role_permissions.exists()

    def get_required_roles(self):
        """Return list of required role names for this page."""
        return list(self.role_permissions.values_list("role_name", flat=True))

    def can_user_access(self, user):
        """
        Check if a user can access this page based on role restrictions.
        Returns True if:
        - Page is public, OR
        - User is active member and no role restrictions, OR
        - User has at least one of the required roles
        """
        if self.is_public:
            return True

        # Check if user is an active member
        from members.utils import is_active_member

        if not is_active_member(user):
            return False

        # If no role restrictions, any active member can access
        if not self.has_role_restrictions():
            return True

        # Check if user has any of the required roles
        required_roles = self.get_required_roles()
        return any(getattr(user, role, False) for role in required_roles)


def upload_document_to(instance, filename):
    # Store files under cms/<page-slug>/<filename> for public, obfuscated for private
    page_slug = instance.page.slug if instance.page else "uncategorized"
    if instance.page and not instance.page.is_public:
        # Use obfuscated filename for restricted/private documents
        return upload_document_obfuscated(instance, filename)
    return f"cms/{page_slug}/{filename}"


class Document(models.Model):
    page = models.ForeignKey(Page, related_name="documents", on_delete=models.CASCADE)
    file = models.FileField(upload_to=upload_document_to)
    title = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "CMS Document"
        verbose_name_plural = "CMS Documents"

    def __str__(self):
        return self.title or self.file.name

    @property
    def is_pdf(self):
        return self.file.name.lower().endswith(".pdf")

    @property
    def extension(self):
        return self.file.name.split(".")[-1].lower()


# Create your models here.


class HomePageContent(models.Model):
    AUDIENCE_CHOICES = [
        ("public", "Public (not logged in)"),
        ("member", "Member (logged in)"),
    ]
    title = models.CharField(
        max_length=200, default="Welcome to the Skyline Soaring Members Site 🛫"
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL path for this page, e.g. 'home', 'about', 'contact'",
    )
    audience = models.CharField(
        max_length=10,
        choices=AUDIENCE_CHOICES,
        default="public",
        help_text="Who should see this page content?",
    )
    content = HTMLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CMS Page Content"
        verbose_name_plural = "CMS Page Content"

    def __str__(self):
        return f"{self.title} [{self.audience}]"


class HomePageImage(models.Model):
    page = models.ForeignKey(
        HomePageContent, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to=upload_homepage_gallery)
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Order for display")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "CMS Page Image"
        verbose_name_plural = "CMS Page Images"

    def __str__(self):
        return self.caption or f"Image {self.pk}"


# Site Feedback Model for Issue #117
class SiteFeedback(models.Model):
    FEEDBACK_TYPE_CHOICES = [
        ("bug", "Bug Report"),
        ("feature", "Feature Request"),
        ("help", "Help Request"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        help_text="User who submitted the feedback",
    )
    feedback_type = models.CharField(
        max_length=20, choices=FEEDBACK_TYPE_CHOICES, default="other"
    )
    referring_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL of the page where feedback was submitted from",
    )
    subject = models.CharField(max_length=200)
    message = HTMLField(help_text="Detailed feedback message")

    # Status tracking
    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    # Admin response
    admin_response = HTMLField(blank=True, null=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_responses",
        help_text="Webmaster who responded to this feedback",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Site Feedback"
        verbose_name_plural = "Site Feedback"

    def __str__(self):
        return f"{self.get_feedback_type_display()}: {self.subject} - {self.user.full_display_name}"

    def save(self, *args, **kwargs):
        # Auto-set resolved_at when status changes to resolved
        if self.status == "resolved" and not self.resolved_at:
            from django.utils import timezone

            self.resolved_at = timezone.now()
        super().save(*args, **kwargs)


# Visitor Contact Model for Issue #70
class VisitorContact(models.Model):
    """
    Model to store contact form submissions from visitors (non-members).
    Replaces the need to expose welcome@skylinesoaring.org to spam.
    """

    name = models.CharField(max_length=100, help_text="Visitor's full name")
    email = models.EmailField(help_text="Visitor's email address for follow-up")
    phone = models.CharField(
        max_length=20, blank=True, null=True, help_text="Optional phone number"
    )
    subject = models.CharField(
        max_length=200, help_text="Brief subject line for the inquiry"
    )
    message = models.TextField(help_text="Detailed message from the visitor")

    # Metadata
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, help_text="IP address for spam prevention"
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Status tracking
    STATUS_CHOICES = [
        ("new", "New"),
        ("read", "Read"),
        ("responded", "Responded"),
        ("closed", "Closed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")

    # Admin tracking
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Member who handled this inquiry",
    )
    admin_notes = models.TextField(
        blank=True, null=True, help_text="Internal notes for member managers"
    )

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Visitor Contact"
        verbose_name_plural = "Visitor Contacts"

    def __str__(self):
        return (
            f"{self.name} - {self.subject} ({self.submitted_at.strftime('%Y-%m-%d')})"
        )
