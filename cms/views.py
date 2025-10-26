# Generic CMS Page view for arbitrary pages and directories
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.urls import reverse

from cms.models import HomePageContent, SiteFeedback
from cms.forms import SiteFeedbackForm
from members.decorators import active_member_required
from django.db.models import Count, Max
from members.utils import is_active_member

from .models import Page


def cms_page(request, **kwargs):
    # Accepts named kwargs: slug1, slug2, slug3 from urls.py
    import logging

    logger = logging.getLogger("cms.debug")
    slugs = []
    for i in range(1, 4):
        slug = kwargs.get(f"slug{i}")
        if slug:
            slugs.append(slug)
    logger.debug(f"cms_page: slugs={slugs}")
    if not slugs:
        logger.debug("cms_page: No slugs, redirecting to cms:home")
        return redirect("cms:home")
    parent = None
    page = None
    for slug in slugs:
        logger.debug(
            f"cms_page: Looking for Page with slug='{slug}' and parent={parent}"
        )
        page = get_object_or_404(Page, slug=slug, parent=parent)
        parent = page
    logger.debug(f"cms_page: Found page {page}")
    # page is now the deepest resolved page
    # Access control: if the page is not public, require the same membership
    # checks we use for the homepage logic. If the user is not authorized,
    # redirect them to the login page.
    assert page is not None
    if not page.is_public:
        user = request.user
        if not is_active_member(user):
            # Use Django's helper to redirect to login (handles encoding)
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
    # Build subpage metadata (doc counts and last-updated timestamps) to
    # avoid doing this in the template and to prevent N+1 queries.
    # Annotate children with document counts and latest upload to avoid N+1
    subpages = []
    children = (
        page.children.annotate(
            doc_count=Count("documents"), doc_max=Max("documents__uploaded_at")
        )
        .order_by("title")
    )
    for child in children:
        # last updated is the later of the page's updated_at and latest document upload
        last_updated = child.updated_at
        if getattr(child, "doc_max", None) and child.doc_max > last_updated:
            last_updated = child.doc_max
        subpages.append({"page": child, "doc_count": getattr(child, "doc_count", 0),
                        "last_updated": last_updated})

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

    return render(
        request,
        "cms/page.html",
        {"page": page, "subpages": subpages,
            "breadcrumbs": breadcrumbs, "has_documents": has_documents},
    )


def homepage(request):
    # If this request came in under the /cms/ path, show the CMS index
    # of top-level pages rather than any legacy HomePageContent. This
    # keeps the site root (/) behavior unchanged while making
    # /cms/ act as a navigable directory index.
    if request.path.startswith("/cms"):
        from .models import Page

        top_pages_qs = Page.objects.filter(parent__isnull=True).order_by("title")
        pages = []
        for p in top_pages_qs:
            # Determine whether the current user may view links in this directory
            can_view = True
            if not p.is_public:
                from members.utils import is_active_member

                can_view = is_active_member(request.user)

            # Only include non-public pages in the listing if the user may view them;
            # otherwise, skip showing restricted directories to anonymous visitors.
            if not p.is_public and not can_view:
                continue

            pages.append(
                {
                    "page": p,
                    # Count documents plus child directories as resources
                    "doc_count": p.documents.count() + p.children.count(),
                    "is_public": p.is_public,
                    "can_view": can_view,
                }
            )
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

    # Fallback: show CMS index of top-level pages
    from .models import Page

    top_pages_qs = Page.objects.filter(parent__isnull=True).order_by("title")
    pages = []
    for p in top_pages_qs:
        can_view = True
        if not p.is_public:
            from members.utils import is_active_member

            can_view = is_active_member(request.user)

        if not p.is_public and not can_view:
            continue

        pages.append(
            {
                "page": p,
                # Include directories in the resource count so directories show up as resources
                "doc_count": p.documents.count() + p.children.count(),
                "is_public": p.is_public,
                "can_view": can_view,
            }
        )
    return render(request, "cms/index.html", {"pages": pages})


# Site Feedback Views for Issue #117

@active_member_required
def submit_feedback(request):
    """
    View for submitting site feedback.
    Captures referring URL and notifies webmasters.
    """
    referring_url = request.GET.get('from', request.META.get('HTTP_REFERER', ''))

    if request.method == 'POST':
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
                "Thank you for your feedback! Webmasters have been notified and will respond soon."
            )
            return redirect('cms:feedback_success')
    else:
        form = SiteFeedbackForm()

    return render(request, 'cms/feedback_form.html', {
        'form': form,
        'referring_url': referring_url,
    })


@active_member_required
def feedback_success(request):
    """Simple success page after feedback submission."""
    return render(request, 'cms/feedback_success.html')


def _notify_webmasters_of_feedback(feedback):
    """
    Send notifications to all webmasters about new feedback.
    """
    try:
        from notifications.models import Notification
        from members.models import Member

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
                    user=webmaster,
                    message=notification_message,
                    url=notification_url
                )
            except Exception as e:
                # Log but don't fail - feedback submission should still work
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to notify webmaster {webmaster}: {e}")

    except ImportError:
        # Notifications app not available
        pass
    except Exception as e:
        # Log but don't fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to notify webmasters of feedback: {e}")


# Create your views here.
