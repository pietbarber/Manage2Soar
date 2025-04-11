from django.urls import path
from . import views

app_name = "instructors"

urlpatterns = [
    path("", views.instructors_home, name="index"),

]
