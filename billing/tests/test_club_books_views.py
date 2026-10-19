import csv
from datetime import timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.urls import reverse

from billing.ledger_services import (
    account_balance,
    get_role_account,
    post_expense,
    post_member_paid_expense,
)
from billing.models import Account, JournalEntry
from members.models import Member
from siteconfig.timezone_utils import get_club_today

GET_PAGES = (
    "billing:club_ledger",
    "billing:club_ledger_csv",
    "billing:chart_of_accounts",
    "billing:account_create",
    "billing:record_expense",
    "billing:record_member_expense",
    "billing:record_income",
    "billing:cash_transfer",
    "billing:general_journal",
    "billing:go_live",
)


@pytest.fixture(autouse=True)
def club_books(enable_club_accounting):
    return enable_club_accounting


@pytest.fixture
def member(db):
    return Member.objects.create_user(
        username="books-member", is_active=True, membership_status="Full Member"
    )


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(
        username="books-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )


@pytest.fixture
def checking(db):
    return Account.objects.create(
        code="101", name="Club Checking", type=Account.Type.ASSET, is_cash=True
    )


def expense(treasurer, checking, memo="Field rent", amount="400.00"):
    return post_expense(
        actor=treasurer,
        date=get_club_today(),
        paid_from=checking,
        expense_account=Account.objects.get(code="500"),
        amount=amount,
        memo=memo,
    )


@pytest.mark.parametrize("name", GET_PAGES)
def test_club_books_pages_require_treasurer(client, member, treasurer, name):
    url = reverse(name)
    assert client.get(url).status_code == 302

    client.force_login(member)
    assert client.get(url).status_code == 403

    client.force_login(treasurer)
    assert client.get(url).status_code == 200


def test_entry_pages_require_treasurer(client, member, treasurer, checking):
    entry = expense(treasurer, checking)
    urls = (
        reverse("billing:journal_detail", args=[entry.pk]),
        reverse("billing:account_register", args=[checking.pk]),
        reverse("billing:account_register_csv", args=[checking.pk]),
        reverse("billing:account_edit", args=[checking.pk]),
    )
    client.force_login(member)
    for url in urls:
        assert client.get(url).status_code == 403
    response = client.post(
        reverse("billing:journal_reverse", args=[entry.pk]),
        {"date": get_club_today().isoformat(), "reason": "No"},
    )
    assert response.status_code == 403
    assert not hasattr(JournalEntry.objects.get(pk=entry.pk), "reversal")

    client.force_login(treasurer)
    for url in urls:
        assert client.get(url).status_code == 200


def test_club_books_redirect_when_disabled(client, treasurer, club_books):
    club_books.club_accounting_enabled = False
    club_books.save(update_fields=["club_accounting_enabled"])
    client.force_login(treasurer)
    response = client.get(reverse("billing:club_ledger"))
    assert response.status_code == 302
    assert response.url == reverse("billing:ledger_list")


def test_record_expense_posts_and_redirects(client, treasurer, checking):
    client.force_login(treasurer)
    response = client.post(
        reverse("billing:record_expense"),
        {
            "date": get_club_today().isoformat(),
            "payee": "Airport authority",
            "expense_account": Account.objects.get(code="500").pk,
            "amount": "425.00",
            "paid_from": checking.pk,
            "memo": "October field rent",
            "reference": "1043",
        },
    )
    entry = JournalEntry.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("billing:journal_detail", args=[entry.pk])
    assert entry.created_by == treasurer
    assert str(account_balance(checking)) == "-425.00"


def test_record_expense_shows_service_errors(client, treasurer, checking):
    client.force_login(treasurer)
    response = client.post(
        reverse("billing:record_expense"),
        {
            "date": "2099-01-01",
            "expense_account": Account.objects.get(code="500").pk,
            "amount": "5",
            "paid_from": checking.pk,
            "memo": "Future",
        },
    )
    assert response.status_code == 200
    assert "Future dates are not allowed" in response.content.decode()
    assert not JournalEntry.objects.exists()


def test_general_journal_posts_balanced_entry(client, treasurer, checking):
    client.force_login(treasurer)
    payable = Account.objects.get(code="200")
    maintenance = Account.objects.get(code="510")
    data = {
        "date": get_club_today().isoformat(),
        "memo": "Annual inspection invoice, unpaid",
        "lines-TOTAL_FORMS": "4",
        "lines-INITIAL_FORMS": "0",
        "lines-0-account": maintenance.pk,
        "lines-0-debit": "800.00",
        "lines-1-account": payable.pk,
        "lines-1-credit": "800.00",
    }
    response = client.post(reverse("billing:general_journal"), data)
    assert response.status_code == 302
    assert account_balance(payable) == 800
    assert account_balance(maintenance) == 800


def test_general_journal_rejects_unbalanced_entry(client, treasurer, checking):
    client.force_login(treasurer)
    data = {
        "date": get_club_today().isoformat(),
        "memo": "Lopsided",
        "lines-TOTAL_FORMS": "2",
        "lines-INITIAL_FORMS": "0",
        "lines-0-account": Account.objects.get(code="510").pk,
        "lines-0-debit": "10.00",
        "lines-1-account": checking.pk,
        "lines-1-credit": "9.00",
    }
    response = client.post(reverse("billing:general_journal"), data)
    assert response.status_code == 200
    assert "must equal credits" in response.content.decode()
    assert not JournalEntry.objects.exists()


def test_general_journal_does_not_offer_member_receivables(client, treasurer):
    client.force_login(treasurer)
    content = client.get(reverse("billing:general_journal")).content.decode()
    assert "Member Receivables" not in content
    assert "Accounts Payable" in content


def test_reverse_entry_view(client, treasurer, checking):
    entry = expense(treasurer, checking)
    client.force_login(treasurer)
    response = client.post(
        reverse("billing:journal_reverse", args=[entry.pk]),
        {"date": get_club_today().isoformat(), "reason": "Paid twice"},
    )
    reversal = JournalEntry.objects.get(reverses=entry)
    assert response.url == reverse("billing:journal_detail", args=[reversal.pk])
    assert account_balance(checking) == 0
    detail = client.get(reverse("billing:journal_detail", args=[entry.pk]))
    assert "Reverse this entry" not in detail.content.decode()


def test_club_ledger_lists_entries_and_cash(client, treasurer, checking):
    expense(treasurer, checking, memo="Hangar electricity")
    client.force_login(treasurer)
    content = client.get(reverse("billing:club_ledger")).content.decode()
    assert "Hangar electricity" in content
    assert "Club Checking" in content
    assert "$-400.00" in content


def test_club_ledger_filters(client, treasurer, checking):
    expense(treasurer, checking, memo="Fuel delivery")
    expense(treasurer, checking, memo="Insurance premium")
    client.force_login(treasurer)
    content = client.get(reverse("billing:club_ledger"), {"q": "fuel"}).content.decode()
    assert "Fuel delivery" in content
    assert "Insurance premium" not in content


def test_club_ledger_csv_sanitizes_cells(client, treasurer, checking):
    expense(treasurer, checking, memo='=HYPERLINK("http://x")')
    client.force_login(treasurer)
    response = client.get(reverse("billing:club_ledger_csv"))
    rows = list(csv.reader(StringIO(response.content.decode())))
    assert rows[0][:4] == ["Date", "Entry", "Source", "Description"]
    assert len(rows) == 3
    assert all(row[3].startswith("'=") for row in rows[1:])
    assert {row[9] or row[10] for row in rows[1:]} == {"400.00"}


def test_account_register_shows_running_balance(client, treasurer, checking):
    expense(treasurer, checking, amount="100.00")
    expense(treasurer, checking, amount="50.00")
    client.force_login(treasurer)
    response = client.get(reverse("billing:account_register", args=[checking.pk]))
    assert response.context["register"]["closing_balance"] == -150


def test_receivables_register_names_member_once(client, treasurer, member):
    member.first_name, member.last_name = "Jack", "Rabbit"
    member.save()
    rent = Account.objects.get(code="500")
    post_member_paid_expense(
        actor=treasurer,
        date=get_club_today(),
        member=member,
        expense_account=rent,
        amount="700.00",
        memo="Field rent paid in cash",
    )
    receivables = get_role_account(Account.Role.MEMBER_RECEIVABLES)
    client.force_login(treasurer)
    response = client.get(reverse("billing:account_register", args=[receivables.pk]))
    html = response.content.decode()
    assert str(member) in html
    assert f"{member}{member}" not in html
    assert html.count(str(member)) == 1


def test_create_and_edit_account(client, treasurer):
    client.force_login(treasurer)
    response = client.post(
        reverse("billing:account_create"),
        {
            "code": "103",
            "name": "Credit Union",
            "type": "asset",
            "is_cash": "on",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    account = Account.objects.get(code="103")
    assert account.is_cash

    response = client.post(
        reverse("billing:account_edit", args=[account.pk]),
        {
            "code": "103",
            "name": "Credit Union Checking",
            "type": "asset",
            "is_cash": "on",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    account.refresh_from_db()
    assert account.name == "Credit Union Checking"


def test_system_account_type_is_locked_in_form(client, treasurer):
    receivables = Account.objects.get(system_role=Account.Role.MEMBER_RECEIVABLES)
    client.force_login(treasurer)
    client.post(
        reverse("billing:account_edit", args=[receivables.pk]),
        {"code": "120", "name": "Receivables", "type": "liability", "is_active": ""},
    )
    receivables.refresh_from_db()
    assert receivables.type == Account.Type.ASSET
    assert receivables.is_active
    assert receivables.name == "Receivables"


def test_club_finances_nav_for_treasurer_only(client, member, treasurer, club_books):
    client.force_login(treasurer)
    content = client.get("/").content.decode()
    assert 'id="clubFinancesDropdown"' in content
    assert reverse("billing:club_ledger") in content
    # Member Billing stays under Log Sheets.
    assert reverse("billing:ledger_list") in content

    client.force_login(member)
    assert 'id="clubFinancesDropdown"' not in client.get("/").content.decode()


@pytest.mark.parametrize("flag", ["club_accounting_enabled", "billing_app_enabled"])
def test_club_finances_nav_hidden_when_disabled(client, treasurer, club_books, flag):
    # Bypass model validation so the template guard is tested on its own.
    type(club_books).objects.filter(pk=club_books.pk).update(**{flag: False})
    cache.clear()
    client.force_login(treasurer)
    assert 'id="clubFinancesDropdown"' not in client.get("/").content.decode()


def go_live_post(**extra):
    checking = Account.objects.get(code="110")
    data = {
        "start_date": (get_club_today() - timedelta(days=1)).isoformat(),
        "banks-TOTAL_FORMS": "2",
        "banks-INITIAL_FORMS": "1",
        "banks-MIN_NUM_FORMS": "0",
        "banks-MAX_NUM_FORMS": "1000",
        "banks-0-account": str(checking.pk),
        "banks-0-name": "Wells Fargo Checking",
        "banks-0-amount": "5000.00",
        "banks-1-account": "",
        "banks-1-name": "",
        "banks-1-amount": "",
    }
    data.update(extra)
    return data


def test_go_live_page_prefills_bank_accounts(client, treasurer):
    client.force_login(treasurer)
    content = client.get(reverse("billing:go_live")).content.decode()
    assert 'value="Checking"' in content
    assert "Start the books" in content
    assert (
        "Go-live setup" in client.get(reverse("billing:club_ledger")).content.decode()
    )


def test_go_live_page_posts_opening_entry(client, treasurer, club_books):
    client.force_login(treasurer)
    response = client.post(
        reverse("billing:go_live"),
        go_live_post(
            **{"banks-1-name": "Credit Union Savings", "banks-1-amount": "250"}
        ),
    )
    entry = JournalEntry.objects.get(source=JournalEntry.Source.OPENING)
    assert response.status_code == 302
    assert response["Location"] == reverse("billing:journal_detail", args=[entry.pk])
    assert Account.objects.get(code="110").name == "Wells Fargo Checking"
    assert account_balance(Account.objects.get(code="111")) == 250
    general_fund = Account.objects.get(system_role=Account.Role.GENERAL_FUND)
    assert account_balance(general_fund) == 5250

    content = client.get(reverse("billing:go_live")).content.decode()
    assert "Replace opening balances" in content
    assert 'value="5000.00"' in content
    assert (
        "Go-live setup"
        not in client.get(reverse("billing:club_ledger")).content.decode()
    )


def test_go_live_page_requires_name_for_new_account(client, treasurer):
    client.force_login(treasurer)
    response = client.post(
        reverse("billing:go_live"), go_live_post(**{"banks-1-amount": "10"})
    )
    assert response.status_code == 200
    assert "Name the new bank account." in response.content.decode()
    assert not JournalEntry.objects.exists()


def test_go_live_page_locked_after_other_entries(client, treasurer):
    client.force_login(treasurer)
    client.post(reverse("billing:go_live"), go_live_post())
    expense(treasurer, Account.objects.get(code="110"))

    response = client.get(reverse("billing:go_live"))
    assert "can no longer be changed here" in response.content.decode()
    response = client.post(reverse("billing:go_live"), go_live_post())
    assert response.status_code == 200
    assert JournalEntry.objects.filter(source=JournalEntry.Source.OPENING).count() == 1


def test_go_live_in_club_finances_nav(client, treasurer):
    client.force_login(treasurer)
    assert reverse("billing:go_live") in client.get("/").content.decode()


def test_general_journal_groups_accounts_by_type(client, treasurer):
    client.force_login(treasurer)
    content = client.get(reverse("billing:general_journal")).content.decode()
    groups = [
        "Assets (Debit increases)",
        "Liabilities (Credit increases)",
        "Equity (Credit increases)",
        "Income (Credit increases)",
        "Expenses (Debit increases)",
    ]
    positions = [content.index(f'<optgroup label="{label}">') for label in groups]
    assert positions == sorted(positions)
    assets = content[positions[0] : positions[1]]
    assert "110 Checking" in assets
    assert "200 Accounts Payable" in content[positions[1] : positions[2]]
    assert "300 General Fund" in content[positions[2] : positions[3]]
    # Member Receivables is still never offered.
    assert "Member Receivables" not in content


def test_record_member_expense_posts_both_sides(client, treasurer, member):
    client.force_login(treasurer)
    response = client.post(
        reverse("billing:record_member_expense"),
        {
            "date": get_club_today().isoformat(),
            "member": member.pk,
            "expense_account": Account.objects.get(code="500").pk,
            "amount": "700.00",
            "memo": "Field rent paid in cash to landowner",
        },
    )
    entry = JournalEntry.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("billing:journal_detail", args=[entry.pk])
    assert entry.member_entry.ledger.member == member

    content = client.get(response["Location"]).content.decode()
    assert "reverse it from" in content
    assert reverse("billing:ledger_detail", args=[member.pk]) in content


def test_expense_menu_labels(client, treasurer):
    client.force_login(treasurer)
    content = client.get(reverse("billing:club_ledger")).content.decode()
    assert "Expense paid by club" in content
    assert "Expense paid by member" in content
    assert reverse("billing:record_member_expense") in content
