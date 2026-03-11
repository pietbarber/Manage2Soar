from html.parser import HTMLParser
from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse

from cms.models import HomePageContent, Page
from members.utils import is_active_member
from siteconfig.templatetags.siteconfig_tags import webcam_enabled


class _AnchorExtractor(HTMLParser):
    """Extract simple anchor tags from HTML content."""

    def __init__(self):
        super().__init__()
        self.links = []
        self._current_href = None
        self._text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_map = dict(attrs)
        self._current_href = attrs_map.get("href")
        self._text_parts = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self._current_href is None:
            return
        title = "".join(self._text_parts).strip()
        if self._current_href and title:
            self.links.append((title, self._current_href))
        self._current_href = None
        self._text_parts = []


def _extract_footer_links(footer):
    """Extract title/url tuples from CMS footer rich text."""
    if not footer or not footer.content:
        return []
    parser = _AnchorExtractor()
    parser.feed(footer.content)
    parser.close()
    return parser.links


def _is_safe_nav_url(url):
    """Allow relative URLs and absolute http(s) URLs only."""
    if not url:
        return False
    parsed = urlparse(url)
    if not parsed.scheme:
        # Reject protocol-relative URLs (e.g. //example.com).
        return not parsed.netloc
    return parsed.scheme in {"http", "https"}


def _dedupe_resource_items(items):
    """Remove duplicate entries by URL while preserving first occurrence order."""
    seen_urls = set()
    deduped = []
    for item in items:
        url = item.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(item)
    return deduped


def _build_resources_nav_items(request, footer=None):
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
        Page.objects.filter(promote_to_navbar=True, navbar_rank__isnull=False)
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

    if request.user.is_authenticated and is_active_member(request.user):
        # Relocated utility links (issue #746 IA update).
        items.append(
            {
                "title": "Gliders and Towplanes",
                "url": reverse("logsheet:equipment_list"),
                "rank": 900,
            }
        )
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

        # Promote member footer links (Weather/WeGlide/etc.) into Resources drawer.
        for idx, (title, url) in enumerate(_extract_footer_links(footer), start=0):
            if not _is_safe_nav_url(url):
                continue
            items.append(
                {
                    "title": title,
                    "url": url,
                    "rank": 950 + idx,
                }
            )

    if request.user.is_authenticated and (
        getattr(request.user, "safety_officer", False) or request.user.is_superuser
    ):
        items.append(
            {
                "title": "Safety Dashboard",
                "url": reverse("members:safety_officer_dashboard"),
                "rank": 925,
            }
        )
        items.append(
            {
                "title": "Suggestion Box Reports",
                "url": reverse("members:safety_report_list"),
                "rank": 930,
            }
        )

    if request.user.is_authenticated and is_active_member(request.user):
        if webcam_enabled():
            items.append(
                {
                    "title": "Webcam",
                    "url": reverse("siteconfig:webcam"),
                    "rank": 940,
                }
            )

    items = _dedupe_resource_items(items)
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
                "resources_nav_items": _build_resources_nav_items(request, footer),
            }
        except Exception:
            # If CMS is not available or an unexpected error occurs, fail gracefully.
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
