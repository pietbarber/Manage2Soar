# Generic CMS Page view for arbitrary pages and directories
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render

from cms.models import HomePageContent
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
            # Use LOGIN_URL and preserve next
            login_url = settings.LOGIN_URL
            return redirect(f"{login_url}?next={request.path}")
    return render(request, "cms/page.html", {"page": page})


def homepage(request):
    # If this request came in under the /cms/ path, show the CMS index
    # of top-level pages rather than any legacy HomePageContent. This
    # keeps the site root (/) behavior unchanged while making
    # /cms/ act as a navigable directory index.
    if request.path.startswith("/cms"):
        from .models import Page

        top_pages = Page.objects.filter(parent__isnull=True).order_by("title")
        pages = []
        for p in top_pages:
            pages.append(
                {
                    "page": p,
                    "doc_count": p.documents.count(),
                    "is_public": p.is_public,
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

    top_pages = Page.objects.filter(parent__isnull=True).order_by("title")
    pages = []
    for p in top_pages:
        pages.append(
            {
                "page": p,
                "doc_count": p.documents.count(),
                "is_public": p.is_public,
            }
        )
    return render(request, "cms/index.html", {"pages": pages})


# Create your views here.
