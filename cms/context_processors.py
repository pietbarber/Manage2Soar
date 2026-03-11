from django.conf import settings
from django.urls import reverse

from cms.models import HomePageContent, Page
from members.utils import is_active_member
from siteconfig.models import SiteConfiguration


def _build_resources_nav_items(request):
    """Build ordered Resources drawer links for the current user."""
    items = [
        {
            "title": "Document Root",
            "url": reverse("cms:resources"),
            "rank": 0,
        }
    ]

    access_request = request if hasattr(request, "session") else None

    promoted_pages = (
        Page.objects.filter(promote_to_navbar=True)
        .prefetch_related("role_permissions", "member_permissions")
        .order_by("navbar_rank", "id")
    )
    for page in promoted_pages:
        if page.can_user_access(request.user, access_request):
            items.append(
                {
                    "title": page.effective_navbar_title(),
                    "url": page.get_absolute_url(),
                    "rank": page.navbar_rank,
                }
            )

    # Relocated utility links (issue #746 IA update).
    items.append(
        {
            "title": "Gliders and Towplanes",
            "url": reverse("logsheet:equipment_list"),
            "rank": 900,
        }
    )

    if request.user.is_authenticated and is_active_member(request.user):
        items.append(
            {
                "title": "Report Website Issue",
                "url": reverse("cms:feedback"),
                "rank": 910,
            }
        )
        items.append(
            {
                "title": "Safety Suggestion Box",
                "url": reverse("members:safety_report_submit"),
                "rank": 920,
            }
        )

    if request.user.is_authenticated and (
        getattr(request.user, "safety_officer", False) or request.user.is_superuser
    ):
        items.append(
            {
                "title": "Suggestion Box Reports",
                "url": reverse("members:safety_report_list"),
                "rank": 930,
            }
        )

    webcam_url = SiteConfiguration.objects.values_list(
        "webcam_snapshot_url", flat=True
    ).first()
    if request.user.is_authenticated and is_active_member(request.user) and webcam_url:
        items.append(
            {
                "title": "Webcam",
                "url": reverse("siteconfig:webcam"),
                "rank": 940,
            }
        )

    return sorted(items, key=lambda item: (item["rank"], item["title"].lower()))


def footer_content(request):
    """
    Context processor to add footer content to all templates.
    Only loads footer content for authenticated users.
    """
    google_oauth_configured = bool(
        getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY", None)
    )

    if request.user.is_authenticated:
        try:
            footer = HomePageContent.objects.filter(
                slug="footer", audience="member"
            ).first()
            return {
                "footer_content": footer,
                "google_oauth_configured": google_oauth_configured,
                "resources_nav_items": _build_resources_nav_items(request),
            }
        except Exception:
            # If CMS is not available or footer doesn't exist, fail gracefully
            return {
                "footer_content": None,
                "google_oauth_configured": google_oauth_configured,
                "resources_nav_items": _build_resources_nav_items(request),
            }
    else:
        return {
            "footer_content": None,
            "google_oauth_configured": google_oauth_configured,
            "resources_nav_items": _build_resources_nav_items(request),
        }
