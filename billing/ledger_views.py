"""Treasurer views for the double-entry club books (Club Finances menu)."""

import csv
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from billing.decorators import (
    billing_app_required,
    club_accounting_required,
    treasurer_required,
)
from billing.ledger_forms import (
    AccountForm,
    ClubLedgerFilterForm,
    ExpenseForm,
    IncomeForm,
    JournalHeaderForm,
    JournalLineFormSet,
    ReverseJournalForm,
    TransferForm,
)
from billing.ledger_services import (
    Line,
    account_balances,
    account_register,
    books_start_date,
    post_cash_transfer,
    post_expense,
    post_income,
    post_journal_entry,
    reverse_journal_entry,
    verify_books,
)
from billing.models import Account, JournalEntry, JournalLine
from siteconfig.timezone_utils import get_club_today
from utils.csv import sanitize_csv_cell

ENTRIES_PER_PAGE = 50


def club_books_view(view_func):
    """Apply the billing, treasurer, and club-accounting gates in order."""
    return billing_app_required(treasurer_required(club_accounting_required(view_func)))


def _year_start():
    return date(get_club_today().year, 1, 1)


def _filtered_entries(request):
    form = ClubLedgerFilterForm(request.GET or None)
    entries = JournalEntry.objects.all()
    filters = {}
    if form.is_valid():
        filters = form.cleaned_data
        if filters.get("start"):
            entries = entries.filter(date__gte=filters["start"])
        if filters.get("end"):
            entries = entries.filter(date__lte=filters["end"])
        if filters.get("account"):
            entries = entries.filter(lines__account=filters["account"])
        if filters.get("source"):
            entries = entries.filter(source=filters["source"])
        if filters.get("q"):
            query = filters["q"]
            entries = entries.filter(
                Q(memo__icontains=query)
                | Q(payee__icontains=query)
                | Q(reference__icontains=query)
            )
    entries = entries.distinct().select_related("created_by", "reverses")
    entries = entries.prefetch_related(
        Prefetch(
            "lines",
            queryset=JournalLine.objects.select_related("account", "member").order_by(
                "-debit", "id"
            ),
        )
    )
    return form, entries


@club_books_view
def club_ledger(request):
    form, entries = _filtered_entries(request)
    page = Paginator(
        entries.order_by("-date", "-created_at", "-id"), ENTRIES_PER_PAGE
    ).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "billing/books/club_ledger.html",
        {
            "form": form,
            "page": page,
            "querystring": query.urlencode(),
            "cash_rows": [row for row in account_balances() if row["account"].is_cash],
            "problems": verify_books(),
        },
    )


@club_books_view
def club_ledger_csv(request):
    _, entries = _filtered_entries(request)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="club_ledger.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Date",
            "Entry",
            "Source",
            "Description",
            "Payee",
            "Reference",
            "Account Code",
            "Account",
            "Member",
            "Debit",
            "Credit",
            "Line Memo",
            "Created By",
            "Internal Note",
        ]
    )
    for entry in entries.order_by("date", "created_at", "id"):
        for line in entry.lines.all():
            member = line.member
            writer.writerow(
                [
                    entry.date.isoformat(),
                    entry.pk,
                    entry.get_source_display(),
                    sanitize_csv_cell(entry.memo),
                    sanitize_csv_cell(entry.payee),
                    sanitize_csv_cell(entry.reference),
                    sanitize_csv_cell(line.account.code),
                    sanitize_csv_cell(line.account.name),
                    sanitize_csv_cell(
                        (member.get_full_name() or member.username) if member else ""
                    ),
                    f"{line.debit:.2f}" if line.debit else "",
                    f"{line.credit:.2f}" if line.credit else "",
                    sanitize_csv_cell(line.memo),
                    sanitize_csv_cell(
                        entry.created_by.get_full_name() or entry.created_by.username
                    ),
                    sanitize_csv_cell(entry.internal_note),
                ]
            )
    return response


def _register_range(request):
    if not request.GET:
        start = _year_start()
        return ClubLedgerFilterForm(initial={"start": start}), start, None
    form = ClubLedgerFilterForm(request.GET)
    if not form.is_valid():
        return form, None, None
    return form, form.cleaned_data.get("start"), form.cleaned_data.get("end")


@club_books_view
def account_register_view(request, account_id):
    account = get_object_or_404(Account, pk=account_id)
    form, start, end = _register_range(request)
    register = account_register(account, start=start, end=end)
    return render(
        request,
        "billing/books/account_register.html",
        {
            "account": account,
            "form": form,
            "start": start,
            "end": end,
            "register": register,
            "rows": list(reversed(register["rows"])),
        },
    )


@club_books_view
def account_register_csv(request, account_id):
    account = get_object_or_404(Account, pk=account_id)
    _, start, end = _register_range(request)
    register = account_register(account, start=start, end=end)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="account_{account.code}_register.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        [
            "Date",
            "Entry",
            "Description",
            "Payee",
            "Other Accounts",
            "Increase",
            "Decrease",
            "Balance",
        ]
    )
    writer.writerow(
        [
            start.isoformat() if start else "",
            "",
            "Opening balance",
            "",
            "",
            "",
            "",
            f"{register['opening_balance']:.2f}",
        ]
    )
    for row in register["rows"]:
        entry = row["entry"]
        writer.writerow(
            [
                entry.date.isoformat(),
                entry.pk,
                sanitize_csv_cell(entry.memo),
                sanitize_csv_cell(entry.payee),
                sanitize_csv_cell("; ".join(row["other_accounts"])),
                f"{row['increase']:.2f}" if row["increase"] else "",
                f"{row['decrease']:.2f}" if row["decrease"] else "",
                f"{row['balance']:.2f}",
            ]
        )
    return response


@club_books_view
def chart_of_accounts(request):
    rows = account_balances()
    groups = []
    for account_type, label in Account.Type.choices:
        type_rows = [row for row in rows if row["account"].type == account_type]
        groups.append(
            {
                "label": label,
                "rows": type_rows,
                "total": sum((row["balance"] for row in type_rows), 0),
            }
        )
    return render(
        request,
        "billing/books/chart_of_accounts.html",
        {
            "groups": groups,
            "problems": verify_books(),
            "start_date": books_start_date(),
        },
    )


@club_books_view
def account_edit(request, account_id=None):
    account = get_object_or_404(Account, pk=account_id) if account_id else None
    form = AccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        try:
            saved = form.save()
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, f"Saved account {saved}.")
            return redirect("billing:chart_of_accounts")
    return render(
        request,
        "billing/books/account_form.html",
        {"form": form, "account": account},
    )


ENTRY_FORMS = {
    "expense": {
        "form": ExpenseForm,
        "title": "Record expense",
        "help": "Money the club paid out, such as field rent or a maintenance invoice.",
        "post": lambda actor, data: post_expense(actor=actor, **data),
    },
    "income": {
        "form": IncomeForm,
        "title": "Record income",
        "help": "Money the club received that is not a member payment, such as a donation.",
        "post": lambda actor, data: post_income(actor=actor, **data),
    },
    "transfer": {
        "form": TransferForm,
        "title": "Transfer between accounts",
        "help": "Move money between bank or cash accounts, such as depositing collected checks.",
        "post": lambda actor, data: post_cash_transfer(actor=actor, **data),
    },
}


def _record_entry(request, kind):
    config = ENTRY_FORMS[kind]
    form = config["form"](request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            entry = config["post"](request.user, form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, f"Posted journal entry #{entry.pk}.")
            return redirect("billing:journal_detail", entry_id=entry.pk)
    return render(
        request,
        "billing/books/entry_form.html",
        {
            "form": form,
            "title": config["title"],
            "help": config["help"],
            "has_cash_accounts": Account.objects.filter(
                is_cash=True, is_active=True
            ).exists(),
        },
    )


@club_books_view
def record_expense(request):
    return _record_entry(request, "expense")


@club_books_view
def record_income(request):
    return _record_entry(request, "income")


@club_books_view
def cash_transfer(request):
    return _record_entry(request, "transfer")


@club_books_view
def general_journal(request):
    header = JournalHeaderForm(request.POST or None)
    formset = JournalLineFormSet(request.POST or None, prefix="lines")
    if request.method == "POST" and header.is_valid() and formset.is_valid():
        data = header.cleaned_data
        lines = [
            Line(
                account=line["account"],
                debit=line.get("debit") or 0,
                credit=line.get("credit") or 0,
                memo=line.get("memo", ""),
            )
            for line in formset.filled_lines()
        ]
        try:
            entry = post_journal_entry(actor=request.user, lines=lines, **data)
        except ValidationError as exc:
            header.add_error(None, exc.messages)
        else:
            messages.success(request, f"Posted journal entry #{entry.pk}.")
            return redirect("billing:journal_detail", entry_id=entry.pk)
    return render(
        request,
        "billing/books/general_journal.html",
        {"form": header, "formset": formset},
    )


@club_books_view
def journal_detail(request, entry_id):
    entry = get_object_or_404(
        JournalEntry.objects.select_related(
            "created_by", "reverses", "member_entry__ledger__member"
        ),
        pk=entry_id,
    )
    lines = entry.lines.select_related("account", "member").order_by("-debit", "id")
    reversal = getattr(entry, "reversal", None)
    can_reverse = (
        reversal is None
        and entry.source == JournalEntry.Source.MANUAL
        and entry.member_entry_id is None
    )
    return render(
        request,
        "billing/books/journal_detail.html",
        {
            "heading": f"Journal entry #{entry.pk}",
            "entry": entry,
            "lines": lines,
            "reversal": reversal,
            "can_reverse": can_reverse,
            "reverse_form": ReverseJournalForm(),
        },
    )


@require_POST
@club_books_view
def journal_reverse(request, entry_id):
    entry = get_object_or_404(JournalEntry, pk=entry_id)
    form = ReverseJournalForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A reversal date and reason are required.")
        return redirect("billing:journal_detail", entry_id=entry.pk)
    try:
        reversal = reverse_journal_entry(
            entry=entry,
            actor=request.user,
            date=form.cleaned_data["date"],
            reason=form.cleaned_data["reason"],
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("billing:journal_detail", entry_id=entry.pk)
    messages.success(request, f"Posted reversal #{reversal.pk}.")
    return redirect("billing:journal_detail", entry_id=reversal.pk)
