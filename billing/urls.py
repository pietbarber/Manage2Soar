from django.urls import path

from billing import views

app_name = "billing"

urlpatterns = [
    path("ledgers/", views.ledger_list, name="ledger_list"),
    path("ledgers/<int:member_id>/", views.ledger_detail, name="ledger_detail"),
    path("entries/<int:entry_id>/reverse/", views.reverse_entry, name="entry_reverse"),
]
