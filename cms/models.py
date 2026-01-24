import threading

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from tinymce.models import HTMLField

from utils.upload_document_obfuscated import upload_document_obfuscated
from utils.upload_entropy import upload_homepage_gallery

# Thread-local storage for recursion guards
_thread_locals = threading.local()

# --- CMS Arbitrary Page and Document Models ---


class PageRolePermission(models.Model):
    """
    Defines role-based access control for CMS pages.

    This model creates a Many-to-Many relationship between Pages and member roles,
    allowing fine-grained access control for sensitive content.

    Business Rules:
    - Only applies to private pages (is_public=False)
    - Uses OR logic: users need ANY of the assigned roles (not ALL)
    - Role choices map to Member model boolean fields
    - Public pages cannot have role restrictions (enforced by validation)

    Examples:
    - Board meeting minutes: directors only
    - Financial reports: directors AND treasurers (separate permissions)
    - Instructor resources: instructors, duty_officers, directors

    Attributes:
        page: Foreign key to the Page this permission applies to
        role_name: The specific member role required (from ROLE_CHOICES)
    """

    # Role choices based on Member model boolean fields
    ROLE_CHOICES = [
        # Special case for any logged-in active member
        ("active_member", "Any Active Member"),
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

    def clean(self):
        """
        Validate business rules for role permissions.

        Ensures that role permissions can only be added to private pages,
        preventing invalid configurations where public pages have role restrictions.

        Raises:
            ValidationError: If attempting to add role permissions to a public page

        Note:
            This validation is called automatically during save() and in Django admin
            when full_clean() is invoked.
        """
        from django.core.exceptions import ValidationError

        if self.page_id and self.page.is_public:
            raise ValidationError(
                "Role permissions cannot be added to public pages. "
                "Set the page to private (uncheck 'is_public') first."
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.page.title} - {self.get_role_name_display()}"


class PageMemberPermission(models.Model):
    """
    Allows assigning specific members EDIT permissions for specific CMS pages or folders.

    This model enables fine-grained EDIT access control, allowing individual members
    to be granted editing rights, separate from VIEW permissions.

    IMPORTANT: This grants EDIT permissions with different scope depending on context:
    - Django Admin: Members listed here (plus officers) can edit both PUBLIC and
      PRIVATE pages.
    - Site Editor (cms.views.can_edit_page): PUBLIC pages are editable here only by
      webmasters; member-based permissions from this model are evaluated by
      Page.can_user_edit(), but the public-page restriction itself is enforced in
      cms.views.can_edit_page(), not in Page.can_user_edit().
    - For PUBLIC pages: This permission affects who can EDIT via Django admin and
      who passes Page.can_user_edit(); the site editor still restricts PUBLIC page
      editing to webmasters via cms.views.can_edit_page(), and the page remains
      publicly viewable.
    - For PRIVATE pages: This permission grants EDIT access in both Django admin and
      the site editor (after cms.views.can_edit_page() allows editing), and also
      grants VIEW access.

    Use Cases:
    - Assign content editor for public documentation (page stays public)
    - Aircraft manager who manages documentation for a specific aircraft folder
    - Committee chair who maintains a committee-specific folder
    - Event coordinator who updates event pages

    Business Rules:
    - Can be applied to both public and private pages
    - Grants EDIT rights (via Django admin) in addition to officers
    - For private pages, EDIT permission also grants VIEW access
    - Applies to the page and all documents attached to it

    Example Workflows:
    1. Public page with editor:
       - Director creates "Club Bylaws" (public)
       - Director adds Secretary via PageMemberPermission
       - Everyone can VIEW the bylaws (public)
       - Only officers + Secretary can EDIT in admin

    2. Private page with editor:
       - Director creates "PW5 Aircraft" folder (private, no role restrictions)
       - Director adds Kevin Barrett via PageMemberPermission
       - All active members can VIEW the folder (no role restrictions)
       - Only officers + Kevin Barrett can EDIT the folder

    Attributes:
        page: Foreign key to the Page this permission applies to
        member: Foreign key to the Member granted EDIT access
    """

    page = models.ForeignKey(
        "Page", on_delete=models.CASCADE, related_name="member_permissions"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cms_page_permissions",
        help_text=(
            "Member granted EDIT access to this page. Applies in Django admin for "
            "public and private pages, and in the in-site editor for private pages "
            "(also granting VIEW access there)."
        ),
    )

    class Meta:
        unique_together = ("page", "member")
        verbose_name = "Page Member Permission"
        verbose_name_plural = "Page Member Permissions"

    def __str__(self):
        return f"{self.page.title} - {self.member.full_display_name}"


class Page(models.Model):
    """
    CMS Page model supporting hierarchical content with role-based access control.

    Provides a flexible content management system with two independent access controls:
    1. VIEW permissions (is_public flag and PageRolePermission)
    2. EDIT permissions (PageMemberPermission - affects Django admin for all pages,
       and site editor for private pages only; public pages remain webmaster-only
       in site editor)

    Features:
    - Hierarchical page structure with parent-child relationships
    - Rich HTML content via TinyMCE integration
    - Automatic slug generation from titles
    - Role-based VIEW access control via PageRolePermission
    - Member-based EDIT access control via PageMemberPermission
    - File attachments via Document model

    View Access Control Logic:
    - Public pages (is_public=True): No VIEW restrictions (everyone can view)
    - Private pages (is_public=False, no roles): Active members only (VIEW restricted)
    - Role-restricted pages (is_public=False, with roles): Specific roles only (VIEW restricted)

    Edit Access Control Logic (Django Admin):
    - Officers (directors, secretaries, webmasters) can always edit
    - Members assigned via PageMemberPermission can edit
    - Edit permissions work independently of VIEW permissions:
      * Public pages can have assigned editors (page stays public)
      * Private pages can have assigned editors (member also gains VIEW access)

    Examples:
    1. Public page with editor: "Club Bylaws" (is_public=True, member=Secretary)
       - Everyone can VIEW the bylaws
       - Only officers + Secretary can EDIT in admin

    2. Private member-only page with editor: "Instructor Resources" (is_public=False, no roles, member=Chief Instructor)
       - All active members can VIEW
       - Only officers + Chief Instructor can EDIT in admin

    3. Private role-restricted page with editor: "Board Minutes" (is_public=False, roles=[director], member=Secretary)
       - Only directors can VIEW (due to role restriction)
       - Only officers + Secretary can EDIT in admin (Secretary also gains VIEW access)

    Attributes:
        title: Display name for the page
        slug: URL-friendly identifier (auto-generated if not provided)
        parent: Optional parent page for hierarchical structure
        content: Rich HTML content (TinyMCE field)
        is_public: Controls VIEW access level (public vs. private)
        role_permissions: Related PageRolePermission objects for VIEW access control
        member_permissions: Related PageMemberPermission objects for EDIT access control
    """

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
        """
        Return the absolute URL path for this CMS page.

        For top-level pages: /cms/{slug}/
        For nested pages: /cms/{parent_slug}/{slug}/
        For multi-level nested pages: /cms/{grandparent_slug}/{parent_slug}/{slug}/

        Returns:
            str: The URL path for accessing this page
        """
        path_parts = [self.slug]
        current = self.parent
        while current:
            path_parts.insert(0, current.slug)
            current = current.parent
        return f"/cms/{'/'.join(path_parts)}/"

    def clean(self):
        """
        Validate business rules for CMS pages.

        Ensures that pages with role restrictions cannot be made public,
        maintaining security by preventing accidental exposure of restricted content.

        Raises:
            ValidationError: If attempting to make a page with role restrictions public

        Note:
            Only validates existing pages (with pk) since Many-to-Many relationships
            don't exist during initial creation.
        """
        from django.core.exceptions import ValidationError

        # Only check if this is an update (has pk) since M2M relations don't exist on create
        if self.pk and self.is_public and self.role_permissions.exists():
            raise ValidationError(
                "Public pages cannot have role restrictions. "
                "Set 'is_public' to False to enable role-based access control."
            )

    def save(self, *args, **kwargs):
        """
        Save the page with automatic slug generation and validation.

        Automatically generates a URL-friendly slug from the title if none provided,
        runs model validation, and fixes YouTube embeds to prevent Error 153.

        Args:
            *args, **kwargs: Standard Django save() parameters
        """
        if not self.slug:
            self.slug = slugify(self.title)

        # Only run clean() if this is an update (pk exists) to prevent unnecessary queries
        if self.pk:
            self.clean()
            # Only fix YouTube embeds if content has changed
            old_content = Page.objects.get(pk=self.pk).content
            if old_content != self.content:
                self._fix_youtube_embeds()
        else:
            # New object, always check
            self._fix_youtube_embeds()

        super().save(*args, **kwargs)

    def _fix_youtube_embeds(self):
        """
        Automatically fix YouTube iframe embeds to prevent Error 153.

        Uses shared utility function to add referrerpolicy="strict-origin-when-cross-origin"
        to YouTube iframes for proper domain verification.
        """
        from .utils import fix_youtube_embeds

        fixed_content = fix_youtube_embeds(self.content)
        if fixed_content != self.content:
            self.content = fixed_content

    def has_role_restrictions(self):
        """
        Check if this page has any role-based access restrictions.

        Returns:
            bool: True if the page has role restrictions, False otherwise.
                 Public pages and pages without role permissions return False.
        """
        # Try to use prefetched data first to avoid extra queries
        if (
            hasattr(self, "_prefetched_objects_cache")
            and "role_permissions" in self._prefetched_objects_cache
        ):
            return len(self.role_permissions.all()) > 0
        return self.role_permissions.exists()

    def get_required_roles(self):
        """
        Get the list of member roles required to access this page.

        Returns:
            list[str]: List of role names (e.g., ['director', 'treasurer'])
                      required for access. Empty list if no role restrictions.

        Note:
            This method can cause database queries. For performance-sensitive
            code, use prefetch_related('role_permissions') on the queryset.
        """
        return list(self.role_permissions.values_list("role_name", flat=True))

    def can_user_access(self, user, request=None):
        """
        Check if a user can VIEW this page based on role-based access control.

        Access is granted using a four-tier system:
        1. Public pages: Accessible to everyone (including anonymous users)
        2. Private pages without restrictions: Accessible to all active members
        3. Role-restricted pages: Only accessible to members with required roles
        4. Users with EDIT permission: Can also VIEW (editors need to see content)

        Args:
            user: Django User instance (can be anonymous)
            request: Optional HttpRequest object (needed for kiosk session detection)

        Returns:
            bool: True if the user can access this page, False otherwise

        Access Logic:
            - Public pages (is_public=True): Always accessible
            - Private pages: Requires active membership status
            - Role restrictions: Uses OR logic - user needs ANY of the required roles
            - EDIT permission: Users who can edit can also view

        Note:
            This method controls VIEW access. For EDIT-only permission checks,
            see can_user_edit() and PageMemberPermission model.

        Examples:
            >>> page.is_public = True
            >>> page.can_user_access(anonymous_user)  # True

            >>> page.is_public = False  # No role restrictions
            >>> page.can_user_access(active_member)  # True

            >>> page.is_public = False
            >>> page.role_permissions.add(director_role)
            >>> page.can_user_access(director)  # True
            >>> page.can_user_access(regular_member)  # False

            >>> # User with EDIT permission can VIEW
            >>> page.member_permissions.create(member=aircraft_manager)
            >>> page.can_user_access(aircraft_manager)  # True (via EDIT permission)
        """
        if self.is_public:
            return True

        # Users with EDIT permission should also be able to VIEW
        # (editors need to see what they're editing)
        # Use thread-local storage to guard against recursion in a thread-safe manner
        checking_access_via_edit = getattr(
            _thread_locals, "checking_access_via_edit", None
        )
        if checking_access_via_edit is None:
            checking_access_via_edit = set()
            _thread_locals.checking_access_via_edit = checking_access_via_edit

        page_key = (
            self.pk,
            user.pk if user and getattr(user, "pk", None) is not None else None,
        )
        if page_key not in checking_access_via_edit:
            checking_access_via_edit.add(page_key)
            try:
                if self.can_user_edit(user):
                    return True
            finally:
                checking_access_via_edit.discard(page_key)

        # Check if user is an active member or authenticated via kiosk
        from members.utils import is_active_member, is_kiosk_session

        # Allow kiosk sessions to view member content (Issue #486)
        if request and is_kiosk_session(request):
            # Kiosk sessions can view member content
            pass
        elif not is_active_member(user):
            return False

        # If no role restrictions, any active member can access
        if not self.has_role_restrictions():
            return True

        # Check if user has any of the required roles
        required_roles = self.get_required_roles()

        # Special case: if "active_member" is in required roles, any active member can access
        if "active_member" in required_roles:
            return True  # User already passed is_active_member check above

        return any(getattr(user, role, False) for role in required_roles)

    def can_user_edit(self, user):
        """
        Check if a user can EDIT this page.

        Edit permissions are granted to:
        1. Superusers
        2. Directors, Secretaries, and Webmasters (club officers)
        3. Members with explicit edit permission via PageMemberPermission

        Args:
            user: Django User instance

        Returns:
            bool: True if user can edit this page, False otherwise

        Note:
            Users with EDIT permission can also VIEW the page (see can_user_access).
            PageMemberPermission grants EDIT rights, and editors can see their content.

        Examples:
            >>> # Officer can always edit
            >>> page.can_user_edit(director)  # True

            >>> # Aircraft manager granted edit permission
            >>> page.member_permissions.create(member=aircraft_manager)
            >>> page.can_user_edit(aircraft_manager)  # True
            >>> page.can_user_access(aircraft_manager)  # True (via EDIT permission)
        """
        if not user or not user.is_authenticated:
            return False

        # Check superuser first (cheap attribute check, avoids DB queries)
        if getattr(user, "is_superuser", False):
            return True

        # Check if user has explicit member permission for this page (may require DB query)
        if self.has_member_permission(user):
            return True

        # Check if user has officer roles (director, secretary, webmaster)
        if any(
            getattr(user, role, False)
            for role in ["director", "secretary", "webmaster"]
        ):
            return True

        return False

    def has_member_permission(self, user):
        """
        Check if a specific member has explicit EDIT permission for this page.

        Args:
            user: Django User instance

        Returns:
            bool: True if user has explicit member permission

        Note:
            Uses prefetched data if available to avoid extra queries.
            This method checks EDIT permissions, not VIEW permissions.
        """
        if not user or not user.is_authenticated:
            return False

        # Try to use prefetched data first to avoid extra queries
        if (
            hasattr(self, "_prefetched_objects_cache")
            and "member_permissions" in self._prefetched_objects_cache
        ):
            return any(mp.member_id == user.id for mp in self.member_permissions.all())
        return self.member_permissions.filter(member=user).exists()

    def get_permitted_members(self):
        """
        Get the list of members with explicit access to this page.

        Returns:
            QuerySet: Members with explicit page access
        """
        from members.models import Member

        member_ids = self.member_permissions.values_list("member_id", flat=True)
        return Member.objects.filter(id__in=member_ids)


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
        ordering = ["title", "file"]  # Sort by title first, then filename

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

    def save(self, *args, **kwargs):
        """Save with automatic YouTube embed fixes to prevent Error 153."""
        # Only fix YouTube embeds if content has changed
        if self.pk:
            old_content = HomePageContent.objects.get(pk=self.pk).content
            if old_content != self.content:
                self._fix_youtube_embeds()
        else:
            # New object, always check
            self._fix_youtube_embeds()
        super().save(*args, **kwargs)

    def _fix_youtube_embeds(self):
        """
        Automatically fix YouTube iframe embeds to prevent Error 153.

        Uses shared utility function to add referrerpolicy="strict-origin-when-cross-origin"
        to YouTube iframes for proper domain verification.
        """
        from .utils import fix_youtube_embeds

        fixed_content = fix_youtube_embeds(self.content)
        if fixed_content != self.content:
            self.content = fixed_content


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
    referring_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL path of the page where feedback was submitted from",
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
