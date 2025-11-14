# Generic CMS Page view for arbitrary pages and directories
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from cms.forms import SiteFeedbackForm, VisitorContactForm
from cms.models import HomePageContent
from members.decorators import active_member_required
from members.utils import is_active_member

from .models import Page

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


def get_accessible_top_level_pages(user):
    """
    Get accessible top-level CMS pages for a user with optimized queries.

    Args:
        user: The user to check access for

    Returns:
        list: List of page dictionaries with metadata
    """
    from django.db.models import Count

    from .models import Page

    # Use annotate to compute counts in a single query, avoiding N+1 queries
    top_pages_qs = (
        Page.objects.filter(parent__isnull=True)
        .prefetch_related("role_permissions")
        .annotate(doc_count=Count("documents"), child_count=Count("children"))
        .order_by("title")
    )

    pages = []
    for p in top_pages_qs:
        # Use the page's built-in access control method
        can_view = p.can_user_access(user)

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
    # Accepts named kwargs: slug1, slug2, slug3 from urls.py
    debug_logger = logging.getLogger("cms.debug")
    slugs = []
    for i in range(1, 4):
        slug = kwargs.get(f"slug{i}")
        if slug:
            slugs.append(slug)
    debug_logger.debug(f"cms_page: slugs={slugs}")
    if not slugs:
        debug_logger.debug("cms_page: No slugs, redirecting to cms:home")
        return redirect("cms:home")
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
    if not page.can_user_access(request.user):
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
        if not child.can_user_access(request.user):
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
        resources_url = reverse("cms:home")
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
        },
    )


def homepage(request):
    # If this request came in under the /cms/ path, show the CMS index
    # of top-level pages rather than any legacy HomePageContent. This
    # keeps the site root (/) behavior unchanged while making
    # /cms/ act as a navigable directory index.
    if request.path.startswith("/cms"):
        # Use helper function to get accessible pages with optimized queries
        pages = get_accessible_top_level_pages(request.user)
        return render(request, "cms/index.html", {"pages": pages})

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
    # First, try to render legacy HomePageContent if it exists for the
    # appropriate audience. If not found, fall back to a navigable index
    # of top-level CMS Pages (directories).
    page = None
    if user.is_authenticated and (
        user.is_superuser
        or getattr(user, "membership_status", None) in allowed_statuses
    ):
        page = HomePageContent.objects.filter(
            audience="member", slug="member-home"
        ).first()
    else:
        page = HomePageContent.objects.filter(audience="public", slug="home").first()

    if page:
        return render(request, "cms/homepage.html", {"page": page})

    # Fallback: show CMS index of top-level pages using optimized helper function
    pages = get_accessible_top_level_pages(request.user)
    return render(request, "cms/index.html", {"pages": pages})


# Site Feedback Views for Issue #117


@active_member_required
def submit_feedback(request):
    """
    View for submitting site feedback.
    Captures referring URL and notifies webmasters.
    """
    referring_url = request.GET.get("from", request.headers.get("referer", ""))

    if request.method == "POST":
        form = SiteFeedbackForm(request.POST)
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
    """
    if request.method == "POST":
        form = VisitorContactForm(request.POST)
        if form.is_valid():
            contact_submission = form.save(commit=False)

            # Capture IP address for spam prevention
            contact_submission.ip_address = _get_client_ip(request)
            contact_submission.save()

            # Send notification to member managers
            _notify_member_managers_of_contact(contact_submission)

            messages.success(
                request, "Thank you for contacting us! We'll get back to you soon."
            )
            return redirect("cms:contact_success")
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
        from django.core.mail import send_mail

        from members.models import Member
        from siteconfig.models import SiteConfiguration

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

        message = f"""
A new visitor has contacted the club through the website.

Visitor Details:
- Name: {safe_name}
- Email: {safe_email}
- Phone: {safe_phone}
- Subject: {safe_user_subject}
- Submitted: {contact_submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}

Message:
{safe_message}

---
You can respond directly to this visitor at: {safe_email}

To manage this contact in the admin interface:
{settings.SITE_URL if hasattr(settings, 'SITE_URL') else f'https://{site_config.domain_name}' if site_config and site_config.domain_name else 'https://localhost:8000'}/admin/cms/visitorcontact/{contact_submission.pk}/change/

This message was sent automatically by the club website contact form.
        """.strip()

        # Send email to each member manager
        recipient_emails = [
            manager.email for manager in member_managers if manager.email
        ]

        if recipient_emails:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_emails,
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


# Create your views here.
