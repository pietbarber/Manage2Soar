import csv
from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from billing.decorators import billing_app_required
from billing.forms import (
    GuestRemittanceForm,
    ManualEntryForm,
    OpeningBalanceOverrideForm,
    ReverseEntryForm,
)
from billing.models import BillingPeriod, Ledger, LedgerEntry
from billing.periods import close_period, reopen_period
from billing.services import (
    get_balance,
    get_statement_rows,
    override_opening_balance,
    post_manual_charge,
    post_manual_credit,
    post_manual_payment,
    post_opening_balance,
    remit_guest_payment,
    reverse_manual_entry,
)
from members.models import Member
from utils.csv import sanitize_csv_cell


def treasurer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_superuser or request.user.treasurer):
            return HttpResponseForbidden("Treasurer access is required.")
        return view_func(request, *args, **kwargs)

    return wrapper


@billing_app_required
@treasurer_required
def ledger_list(request):
    query = request.GET.get("q", "").strip()
    members = Member.objects.all().order_by("last_name", "first_name", "username")
    if query:
        members = members.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    rows = []
    ledgers = (
        Ledger.objects.filter(member__in=members)
        .select_related("member")
        .annotate(
            running_balance=Coalesce(
                Sum(
                    Case(
                        When(
                            entries__effect=LedgerEntry.Effect.CREDIT,
                            then=-F("entries__amount"),
                        ),
                        default=F("entries__amount"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )
    ledger_by_member = {ledger.member_id: ledger for ledger in ledgers}
    for member in members:
        ledger = ledger_by_member.get(member.pk)
        rows.append(
            {
                "member": member,
                "balance": ledger.running_balance if ledger else 0,
            }
        )
    return render(request, "billing/ledger_list.html", {"rows": rows, "query": query})


@require_POST
@billing_app_required
@treasurer_required
def close_billing_period(request):
    try:
        year = int(request.POST.get("year", ""))
        month = int(request.POST.get("month", ""))
        date(year, month, 1)
        close_period(
            year=year,
            month=month,
            actor=request.user,
            reason=request.POST.get("reason", ""),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"Closed billing period {year}-{month:02d}.")
    return redirect("billing:period_list")


@require_POST
@billing_app_required
@treasurer_required
def reopen_billing_period(request, period_id):
    period = get_object_or_404(BillingPeriod, pk=period_id)
    try:
        reopen_period(
            period=period, actor=request.user, reason=request.POST.get("reason", "")
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(
            request, f"Reopened billing period {period.year}-{period.month:02d}."
        )
    return redirect("billing:period_list")


@billing_app_required
@treasurer_required
def billing_period_list(request):
    periods = BillingPeriod.objects.prefetch_related("events__actor")
    return render(
        request,
        "billing/period_list.html",
        {"periods": periods, "today": date.today()},
    )


@billing_app_required
@treasurer_required
def ledger_detail(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    ledger = Ledger.objects.filter(member=member).first()
    statement_rows = list(reversed(get_statement_rows(ledger)))
    has_opening_balance = bool(
        ledger and ledger.entries.filter(kind=LedgerEntry.Kind.OPENING_BALANCE).exists()
    )
    form = ManualEntryForm(
        request.POST or None, allow_opening_balance=not has_opening_balance
    )

    if request.method == "POST":
        if not form.is_valid():
            return render(
                request,
                "billing/ledger_detail.html",
                {
                    "member": member,
                    "ledger": ledger,
                    "statement_rows": statement_rows,
                    "form": form,
                    "has_opening_balance": has_opening_balance,
                    "override_form": OpeningBalanceOverrideForm(),
                    "balance": get_balance(ledger) if ledger else 0,
                },
            )
        data = form.cleaned_data
        common = {
            "member": member,
            "actor": request.user,
            "amount": data["amount"],
            "effective_date": data["effective_date"],
            "description": data["description"],
            "reason": data["reason"],
        }
        try:
            if data["kind"] == "manual_charge":
                post_manual_charge(**common)
            elif data["kind"] == "payment":
                post_manual_payment(**common)
            elif data["kind"] == "credit":
                post_manual_credit(**common)
            else:
                post_opening_balance(effect=data["effect"], **common)
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Ledger entry posted.")
            return redirect("billing:ledger_detail", member_id=member.pk)

    return render(
        request,
        "billing/ledger_detail.html",
        {
            "member": member,
            "ledger": ledger,
            "statement_rows": statement_rows,
            "form": form,
            "has_opening_balance": has_opening_balance,
            "override_form": OpeningBalanceOverrideForm(),
            "balance": get_balance(ledger) if ledger else 0,
        },
    )


@require_POST
@billing_app_required
@treasurer_required
def override_opening_balance_view(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    form = OpeningBalanceOverrideForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A complete opening-balance override is required.")
    else:
        try:
            override_opening_balance(
                member=member, actor=request.user, **form.cleaned_data
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Opening balance override posted.")
    return redirect("billing:ledger_detail", member_id=member.pk)


@billing_app_required
@treasurer_required
def ledger_detail_csv(request, member_id):
    """Export one member's ledger, including staff-only audit notes."""
    member = get_object_or_404(Member, pk=member_id)
    ledger = Ledger.objects.filter(member=member).first()

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="ledger_{member.pk}.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Date",
            "Type",
            "Description",
            "Debit",
            "Credit",
            "Balance",
            "Created By",
            "Internal Note",
        ]
    )
    for row in get_statement_rows(ledger):
        entry = row["entry"]
        writer.writerow(
            [
                entry.effective_date.isoformat(),
                sanitize_csv_cell(entry.get_kind_display()),
                sanitize_csv_cell(entry.member_description),
                (
                    f"{entry.amount:.2f}"
                    if entry.effect == LedgerEntry.Effect.DEBIT
                    else ""
                ),
                (
                    f"{entry.amount:.2f}"
                    if entry.effect == LedgerEntry.Effect.CREDIT
                    else ""
                ),
                f"{row['running_balance']:.2f}",
                sanitize_csv_cell(
                    entry.created_by.get_full_name() or entry.created_by.username
                ),
                sanitize_csv_cell(entry.internal_note),
            ]
        )
    return response


@require_POST
@billing_app_required
@treasurer_required
def reverse_entry(request, entry_id):
    entry = get_object_or_404(LedgerEntry, pk=entry_id)
    form = ReverseEntryForm(request.POST)
    if form.is_valid():
        try:
            reverse_manual_entry(
                entry=entry,
                actor=request.user,
                effective_date=entry.effective_date,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Ledger entry reversed.")
    else:
        messages.error(request, "A reversal reason is required.")
    return redirect("billing:ledger_detail", member_id=entry.ledger.member_id)


@require_POST
@billing_app_required
@treasurer_required
def remit_guest_payment_entry(request, entry_id):
    entry = get_object_or_404(
        LedgerEntry,
        pk=entry_id,
        kind=LedgerEntry.Kind.GUEST_PAYMENT_PENDING,
    )
    form = GuestRemittanceForm(request.POST)
    if form.is_valid():
        try:
            remit_guest_payment(
                entry=entry,
                actor=request.user,
                effective_date=date.today(),
                reference=form.cleaned_data["reference"],
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Guest payment remitted in full.")
    else:
        messages.error(request, "A valid remittance confirmation is required.")
    return redirect("billing:ledger_detail", member_id=entry.ledger.member_id)
