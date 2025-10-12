from django.urls import path
from . import views

urlpatterns = [
    path('', views.notifications_list, name='notifications_list'),
    path('dismiss/<int:pk>/', views.dismiss_notification,
         name='dismiss_notification'),
]
