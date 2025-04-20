from django.urls import path
from . import views

app_name = "duty_roster"

urlpatterns = [
    path("", views.roster_home, name="roster_home"),
    path("blackout/", views.blackout_manage, name="blackout_manage"),

]
