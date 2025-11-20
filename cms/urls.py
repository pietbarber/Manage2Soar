from django.urls import path, re_path

from . import views

app_name = "cms"

urlpatterns = [
    # CMS Resources index page at /cms/
    path("", views.cms_resources_index, name="resources"),
    # CMS Edit pages
    path("edit/page/<int:page_id>/", views.edit_cms_page, name="edit_page"),
    path(
        "edit/homepage/<int:content_id>/",
        views.edit_homepage_content,
        name="edit_homepage",
    ),
    path("create/page/", views.create_cms_page, name="create_page"),
    # Site feedback URLs (Issue #117)
    path("feedback/", views.submit_feedback, name="feedback"),
    path("feedback/success/", views.feedback_success, name="feedback_success"),
    # Visitor contact URLs (Issue #70)
    path("contact/", views.contact, name="contact"),
    path("contact/success/", views.contact_success, name="contact_success"),
    # /cms/<slug>/ or /cms/<parent>/<slug>/ (supports up to 3 levels for now)
    # Exclude common reserved paths (admin, debug, api, etc.) from CMS routing
    re_path(
        r"^(?!(?:admin|debug|api|static|media|favicon\.ico|robots\.txt|feedback|contact)/)(?P<slug1>[-\w]+)/$",
        views.cms_page,
        name="cms_page",
    ),
    re_path(
        r"^(?P<slug1>[-\w]+)/(?P<slug2>[-\w]+)/$",
        views.cms_page,
        name="cms_page_nested",
    ),
    re_path(
        r"^(?P<slug1>[-\w]+)/(?P<slug2>[-\w]+)/(?P<slug3>[-\w]+)/$",
        views.cms_page,
        name="cms_page_nested2",
    ),
]
