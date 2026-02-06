# Generic CMS Page view for arbitrary pages and directories
import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Max
from django.forms import inlineformset_factory
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from tinymce.widgets import TinyMCE

from cms.forms import SiteFeedbackForm, VisitorContactForm
from cms.models import HomePageContent
from members.decorators import active_member_required
from members.utils import is_active_member
from utils.email_helpers import get_absolute_club_logo_url

from .models import Document, Page, PageMemberPermission, PageRolePermission

# Module-level logger to avoid repeated getLogger calls
logger = logging.getLogger(__name__)


def get_role_display_names(page):
    """
    Get human-readable role names for a page's role restrictions.

    Args:
        page: A Page instance with prefetched role_permissions

    Returns:
        list: List of human-readable role names, empty if no restrictions
    """
    if not page.has_role_restrictions():
        return []

    from .models import PageRolePermission

    # Try to use prefetched data to avoid extra queries
    if (
        hasattr(page, "_prefetched_objects_cache")
        and "role_permissions" in page._prefetched_objects_cache
    ):
        role_names = [rp.role_name for rp in page.role_permissions.all()]
    else:
        # Fallback to values_list which is more efficient than fetching full objects
        role_names = list(page.role_permissions.values_list("role_name", flat=True))

    role_choices_dict = dict(PageRolePermission.ROLE_CHOICES)
    return [role_choices_dict.get(role, role.title()) for role in role_names]


def get_accessible_top_level_pages(user, request=None):
    """
    Get accessible top-level CMS pages for a user with optimized queries.

    Args:
        user: The user to check access for
        request: Optional HttpRequest object (needed for kiosk session detection)

    Returns:
        list: List of page dictionaries with metadata
    """
    from django.db.models import Count

    from .models import Page

    # Use annotate to compute counts in a single query, avoiding N+1 queries
    # IMPORTANT: Use distinct=True to prevent Cartesian product when counting multiple relations
    top_pages_qs = (
        Page.objects.filter(parent__isnull=True)
        .prefetch_related("role_permissions")
        .annotate(
            doc_count=Count("documents", distinct=True),
            child_count=Count("children", distinct=True),
        )
        .order_by("title")
    )

    pages = []
    for p in top_pages_qs:
        # Use the page's built-in access control method
        can_view = p.can_user_access(user, request)

        # Only include pages the user can access
        if not can_view:
            continue

        # Get role information for display (avoiding template database queries)
        required_roles = get_role_display_names(p) if not p.is_public else []

        pages.append(
            {
                "page": p,
                # Use annotated counts to avoid N+1 queries
                "doc_count": getattr(p, "doc_count", 0) + getattr(p, "child_count", 0),
                "is_public": p.is_public,
                "can_view": can_view,
                "has_role_restrictions": p.has_role_restrictions(),
                "required_roles": required_roles,
            }
        )

    return pages


def cms_page(request, **kwargs):
    # Accepts 'path' kwarg: slash-separated slugs (e.g. "parent/child/grandchild")
    # Supports up to MAX_CMS_DEPTH levels of nesting (Issue #596)
    debug_logger = logging.getLogger("cms.debug")
    path_str = kwargs.get("path", "")
    slugs = [s for s in path_str.split("/") if s]
    debug_logger.debug(f"cms_page: slugs={slugs}")
    if not slugs:
        debug_logger.debug("cms_page: No slugs, redirecting to cms:resources")
        return redirect("cms:resources")
    parent = None
    page = None
    for slug in slugs:
        debug_logger.debug(
            f"cms_page: Looking for Page with slug='{slug}' and parent={parent}"
        )
        # Prefetch role_permissions to avoid N+1 queries later
        page = get_object_or_404(
            Page.objects.prefetch_related("role_permissions"), slug=slug, parent=parent
        )
        parent = page
    debug_logger.debug(f"cms_page: Found page {page}")
    # page is now the deepest resolved page
    # Access control: check if user can access this page based on role restrictions
    assert page is not None
    if not page.can_user_access(request.user, request):
        # Use Django's helper to redirect to login (handles encoding)
        return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
    # Build subpage metadata (doc counts and last-updated timestamps) to
    # avoid doing this in the template and to prevent N+1 queries.
    # Annotate children with document counts and latest upload to avoid N+1
    # Also prefetch role permissions to avoid N+1 queries in template
    subpages = []
    children = (
        page.children.annotate(
            doc_count=Count("documents"), doc_max=Max("documents__uploaded_at")
        )
        .prefetch_related("role_permissions")
        .order_by("title")
    )
    for child in children:
        # Skip pages the user cannot access (security filtering)
        if not child.can_user_access(request.user, request):
            continue

        # last updated is the later of the page's updated_at and latest document upload
        last_updated = child.updated_at
        if getattr(child, "doc_max", None) and child.doc_max > last_updated:
            last_updated = child.doc_max

        # Get role information for display (avoiding template database queries)
        required_roles = get_role_display_names(child) if not child.is_public else []

        subpages.append(
            {
                "page": child,
                "doc_count": getattr(child, "doc_count", 0),
                "last_updated": last_updated,
                "has_role_restrictions": child.has_role_restrictions(),
                "required_roles": required_roles,
            }
        )

    # Build breadcrumbs: Resources -> (parents...) -> current page
    breadcrumbs = []
    # Top-level 'Resources' link
    try:
        resources_url = reverse("cms:resources")
    except Exception:
        resources_url = "/cms/"
    breadcrumbs.append({"title": "Resources", "url": resources_url})

    # Walk parent chain from root down to immediate parent
    parents = []
    p = page.parent
    while p:
        parents.append(p)
        p = p.parent
    parents.reverse()
    for par in parents:
        breadcrumbs.append({"title": par.title, "url": par.get_absolute_url()})

    # Whether the current page has documents (avoid calling .exists in template)
    has_documents = page.documents.exists()

    # Get role information for the current page (avoiding template database queries)
    # role_permissions are already prefetched from the page traversal loop
    page_required_roles = get_role_display_names(page) if not page.is_public else []

    # Check if user can create subpages under this page (Issue #596)
    can_create_subpage = can_create_in_directory(request.user, page)

    return render(
        request,
        "cms/page.html",
        {
            "page": page,
            "subpages": subpages,
            "breadcrumbs": breadcrumbs,
            "has_documents": has_documents,
            "page_has_role_restrictions": page.has_role_restrictions(),
            "page_required_roles": page_required_roles,
            "can_edit_page": can_edit_page(request.user, page),
            "can_create_subpage": can_create_subpage,
        },
    )


def homepage(request):
    """
    Homepage view for root URL ("/") only.
    Shows HomePageContent based on user authentication status.
    """
    user = request.user
    allowed_statuses = [
        "Full Member",
        "Student Member",
        "Family Member",
        "Service Member",
        "Founding Member",
        "Honorary Member",
        "Emeritus Member",
        "SSEF Member",
        "Temporary Member",
        "Introductory Member",
    ]

    # Try to render legacy HomePageContent for the appropriate audience
    page = None
    from members.utils import is_kiosk_session

    # Show member content if: authenticated + (kiosk session OR active membership)
    if user.is_authenticated and (
        is_kiosk_session(request)
        or user.is_superuser
        or getattr(user, "membership_status", None) in allowed_statuses
    ):
        page = HomePageContent.objects.filter(
            audience="member", slug="member-home"
        ).first()
    else:
        page = HomePageContent.objects.filter(audience="public", slug="home").first()

    if page:
        # Homepage editing is webmaster-only
        can_edit_homepage = user.is_authenticated and (
            user.is_superuser or getattr(user, "webmaster", False)
        )
        return render(
            request,
            "cms/homepage.html",
            {"page": page, "can_edit_page": can_edit_homepage},
        )

    # Fallback: show CMS index of top-level pages using optimized helper function
    pages = get_accessible_top_level_pages(request.user, request)
    return render(request, "cms/index.html", {"pages": pages})


def cms_resources_index(request):
    """
    CMS Resources index view for /cms/ path.
    Always shows the navigable directory index of CMS pages/resources.
    """
    # Use helper function to get accessible pages with optimized queries
    pages = get_accessible_top_level_pages(request.user, request)
    return render(
        request,
        "cms/index.html",
        {
            "pages": pages,
            # Top-level creation
            "can_create_page": can_create_in_directory(request.user, None),
        },
    )


# Site Feedback Views for Issue #117


def _validate_referring_url(url, request):
    """
    Validate that a referring URL is safe (relative or same-host).
    Prevents XSS and open redirect vulnerabilities.
    """
    if not url:
        return ""
    # Only allow relative URLs or URLs pointing to the same host
    if url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=False
    ):
        return url
    return ""


@active_member_required
def submit_feedback(request):
    """
    View for submitting site feedback.
    Captures referring URL and notifies webmasters.
    """
    if request.method == "POST":
        form = SiteFeedbackForm(request.POST)
        # Get referring URL from hidden form field (preserved from initial GET)
        # Validate to prevent XSS and open redirect attacks
        raw_url = request.POST.get("referring_url", "")
        referring_url = _validate_referring_url(raw_url, request)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            feedback.referring_url = referring_url
            feedback.save()

            # Send notification to webmasters
            _notify_webmasters_of_feedback(feedback)

            messages.success(
                request,
                "Thank you for your feedback! Webmasters have been notified and will respond soon.",
            )
            return redirect("cms:feedback_success")
    else:
        form = SiteFeedbackForm()
        # Capture referring URL on initial GET request
        # Validate to prevent XSS and open redirect attacks
        raw_url = request.GET.get("from", request.headers.get("referer", ""))
        referring_url = _validate_referring_url(raw_url, request)

    return render(
        request,
        "cms/feedback_form.html",
        {
            "form": form,
            "referring_url": referring_url,
        },
    )


@active_member_required
def feedback_success(request):
    """Simple success page after feedback submission."""
    return render(request, "cms/feedback_success.html")


def _notify_webmasters_of_feedback(feedback):
    """
    Send notifications to all webmasters about new feedback.
    """
    try:
        from members.models import Member
        from notifications.models import Notification

        webmasters = Member.objects.filter(webmaster=True, is_active=True)

        for webmaster in webmasters:
            try:
                notification_message = (
                    f"New site feedback from {feedback.user.full_display_name}: "
                    f"{feedback.get_feedback_type_display()} - {feedback.subject}"
                )

                # Link to admin interface for feedback management
                notification_url = f"/admin/cms/sitefeedback/{feedback.pk}/change/"

                Notification.objects.create(
                    user=webmaster, message=notification_message, url=notification_url
                )
            except Exception as e:
                # Log but don't fail - feedback submission should still work
                logger.error(f"Failed to notify webmaster {webmaster}: {e}")

    except ImportError:
        # Notifications app not available
        pass
    except Exception as e:
        # Log but don't fail
        logger.error(f"Failed to notify webmasters of feedback: {e}")


# Visitor Contact Views for Issue #70


def contact(request):
    """
    Public contact form for visitors to reach the club.
    No authentication required - this replaces exposing welcome@skylinesoaring.org

    Includes honeypot spam prevention (Issue #590) - if honeypot field is filled,
    we silently redirect to success page without saving, so bot thinks it worked.
    """
    if request.method == "POST":
        form = VisitorContactForm(request.POST)
        if form.is_valid():
            # Check honeypot - if triggered, silently redirect without saving
            if form.is_honeypot_triggered():
                # Don't save, don't notify, but redirect to success so bot thinks it worked
                return redirect("contact_success")

            contact_submission = form.save(commit=False)

            # Capture IP address for spam prevention
            contact_submission.ip_address = _get_client_ip(request)
            contact_submission.save()

            # Send notification to member managers
            _notify_member_managers_of_contact(contact_submission)

            messages.success(
                request, "Thank you for contacting us! We'll get back to you soon."
            )
            return redirect("contact_success")
    else:
        form = VisitorContactForm()

    # Get site configuration for club-specific information
    from siteconfig.models import SiteConfiguration

    site_config = SiteConfiguration.objects.first()

    return render(
        request,
        "cms/contact.html",
        {
            "form": form,
            "site_config": site_config,
            "page_title": f'Contact {site_config.club_name if site_config else "Our Club"}',
        },
    )


def contact_success(request):
    """Success page after visitor contact form submission."""
    # Get site configuration for club-specific information
    from siteconfig.models import SiteConfiguration

    site_config = SiteConfiguration.objects.first()

    return render(
        request,
        "cms/contact_success.html",
        {
            "page_title": "Message Sent Successfully",
            "site_config": site_config,
        },
    )


def _get_client_ip(request):
    """Get the visitor's IP address for logging purposes."""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def _notify_member_managers_of_contact(contact_submission):
    """
    Send notifications to member managers about new visitor contact.
    This replaces sending emails to the spam-prone welcome@skylinesoaring.org
    """
    try:
        from members.models import Member
        from siteconfig.models import SiteConfiguration
        from utils.email import send_mail

        # Get site configuration for domain info
        site_config = SiteConfiguration.objects.first()

        # Get all member managers
        member_managers = Member.objects.filter(member_manager=True, is_active=True)

        if not member_managers.exists():
            # Fallback to webmasters if no member managers
            member_managers = Member.objects.filter(webmaster=True, is_active=True)

        # Prepare email content with proper escaping to prevent email injection
        # Strip newlines and control characters from subject to prevent header injection
        safe_subject = "".join(
            char
            for char in contact_submission.subject
            if char.isprintable() and char not in "\r\n"
        )
        subject = f"New Visitor Contact: {safe_subject[:100]}"  # Limit subject length

        # Sanitize all user input in email body
        safe_name = contact_submission.name.replace("\r", "").replace("\n", " ")
        safe_email = contact_submission.email.replace("\r", "").replace("\n", " ")
        safe_phone = (
            (contact_submission.phone or "Not provided")
            .replace("\r", "")
            .replace("\n", " ")
        )
        safe_user_subject = contact_submission.subject.replace("\r", "").replace(
            "\n", " "
        )
        safe_message = (
            contact_submission.message
        )  # Keep original formatting for message content

        # Prepare context for email templates
        config = SiteConfiguration.objects.first()

        # Determine base URL for admin interface link
        if hasattr(settings, "SITE_URL"):
            base_url = settings.SITE_URL
        elif site_config and site_config.domain_name:
            base_url = f"https://{site_config.domain_name}"
        else:
            base_url = "https://localhost:8000"

        context = {
            "contact": contact_submission,
            "submitted_at": contact_submission.submitted_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "admin_url": f"{base_url}/admin/cms/visitorcontact/{contact_submission.pk}/change/",
            "club_name": config.club_name if config else "Club",
            "club_logo_url": get_absolute_club_logo_url(config),
            "site_url": getattr(settings, "SITE_URL", None),
        }

        # Render HTML and plain text templates
        html_message = render_to_string("cms/emails/visitor_contact.html", context)
        text_message = render_to_string("cms/emails/visitor_contact.txt", context)

        # Send email to each member manager
        recipient_emails = [
            manager.email for manager in member_managers if manager.email
        ]

        if recipient_emails:
            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_emails,
                html_message=html_message,
                fail_silently=False,  # We want to know if email fails
            )

        # Also create notifications in the system if available
        try:
            from notifications.models import Notification

            for manager in member_managers:
                notification_message = (
                    f"New visitor contact from {contact_submission.name}: "
                    f"{contact_submission.subject}"
                )

                notification_url = (
                    f"/admin/cms/visitorcontact/{contact_submission.pk}/change/"
                )

                Notification.objects.create(
                    user=manager, message=notification_message, url=notification_url
                )
        except ImportError:
            # Notifications app not available
            pass
        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create notifications for visitor contact: {e}")

    except Exception as e:
        # Log the error but don't fail the contact submission
        logger.error(f"Failed to notify member managers of visitor contact: {e}")


# CMS Edit Forms and Views


class CmsPageForm(forms.ModelForm):
    """Form for editing CMS pages with enhanced TinyMCE."""

    class Meta:
        model = Page
        fields = ["title", "slug", "parent", "content", "is_public"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control form-control-lg"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "content": TinyMCE(attrs={"class": "tinymce-enhanced"}),
            "is_public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class HomePageContentForm(forms.ModelForm):
    """Form for editing homepage content with enhanced TinyMCE."""

    class Meta:
        model = HomePageContent
        fields = ["title", "slug", "audience", "content"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control form-control-lg"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "audience": forms.Select(attrs={"class": "form-select"}),
            "content": TinyMCE(attrs={"class": "tinymce-enhanced"}),
        }


class DocumentForm(forms.ModelForm):
    """Form for uploading documents to CMS pages."""

    class Meta:
        model = Document
        fields = ["file", "title"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Optional: Enter a title for this file",
                }
            )
        }


# Create formset for managing multiple documents
DocumentFormSet = inlineformset_factory(
    Page,
    Document,
    form=DocumentForm,
    fields=["file", "title"],
    extra=1,
    can_delete=True,
)


def can_edit_page(user, page):
    """
    Check if user can edit a specific CMS page.

    Edit permissions are granted to:
    1. Superusers and webmasters (can edit everything)
    2. Members with explicit PageMemberPermission (for any page, public or private)
    3. Officers (directors, secretaries) with the appropriate roles, for both public
       and private pages (via Page.can_user_edit)

    Note: is_public controls VIEW access, not EDIT access. Members and officers assigned
    via PageMemberPermission or role-based rules can edit public pages while they remain
    publicly viewable. This was fixed in Issue #549 to allow content editors for public
    documentation.
    """
    if user is None or not user.is_authenticated:
        return False

    # Webmaster override - can edit everything
    if user.is_superuser or getattr(user, "webmaster", False):
        return True

    # Check EDIT permissions (includes member permissions for both public and private pages)
    return page.can_user_edit(user)


def can_create_in_directory(user, parent_page=None):
    """
    Check if user can create pages in a directory (uses parent page EDIT permissions).

    Note: Members with EDIT permission on a public parent page can create child pages
    under it. The is_public flag controls VIEW access, not EDIT/create access.
    """
    if user is None or not user.is_authenticated:
        return False

    # Webmaster can create anywhere
    if user.is_superuser or getattr(user, "webmaster", False):
        return True

    # If no parent (top-level), only webmaster can create
    if not parent_page:
        return False

    # User needs EDIT permission on parent to create children
    # This checks member permissions for both public and private pages
    return parent_page.can_user_edit(user)


@active_member_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def edit_cms_page(request, page_id):
    """Edit a CMS page with full TinyMCE functionality."""
    page = get_object_or_404(Page, id=page_id)

    # Check page-specific edit permissions
    if not can_edit_page(request.user, page):
        return HttpResponseForbidden("You don't have permission to edit this page.")

    if request.method == "POST":
        form = CmsPageForm(request.POST, instance=page)
        formset = DocumentFormSet(request.POST, request.FILES, instance=page)

        if form.is_valid() and formset.is_valid():
            form.save()

            # Save documents with uploaded_by field
            documents = formset.save(commit=False)
            for document in documents:
                if not document.uploaded_by:
                    document.uploaded_by = request.user
                document.save()

            # Handle deletions
            for document in formset.deleted_objects:
                document.delete()

            # Finalize formset state (commit all changes)

            messages.success(request, f'Page "{page.title}" updated successfully!')
            return redirect(page.get_absolute_url())
    else:
        form = CmsPageForm(instance=page)
        formset = DocumentFormSet(instance=page)

    return render(
        request,
        "cms/edit_page.html",
        {
            "form": form,
            "formset": formset,
            "page": page,
            "page_title": f"Edit Page: {page.title}",
        },
    )


@active_member_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def edit_homepage_content(request, content_id):
    """Edit homepage content with full TinyMCE functionality."""
    # Homepage editing is webmaster-only (no role restrictions)
    if not (
        request.user.is_authenticated
        and (request.user.is_superuser or getattr(request.user, "webmaster", False))
    ):
        return HttpResponseForbidden("Only webmasters can edit homepage content.")

    content = get_object_or_404(HomePageContent, id=content_id)

    if request.method == "POST":
        form = HomePageContentForm(request.POST, instance=content)
        if form.is_valid():
            form.save()
            messages.success(
                request, f'Homepage content "{content.title}" updated successfully!'
            )
            return redirect("homepage")
    else:
        form = HomePageContentForm(instance=content)

    return render(
        request,
        "cms/edit_homepage.html",
        {
            "form": form,
            "content": content,
            "page_title": f"Edit Homepage: {content.title}",
        },
    )


@active_member_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def create_cms_page(request):
    """Create a new CMS page with full TinyMCE functionality.

    Supports creating subpages (Issue #596): when ?parent=<id> is provided,
    the parent field is pre-set and disabled, is_public is inherited from the
    parent, and role/member permissions are copied from the parent after creation.
    """
    # Get parent page if specified
    parent_id = request.GET.get("parent")
    parent_page = None
    is_subpage = False
    if parent_id:
        parent_page = get_object_or_404(Page, id=parent_id)
        is_subpage = True

    # Check creation permissions
    if not can_create_in_directory(request.user, parent_page):
        return HttpResponseForbidden(
            "You don't have permission to create pages in this directory."
        )

    if request.method == "POST":
        form = CmsPageForm(request.POST)
        formset = DocumentFormSet(request.POST, request.FILES)

        # When creating a subpage, the parent field is disabled in the form
        # so it won't be in POST data. We must set it on the instance before save.
        if is_subpage:
            form.instance.parent = parent_page

        if form.is_valid() and formset.is_valid():
            page = form.save()

            # Copy permissions from parent page (Issue #596)
            if is_subpage and parent_page:
                # Copy role permissions (VIEW access)
                for role_perm in parent_page.role_permissions.all():
                    PageRolePermission.objects.get_or_create(
                        page=page, role_name=role_perm.role_name
                    )
                # Copy member permissions (EDIT access)
                for member_perm in parent_page.member_permissions.all():
                    PageMemberPermission.objects.get_or_create(
                        page=page, member=member_perm.member
                    )

            # Save documents with uploaded_by field
            formset.instance = page
            documents = formset.save(commit=False)
            for document in documents:
                document.page = page
                if not document.uploaded_by:
                    document.uploaded_by = request.user
                document.save()

            # Finalize formset changes (e.g., deletions, post-save hooks)
            formset.save()

            messages.success(request, f'Page "{page.title}" created successfully!')
            return redirect(page.get_absolute_url())
    else:
        initial = {}
        if is_subpage and parent_page:
            initial["parent"] = parent_page.id
            initial["is_public"] = parent_page.is_public
        form = CmsPageForm(initial=initial)

        # Disable the parent field when creating a subpage (Issue #596)
        if is_subpage:
            form.fields["parent"].disabled = True

        formset = DocumentFormSet(queryset=Document.objects.none())

    # Build page title to include parent context for subpages
    if is_subpage and parent_page:
        page_title = f'Create Subpage under "{parent_page.title}"'
    else:
        page_title = "Create New CMS Page"

    return render(
        request,
        "cms/create_page.html",
        {
            "form": form,
            "formset": formset,
            "page_title": page_title,
            "parent_page": parent_page,
            "is_subpage": is_subpage,
        },
    )


# Create your views here.
