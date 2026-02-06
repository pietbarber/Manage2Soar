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
    # CMS page routing - supports up to MAX_CMS_DEPTH levels of nesting (Issue #596)
    # Single catch-all pattern handles any depth from 1 to 10 slug segments.
    # Excludes reserved paths (edit, create, admin, etc.) from CMS routing.
    re_path(
        r"^(?!(?:admin|debug|api|static|media|favicon\.ico|robots\.txt|feedback|contact|edit|create)/)(?P<path>[-\w]+(?:/[-\w]+)*)/$",
        views.cms_page,
        name="cms_page",
    ),
]
