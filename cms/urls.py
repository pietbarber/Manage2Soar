from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.homepage, name='home'),
    # /cms/<slug>/ or /cms/<parent>/<slug>/ (supports up to 3 levels for now)
    re_path(r'^(?P<slug1>[-\w]+)/$', views.cms_page, name='cms_page'),
    re_path(r'^(?P<slug1>[-\w]+)/(?P<slug2>[-\w]+)/$',
            views.cms_page, name='cms_page_nested'),
    re_path(r'^(?P<slug1>[-\w]+)/(?P<slug2>[-\w]+)/(?P<slug3>[-\w]+)/$',
            views.cms_page, name='cms_page_nested2'),
]
