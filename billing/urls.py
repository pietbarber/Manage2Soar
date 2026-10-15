from django.urls import path

from billing import ledger_views, views

app_name = "billing"

urlpatterns = [
    path("ledgers/", views.ledger_list, name="ledger_list"),
    path("periods/", views.billing_period_list, name="period_list"),
    path("periods/close/", views.close_billing_period, name="period_close"),
    path(
        "periods/<int:period_id>/reopen/",
        views.reopen_billing_period,
        name="period_reopen",
    ),
    path("ledgers/<int:member_id>/", views.ledger_detail, name="ledger_detail"),
    path(
        "ledgers/<int:member_id>/export/",
        views.ledger_detail_csv,
        name="ledger_detail_csv",
    ),
    path(
        "ledgers/<int:member_id>/opening-balance-override/",
        views.override_opening_balance_view,
        name="opening_balance_override",
    ),
    path("entries/<int:entry_id>/reverse/", views.reverse_entry, name="entry_reverse"),
    path(
        "entries/<int:entry_id>/remit/",
        views.remit_guest_payment_entry,
        name="guest_payment_remit",
    ),
    # Club books (double-entry general ledger) under the Club Finances menu.
    path("books/", ledger_views.club_ledger, name="club_ledger"),
    path("books/export/", ledger_views.club_ledger_csv, name="club_ledger_csv"),
    path("books/accounts/", ledger_views.chart_of_accounts, name="chart_of_accounts"),
    path("books/accounts/new/", ledger_views.account_edit, name="account_create"),
    path(
        "books/accounts/<int:account_id>/",
        ledger_views.account_register_view,
        name="account_register",
    ),
    path(
        "books/accounts/<int:account_id>/export/",
        ledger_views.account_register_csv,
        name="account_register_csv",
    ),
    path(
        "books/accounts/<int:account_id>/edit/",
        ledger_views.account_edit,
        name="account_edit",
    ),
    path("books/expense/", ledger_views.record_expense, name="record_expense"),
    path("books/income/", ledger_views.record_income, name="record_income"),
    path("books/transfer/", ledger_views.cash_transfer, name="cash_transfer"),
    path("books/journal/", ledger_views.general_journal, name="general_journal"),
    path(
        "books/entries/<int:entry_id>/",
        ledger_views.journal_detail,
        name="journal_detail",
    ),
    path(
        "books/entries/<int:entry_id>/reverse/",
        ledger_views.journal_reverse,
        name="journal_reverse",
    ),
]
