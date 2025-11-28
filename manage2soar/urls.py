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
from django.http import FileResponse
from django.urls import include, path
from django.views.generic import TemplateView

from cms import views as cms_views
from instructors import views as instr_views
from members import views as members_views


def service_worker_view(request):
    """Serve service worker from root URL for proper scope."""
    import os

    sw_path = os.path.join(
        settings.STATIC_ROOT or settings.BASE_DIR / "static", "js", "service-worker.js"
    )
    # Fallback to static dir if collectstatic hasn't run
    if not os.path.exists(sw_path):
        sw_path = os.path.join(settings.BASE_DIR, "static", "js", "service-worker.js")
    return FileResponse(
        open(sw_path, "rb"),
        content_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


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
        "password-reset/", auth_views.PasswordResetView.as_view(), name="password_reset"
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
]

# Serve media files in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
