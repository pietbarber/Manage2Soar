from django.urls import path
from .views import dashboard

app_name = "analytics"
urlpatterns = [
    path("", dashboard, name="dashboard"),
]
