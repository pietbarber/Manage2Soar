###################################################################################
# URL configuration for Manage2Soar project.
#
# The `urlpatterns` list routes URLs to views. For more information please see:
#    https://docs.djangoproject.com/en/5.1/topics/http/urls/
# Examples:
# Function views
#    1. Add an import:  from my_app import views
#    2. Add a URL to urlpatterns:  path('', views.home, name='home')
# Class-based views
#    1. Add an import:  from other_app.views import Home
#    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
# Including another URLconf
#     1. Import the include() function: from django.urls import include, path
#     2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
###################################################################################


from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView

from cms import views as cms_views
from instructors import views as instr_views
from members import views as members_views
from members.api import email_lists
from siteconfig.models import SiteConfiguration


def service_worker_view(request):
    """Serve service worker with dynamic cache version based on build hash."""
    import hashlib
    import os
    import re
    from datetime import date

    # Compute service worker path once
    sw_path = os.path.join(settings.BASE_DIR, "static", "js", "service-worker.js")

    # Generate a cache version hash from:
    # 1. BUILD_HASH env var (set during Docker build)
    # 2. Or fall back to service worker file mtime
    # 3. Or fall back to current date (changes daily)
    build_hash = os.environ.get("BUILD_HASH", "")

    if not build_hash:
        # Use try-except to avoid TOCTOU vulnerability
        try:
            mtime = os.path.getmtime(sw_path)
            build_hash = hashlib.md5(
                str(mtime).encode(), usedforsecurity=False
            ).hexdigest()[:8]
        except (FileNotFoundError, OSError):
            # Fall back to date-based hash (changes daily)
            build_hash = hashlib.md5(
                str(date.today()).encode(), usedforsecurity=False
            ).hexdigest()[:8]

    cache_name = f"manage2soar-{build_hash}"

    # Read the service worker template and inject the cache name
    try:
        with open(sw_path) as f:
            content = f.read()
        # Replace the cache name using regex for flexibility
        content = re.sub(
            r"const CACHE_NAME = '[^']+';",
            f"const CACHE_NAME = '{cache_name}';",
            content,
        )
    except OSError:
        # Minimal no-op service worker if file not found or cannot be read
        content = "// Service worker file not found"

    return HttpResponse(
        content,
        content_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


def _club_pwa_icon_url():
    """Return the URL for the club-branded PWA/Apple touch icon if one has been
    generated from the club logo, otherwise fall back to the default static icon.

    The result is cached under 'pwa_club_icon_url' to avoid a GCS network call
    on every manifest/apple-touch-icon request.  The cache entry is invalidated
    by SiteConfiguration.save() whenever a new club logo is processed.
    """
    from django.core.cache import cache
    from django.core.files.storage import default_storage

    from utils.favicon import PWA_CLUB_ICON_NAME

    cached = cache.get("pwa_club_icon_url")
    if cached is not None:
        return cached

    if default_storage.exists(PWA_CLUB_ICON_NAME):
        url = default_storage.url(PWA_CLUB_ICON_NAME)
    else:
        url = f"{settings.STATIC_URL.rstrip('/')}/images/pwa-icon-192.png"

    # Cache for 5 minutes; invalidated on logo upload via SiteConfiguration.save()
    cache.set("pwa_club_icon_url", url, timeout=300)
    return url


def manifest_view(request):
    """Serve PWA manifest from Django to avoid CORS issues with GCS."""
    # Get the static URL prefix for icon paths
    static_url = settings.STATIC_URL.rstrip("/")

    # Use the club name from SiteConfiguration so the shortcut is branded correctly.
    # Guard against DB-not-ready errors (migrations, startup) the same way
    # utils.url_helpers.get_canonical_url() does.
    try:
        from django.db.utils import OperationalError, ProgrammingError

        siteconfig = SiteConfiguration.objects.first()
        club_name = (
            siteconfig.club_name
            if siteconfig and siteconfig.club_name
            else "Manage2Soar"
        )
    except (OperationalError, ProgrammingError):
        club_name = "Manage2Soar"
    # Short name: use first word of club name, capped at 12 characters for home screen.
    # `split()` on an all-whitespace string returns [] which would raise IndexError,
    # so guard against that case explicitly.
    club_name_parts = club_name.split() if club_name else []
    short_name = club_name_parts[0][:12] if club_name_parts else "M2S"

    # Use club-branded icon when available, fall back to the default static icon
    club_icon_url = _club_pwa_icon_url()

    manifest = {
        "name": club_name,
        "short_name": short_name,
        "description": "Soaring club management - members, flights, instruction, and operations",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#212529",
        "orientation": "any",
        "icons": [
            {
                "src": club_icon_url,
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": f"{static_url}/images/pwa-icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
        "categories": ["business", "productivity"],
        "lang": "en-US",
    }
    return JsonResponse(manifest)


def apple_touch_icon_view(request):
    """Redirect Apple touch icon requests to the club-branded PWA icon.

    iOS/Safari requests /apple-touch-icon.png and /apple-touch-icon-precomposed.png
    when a user adds the site to their home screen.  When a club logo has been
    uploaded, this serves the club-branded 192×192 icon; otherwise it falls back
    to the default static PWA icon.  Without this handler those requests result
    in 404 errors in the logs.

    Uses a 302 (temporary) redirect rather than 301 (permanent) so that clients
    don't cache the fallback URL permanently — if a club logo is uploaded later
    the next request will pick up the branded icon without requiring a cache flush.
    """
    from django.http import HttpResponseRedirect

    return HttpResponseRedirect(_club_pwa_icon_url())


urlpatterns = [
    path("admin/", admin.site.urls),
    path("members/", include("members.urls")),
    path("logsheet/", include(("logsheet.urls", "logsheet"), namespace="logsheet")),
    path("instructors/", include("instructors.urls")),
    path("duty_roster/", include("duty_roster.urls")),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("oauth/", include("social_django.urls", namespace="social")),
    path("cms/", include("cms.urls")),
    path(
        "password-reset/",
        members_views.CustomPasswordResetView.as_view(
            html_email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path(
        "TRAINING/Syllabus/full/",
        instr_views.public_syllabus_full,
        name="public_syllabus_full",
    ),
    path(
        "TRAINING/Syllabus/",
        instr_views.public_syllabus_overview,
        name="public_syllabus_overview",
    ),
    path(
        "TRAINING/Syllabus/<str:code>.shtml",
        instr_views.public_syllabus_detail,
        name="public_syllabus_detail",
    ),
    path(
        "TRAINING/Syllabus/<str:code>/",
        instr_views.public_syllabus_detail,
        name="public_syllabus_detail",
    ),
    path(
        "TRAINING/Syllabus/<str:code>/qr.png",
        instr_views.public_syllabus_qr,
        name="public_syllabus_qr",
    ),
    path("analytics/", include("analytics.urls")),
    # API endpoints for mail server integration
    path("api/email-lists/", email_lists, name="api_email_lists"),
    path("avatar/<str:username>.png", members_views.pydenticon_view, name="pydenticon"),
    # Public contact form for visitors (no authentication required)
    path("contact/", cms_views.contact, name="contact"),
    path("contact/success/", cms_views.contact_success, name="contact_success"),
    path("", include("knowledgetest.urls")),
    # Homepage at root level - separate from CMS resources
    path("", cms_views.homepage, name="home"),
    # Notifications app
    path("notifications/", include("notifications.urls")),
    # PWA Support
    path(
        "offline/", TemplateView.as_view(template_name="offline.html"), name="offline"
    ),
    path("service-worker.js", service_worker_view, name="service-worker"),
    path("manifest.json", manifest_view, name="manifest"),
    # Apple touch icon - iOS/Safari requests these when adding to home screen
    path("apple-touch-icon.png", apple_touch_icon_view, name="apple-touch-icon"),
    path(
        "apple-touch-icon-precomposed.png",
        apple_touch_icon_view,
        name="apple-touch-icon-precomposed",
    ),
]

# Serve media files in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
