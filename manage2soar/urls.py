"""
URL configuration for Manage2Soar project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static
from members import views as member_views
from django.contrib.auth import views as auth_views
from django.urls import include
from instructors import views as instr_views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('members/', include('members.urls')),
    path('logsheet/', include(('logsheet.urls', 'logsheet'), namespace='logsheet')),
    path('instructors/', include('instructors.urls')),
    path("duty_roster/", include("duty_roster.urls")),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('oauth/', include('social_django.urls', namespace='social')),
    path("", member_views.home, name="home"),
    path("password-reset/", auth_views.PasswordResetView.as_view(),
         name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(),
         name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(),
         name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(),
         name="password_reset_complete"),

    path("TRAINING/Syllabus/full/", instr_views.public_syllabus_full,
         name="public_syllabus_full"),
    path("TRAINING/Syllabus/",
         instr_views.public_syllabus_overview, name="public_syllabus_overview"),
    path("TRAINING/Syllabus/<str:code>.shtml",
         instr_views.public_syllabus_detail,   name="public_syllabus_detail"),
    path("TRAINING/Syllabus/<str:code>/",
         instr_views.public_syllabus_detail,   name="public_syllabus_detail"),
    path("TRAINING/Syllabus/<str:code>/qr.png",
         instr_views.public_syllabus_qr, name="public_syllabus_qr"),
    path("analytics/", include("analytics.urls")),
    path("", include('knowledgetest.urls'))


]

# Serve media files in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
