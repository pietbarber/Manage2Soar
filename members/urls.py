from django.contrib.auth import views as auth_views
from django.urls import path, include
from members import views
from . import views
from .views import member_list, member_edit
from django.conf import settings
from django.conf.urls.static import static
from .views import tinymce_image_upload



urlpatterns = [
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('duty_roster/', views.duty_roster, name='duty_roster'),
    path('instructors/', views.instructors_only, name='instructors'),
    path('members/', views.members_list, name='members'),
    path('log_sheets/', views.log_sheets, name='log_sheets'),
    path("", views.member_list, name="member_list"),
    path('<int:pk>/edit/', member_edit, name='member_edit'),
    path('tinymce/', include('tinymce.urls')),
    path('oauth/', include('social_django.urls', namespace='social')),
    path("<int:member_id>/view/", views.member_view, name="member_view"),
    path("badges/", views.badge_board, name="badge_board"),
    path('set-password/', views.set_password, name='set_password'),
    path('<int:member_id>/biography/', views.biography_view, name='biography_view'),
    path("tinymce-upload/", tinymce_image_upload, name="tinymce_image_upload"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.conf.urls import handler403

handler403 = "django.views.defaults.permission_denied"

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

