"""Double-entry club books: posting, reversal, balances, and integrity checks.

Every write goes through ``post_journal_entry``. It refuses unbalanced
entries, closed billing periods, future dates, and dates before the books'
start date, and it is idempotent on ``source_key``. Posted entries and lines
are immutable; corrections are reversals. ``go_live`` sets the start date and
posts the opening entry for the club's bank balances.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from billing.exceptions import ClubAccountingDisabledError
from billing.models import Account, JournalEntry, JournalLine
from billing.periods import lock_period_for_date
from billing.permissions import require_audit_text, require_manual_transaction_access
from billing.services import _club_today, _money

ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


@dataclass(frozen=True)
class Line:
    account: Account
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    member: object = None
    memo: str = ""


@dataclass(frozen=True)
class BankBalance:
    """One go-live row: an existing bank account (or a new one) and its balance."""

    name: str
    amount: Decimal = ZERO
    account: Account | None = None


# Bank accounts live in the 110-119 block of the chart; the seed provides 110.
BANK_ACCOUNT_CODES = tuple(str(code) for code in range(110, 120))


def _config():
    from siteconfig.models import SiteConfiguration

    return SiteConfiguration.objects.only(
        "billing_app_enabled", "club_accounting_enabled", "club_accounting_start_date"
    ).first()


def club_accounting_enabled():
    config = _config()
    return bool(
        config and config.billing_app_enabled and config.club_accounting_enabled
    )


def _require_club_accounting():
    if not club_accounting_enabled():
        raise ClubAccountingDisabledError("Club accounting is disabled for this site.")


def books_start_date():
    config = _config()
    return config.club_accounting_start_date if config else None


def get_role_account(role):
    try:
        return Account.objects.get(system_role=role)
    except Account.DoesNotExist as exc:
        raise ValidationError(
            f"No account is assigned the {Account.Role(role).label} role."
        ) from exc


def _validate_date(entry_date, *, source, reverses=None):
    if entry_date > _club_today():
        raise ValidationError("Future dates are not allowed.")
    start = books_start_date()
    replacing_opening = (
        source == JournalEntry.Source.REVERSAL
        and reverses is not None
        and reverses.source == JournalEntry.Source.OPENING
    )
    if start and not replacing_opening:
        if source == JournalEntry.Source.OPENING:
            if entry_date != start:
                raise ValidationError(
                    "The opening entry must be dated on the books' start date."
                )
        elif entry_date < start:
            raise ValidationError(
                "Entries must be dated on or after the books' start date "
                f"({start:%Y-%m-%d})."
            )
    if lock_period_for_date(entry_date):
        raise ValidationError(
            f"The {entry_date:%B %Y} billing period is closed. Reopen it to post "
            "entries dated in that month."
        )


def _normalize_lines(lines, *, allow_receivables):
    normalized = []
    for line in lines:
        debit = Decimal(str(line.debit or 0))
        credit = Decimal(str(line.credit or 0))
        if debit < 0 or credit < 0:
            raise ValidationError("Line amounts cannot be negative.")
        if (debit > 0) == (credit > 0):
            raise ValidationError("Each line needs either a debit or a credit amount.")
        debit = _money(debit) if debit else ZERO
        credit = _money(credit) if credit else ZERO
        account = line.account
        if not account.is_active:
            raise ValidationError(f"{account} is inactive.")
        is_receivables = account.system_role == Account.Role.MEMBER_RECEIVABLES
        if is_receivables:
            if not allow_receivables:
                raise ValidationError(
                    "Member Receivables changes only through member ledgers."
                )
            if line.member is None:
                raise ValidationError("Member Receivables lines must name a member.")
        elif line.member is not None:
            raise ValidationError("Only Member Receivables lines may name a member.")
        normalized.append(
            Line(
                account=account,
                debit=debit,
                credit=credit,
                member=line.member,
                memo=(line.memo or "").strip(),
            )
        )
    if len(normalized) < 2:
        raise ValidationError("A journal entry needs at least two lines.")
    total_debit = sum((line.debit for line in normalized), ZERO)
    total_credit = sum((line.credit for line in normalized), ZERO)
    if total_debit != total_credit:
        raise ValidationError(
            f"Debits ({total_debit}) must equal credits ({total_credit})."
        )
    return normalized


def _fingerprint(lines):
    return sorted(
        (
            line.account.pk,
            line.debit,
            line.credit,
            getattr(line.member, "pk", None),
        )
        for line in lines
    )


def _existing_matches(existing, *, entry_date, lines):
    existing_lines = [
        Line(
            account=line.account,
            debit=line.debit,
            credit=line.credit,
            member=line.member,
        )
        for line in existing.lines.select_related("account", "member")
    ]
    return existing.date == entry_date and _fingerprint(existing_lines) == _fingerprint(
        lines
    )


@transaction.atomic
def post_journal_entry(
    *,
    actor,
    date,
    lines,
    memo,
    payee="",
    reference="",
    internal_note="",
    source=JournalEntry.Source.MANUAL,
    source_key=None,
    member_entry=None,
    reverses=None,
    allow_receivables=False,
):
    """Post one balanced, immutable journal entry and return it."""
    _require_club_accounting()
    if source != JournalEntry.Source.MEMBER_POSTING:
        require_manual_transaction_access(actor)
    elif actor is None:
        raise ValidationError("A posting actor is required.")
    memo = require_audit_text(memo, "memo")
    lines = _normalize_lines(lines, allow_receivables=allow_receivables)
    source_key = (source_key or "").strip() or None
    if source_key:
        existing = JournalEntry.objects.filter(source_key=source_key).first()
        if existing:
            if not _existing_matches(existing, entry_date=date, lines=lines):
                raise ValidationError(
                    "Source key already identifies a different journal entry."
                )
            return existing
    _validate_date(date, source=source, reverses=reverses)
    if source == JournalEntry.Source.OPENING and active_opening_entry():
        raise ValidationError("The books already have an opening entry.")

    entry = JournalEntry(
        date=date,
        memo=memo,
        payee=(payee or "").strip(),
        reference=(reference or "").strip(),
        internal_note=(internal_note or "").strip(),
        source=source,
        source_key=source_key,
        member_entry=member_entry,
        reverses=reverses,
        created_by=actor,
    )
    entry._service_created = True
    try:
        with transaction.atomic():
            entry.save()
    except IntegrityError:
        if not source_key:
            raise
        existing = JournalEntry.objects.get(source_key=source_key)
        if not _existing_matches(existing, entry_date=date, lines=lines):
            raise ValidationError(
                "Source key already identifies a different journal entry."
            )
        return existing
    for line in lines:
        record = JournalLine(
            entry=entry,
            account=line.account,
            debit=line.debit,
            credit=line.credit,
            member=line.member,
            memo=line.memo,
        )
        record._service_created = True
        record.save()
    return entry


def post_expense(
    *,
    actor,
    date,
    paid_from,
    expense_account,
    amount,
    memo,
    payee="",
    reference="",
    internal_note="",
):
    if not paid_from.is_cash:
        raise ValidationError("Expenses must be paid from a cash or bank account.")
    if expense_account.type != Account.Type.EXPENSE:
        raise ValidationError("Choose an expense account.")
    amount = _money(amount)
    return post_journal_entry(
        actor=actor,
        date=date,
        memo=memo,
        payee=payee,
        reference=reference,
        internal_note=internal_note,
        lines=[
            Line(account=expense_account, debit=amount),
            Line(account=paid_from, credit=amount),
        ],
    )


def post_income(
    *,
    actor,
    date,
    deposit_to,
    income_account,
    amount,
    memo,
    payee="",
    reference="",
    internal_note="",
):
    if not deposit_to.is_cash:
        raise ValidationError("Income must be deposited to a cash or bank account.")
    if income_account.type != Account.Type.INCOME:
        raise ValidationError("Choose an income account.")
    amount = _money(amount)
    return post_journal_entry(
        actor=actor,
        date=date,
        memo=memo,
        payee=payee,
        reference=reference,
        internal_note=internal_note,
        lines=[
            Line(account=deposit_to, debit=amount),
            Line(account=income_account, credit=amount),
        ],
    )


def post_cash_transfer(
    *,
    actor,
    date,
    from_account,
    to_account,
    amount,
    memo,
    reference="",
    internal_note="",
):
    if not (from_account.is_cash and to_account.is_cash):
        raise ValidationError("Transfers move money between cash or bank accounts.")
    if from_account.pk == to_account.pk:
        raise ValidationError("Choose two different accounts.")
    amount = _money(amount)
    return post_journal_entry(
        actor=actor,
        date=date,
        memo=memo,
        reference=reference,
        internal_note=internal_note,
        lines=[
            Line(account=to_account, debit=amount),
            Line(account=from_account, credit=amount),
        ],
    )


@transaction.atomic
def reverse_journal_entry(*, entry, actor, date, reason):
    """Post the mirror image of a manual journal entry."""
    _require_club_accounting()
    require_manual_transaction_access(actor)
    reason = require_audit_text(reason, "reversal reason")
    original = JournalEntry.objects.select_for_update().get(pk=entry.pk)
    if original.source == JournalEntry.Source.REVERSAL:
        raise ValidationError("A reversal cannot itself be reversed.")
    if (
        original.member_entry_id
        or original.source == JournalEntry.Source.MEMBER_POSTING
    ):
        raise ValidationError("Reverse member postings from the member's ledger.")
    if original.source == JournalEntry.Source.OPENING:
        raise ValidationError(
            "Change opening balances with the go-live wizard instead."
        )
    return _post_reversal(original, actor=actor, date=date, reason=reason)


def _post_reversal(original, *, actor, date, reason):
    if hasattr(original, "reversal"):
        raise ValidationError("This journal entry has already been reversed.")
    if date < original.date:
        raise ValidationError("A reversal cannot be dated before the original entry.")
    lines = [
        Line(
            account=line.account,
            debit=line.credit,
            credit=line.debit,
            member=line.member,
            memo=line.memo,
        )
        for line in original.lines.select_related("account", "member")
    ]
    return post_journal_entry(
        actor=actor,
        date=date,
        lines=lines,
        memo=f"Reversal: {original.memo}"[:255],
        payee=original.payee,
        reference=original.reference,
        internal_note=reason,
        source=JournalEntry.Source.REVERSAL,
        reverses=original,
        source_key=f"journal-reversal:{original.pk}",
        allow_receivables=True,
    )


def bank_accounts():
    """Active bank and cash accounts, other than Undeposited Funds."""
    return Account.objects.filter(is_active=True, is_cash=True).exclude(
        system_role=Account.Role.UNDEPOSITED_FUNDS
    )


def active_opening_entry():
    """Return the opening entry in effect (not reversed), if any."""
    return (
        JournalEntry.objects.filter(
            source=JournalEntry.Source.OPENING, reversal__isnull=True
        )
        .order_by("-created_at", "-id")
        .first()
    )


def go_live_locked():
    """True once the books hold anything besides opening entries.

    Until then the go-live wizard may be rerun; replaced opening entries and
    their reversals don't count.
    """
    return (
        JournalEntry.objects.exclude(source=JournalEntry.Source.OPENING)
        .exclude(
            source=JournalEntry.Source.REVERSAL,
            reverses__source=JournalEntry.Source.OPENING,
        )
        .exists()
    )


def _next_bank_account_code():
    used = set(
        Account.objects.filter(code__in=BANK_ACCOUNT_CODES).values_list(
            "code", flat=True
        )
    )
    for code in BANK_ACCOUNT_CODES:
        if code not in used:
            return code
    raise ValidationError(
        "Bank account codes 110-119 are all in use. Add the account from the "
        "Chart of Accounts instead."
    )


def _go_live_account(row):
    name = (row.name or "").strip()
    if row.account is None:
        if not name:
            raise ValidationError("Each new bank account needs a name.")
        account = Account(
            code=_next_bank_account_code(),
            name=name,
            type=Account.Type.ASSET,
            is_cash=True,
        )
        account.full_clean()
        account.save()
        return account
    account = row.account
    if not account.is_active or not account.is_cash:
        raise ValidationError(f"{account} is not an active bank or cash account.")
    if account.system_role == Account.Role.UNDEPOSITED_FUNDS:
        raise ValidationError("Undeposited Funds starts at zero.")
    if name and name != account.name:
        account.name = name
        account.full_clean()
        account.save(update_fields=["name"])
    return account


@transaction.atomic
def go_live(*, actor, start_date, rows):
    """Start the books: set the start date and post the opening bank balances.

    Each row's balance is debited to its bank account (credited if overdrawn)
    and the total is credited to the General Fund. Until any other entry is
    posted, running this again reverses the current opening entry and posts a
    replacement; after that, opening balances are corrected with a general
    journal entry.
    """
    from siteconfig.models import SiteConfiguration

    _require_club_accounting()
    require_manual_transaction_access(actor)
    config = SiteConfiguration.objects.select_for_update().first()
    if go_live_locked():
        raise ValidationError(
            "The books already have entries after go-live. Correct opening "
            "balances with a general journal entry."
        )
    if start_date > _club_today():
        raise ValidationError("Future dates are not allowed.")
    general_fund = get_role_account(Account.Role.GENERAL_FUND)

    lines = []
    total = ZERO
    for row in rows:
        amount = Decimal(str(row.amount or 0))
        account = _go_live_account(row)
        if not amount:
            continue
        if amount > 0:
            lines.append(Line(account=account, debit=_money(amount)))
            total += _money(amount)
        else:
            lines.append(Line(account=account, credit=_money(-amount)))
            total -= _money(-amount)
    if not lines:
        raise ValidationError("Enter at least one bank balance.")
    if total > 0:
        lines.append(Line(account=general_fund, credit=total))
    elif total < 0:
        lines.append(Line(account=general_fund, debit=-total))

    current = active_opening_entry()
    if current:
        if _existing_matches(current, entry_date=start_date, lines=lines):
            return current
        _post_reversal(
            current,
            actor=actor,
            date=current.date,
            reason="Replaced by the go-live wizard.",
        )
    if config.club_accounting_start_date != start_date:
        config.club_accounting_start_date = start_date
        config.save(update_fields=["club_accounting_start_date"])
    return post_journal_entry(
        actor=actor,
        date=start_date,
        lines=lines,
        memo="Opening bank balances",
        source=JournalEntry.Source.OPENING,
    )


def _line_totals(queryset):
    return queryset.aggregate(
        debit=Coalesce(Sum("debit"), Value(ZERO), output_field=MONEY_FIELD),
        credit=Coalesce(Sum("credit"), Value(ZERO), output_field=MONEY_FIELD),
    )


def natural_balance(account, debit, credit):
    """Express a balance in the account's normal direction."""
    return debit - credit if account.is_debit_normal else credit - debit


def account_balance(account, *, as_of=None, before=None):
    lines = JournalLine.objects.filter(account=account)
    if as_of is not None:
        lines = lines.filter(entry__date__lte=as_of)
    if before is not None:
        lines = lines.filter(entry__date__lt=before)
    totals = _line_totals(lines)
    return natural_balance(account, totals["debit"], totals["credit"])


def account_balances(*, as_of=None):
    """Return every account with its debit, credit, and natural balance."""
    line_filter = Q(lines__entry__date__lte=as_of) if as_of else Q()
    accounts = Account.objects.annotate(
        total_debit=Coalesce(
            Sum("lines__debit", filter=line_filter),
            Value(ZERO),
            output_field=MONEY_FIELD,
        ),
        total_credit=Coalesce(
            Sum("lines__credit", filter=line_filter),
            Value(ZERO),
            output_field=MONEY_FIELD,
        ),
    ).order_by("code")
    rows = []
    for account in accounts:
        rows.append(
            {
                "account": account,
                "debit": account.total_debit,
                "credit": account.total_credit,
                "balance": natural_balance(
                    account, account.total_debit, account.total_credit
                ),
            }
        )
    return rows


def account_register(account, *, start=None, end=None):
    """Return the opening balance and running-balance rows for one account."""
    opening = account_balance(account, before=start) if start else ZERO
    lines = (
        JournalLine.objects.filter(account=account)
        .select_related("entry", "member")
        .order_by("entry__date", "entry__created_at", "entry_id", "id")
    )
    if start:
        lines = lines.filter(entry__date__gte=start)
    if end:
        lines = lines.filter(entry__date__lte=end)
    lines = list(lines)

    other_accounts = defaultdict(list)
    for other in (
        JournalLine.objects.filter(entry_id__in={line.entry_id for line in lines})
        .exclude(account=account)
        .select_related("account")
        .order_by("id")
    ):
        name = other.account.name
        if name not in other_accounts[other.entry_id]:
            other_accounts[other.entry_id].append(name)

    balance = opening
    rows = []
    for line in lines:
        change = natural_balance(account, line.debit, line.credit)
        balance += change
        rows.append(
            {
                "line": line,
                "entry": line.entry,
                "other_accounts": other_accounts[line.entry_id],
                "increase": change if change > 0 else None,
                "decrease": -change if change < 0 else None,
                "balance": balance,
            }
        )
    return {"opening_balance": opening, "rows": rows, "closing_balance": balance}


def verify_books():
    """Return a list of human-readable integrity problems (empty when sound)."""
    problems = []
    unbalanced = (
        JournalEntry.objects.annotate(
            total_debit=Coalesce(
                Sum("lines__debit"), Value(ZERO), output_field=MONEY_FIELD
            ),
            total_credit=Coalesce(
                Sum("lines__credit"), Value(ZERO), output_field=MONEY_FIELD
            ),
            line_count=Count("lines"),
        )
        .filter(Q(line_count__lt=2) | ~Q(total_debit=F("total_credit")))
        .values_list("pk", flat=True)
    )
    for pk in unbalanced:
        problems.append(f"Journal entry #{pk} does not balance.")

    totals = _line_totals(JournalLine.objects.all())
    if totals["debit"] != totals["credit"]:
        problems.append(
            f"Trial balance is off: debits {totals['debit']} vs. credits {totals['credit']}."
        )

    receivables_without_member = JournalLine.objects.filter(
        account__system_role=Account.Role.MEMBER_RECEIVABLES, member__isnull=True
    ).count()
    if receivables_without_member:
        problems.append(
            f"{receivables_without_member} Member Receivables line(s) do not name a member."
        )
    misplaced_members = (
        JournalLine.objects.filter(member__isnull=False)
        .exclude(account__system_role=Account.Role.MEMBER_RECEIVABLES)
        .count()
    )
    if misplaced_members:
        problems.append(
            f"{misplaced_members} line(s) outside Member Receivables name a member."
        )
    return problems
