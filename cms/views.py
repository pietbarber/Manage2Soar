# Generic CMS Page view for arbitrary pages and directories
from django.shortcuts import render
from django.shortcuts import redirect
from cms.models import HomePageContent
from django.shortcuts import get_object_or_404
from .models import Page


def cms_page(request, **kwargs):
    # Accepts named kwargs: slug1, slug2, slug3 from urls.py
    import logging
    logger = logging.getLogger("cms.debug")
    slugs = []
    for i in range(1, 4):
        slug = kwargs.get(f'slug{i}')
        if slug:
            slugs.append(slug)
    logger.debug(f"cms_page: slugs={slugs}")
    if not slugs:
        logger.debug("cms_page: No slugs, redirecting to home")
        return redirect('home')
    parent = None
    page = None
    for slug in slugs:
        logger.debug(
            f"cms_page: Looking for Page with slug='{slug}' and parent={parent}")
        page = get_object_or_404(Page, slug=slug, parent=parent)
        parent = page
    logger.debug(f"cms_page: Found page {page}")
    # page is now the deepest resolved page
    return render(request, 'cms/page.html', {'page': page})


def homepage(request):
    user = request.user
    allowed_statuses = [
        "Full Member", "Student Member", "Family Member", "Service Member",
        "Founding Member", "Honorary Member", "Emeritus Member",
        "SSEF Member", "Temporary Member", "Introductory Member"
    ]
    if user.is_authenticated and (
        user.is_superuser or getattr(
            user, "membership_status", None) in allowed_statuses
    ):
        page = HomePageContent.objects.filter(
            audience='member', slug='member-home').first()
    else:
        page = HomePageContent.objects.filter(
            audience='public', slug='home').first()
    return render(request, 'cms/homepage.html', {'page': page})

# Create your views here.
