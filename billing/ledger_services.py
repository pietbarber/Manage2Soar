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
from billing.models import Account, JournalEntry, JournalLine, LedgerEntry
from billing.periods import lock_period_for_date
from billing.permissions import require_audit_text, require_manual_transaction_access
from billing.services import _club_today, _money, member_label

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
    """One Finances Setup row: an existing bank account (or a new one) and its balance."""

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


BOOKS_NOT_STARTED = "Finish Finances Setup before recording entries in the club books."


def _require_club_accounting():
    if not club_accounting_enabled():
        raise ClubAccountingDisabledError("Club accounting is disabled for this site.")


def books_start_date():
    config = _config()
    if config and config.club_accounting_start_date:
        return config.club_accounting_start_date
    # The setup wizard saves the date with the opening entry, so fall back to
    # that entry's date if the setting has been cleared.
    opening = active_opening_entry()
    return opening.date if opening else None


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
    # Member postings, and reversals that mirror a member ledger reversal, are
    # authorized by the member ledger service that created them.
    if source != JournalEntry.Source.MEMBER_POSTING and member_entry is None:
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
    # Anything posted before the opening entry would lock Finances Setup out.
    if source != JournalEntry.Source.OPENING and not active_opening_entry():
        raise ValidationError(BOOKS_NOT_STARTED)
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


@transaction.atomic
def post_member_paid_expense(
    *,
    actor,
    date,
    member,
    expense_account,
    amount,
    memo,
    reference="",
    internal_note="",
):
    """Record a club expense a member paid out of pocket.

    The member's ledger is credited (the club owes them, or they owe less) and
    the books debit the expense against Member Receivables for that member.
    Both post together; reverse it from the member's ledger.
    """
    from billing.services import post_manual_credit

    _require_club_accounting()
    require_manual_transaction_access(actor)
    if not member_books_live():
        raise ValidationError("Finish Finances Setup before recording member expenses.")
    if expense_account.type != Account.Type.EXPENSE:
        raise ValidationError("Choose an expense account.")
    memo = require_audit_text(memo, "memo")
    member_entry = post_manual_credit(
        member=member,
        actor=actor,
        amount=amount,
        effective_date=date,
        description=memo,
        reason=(internal_note or "").strip()
        or f"Paid a club expense ({expense_account.name}).",
        book_account=expense_account,
        book_reference=reference,
    )
    return JournalEntry.objects.get(member_entry=member_entry)


def member_books_live():
    """True once member-ledger entries post to the books.

    That starts when Finances Setup posts the opening entry; before then, member
    balances are gathered into the opening entry instead.
    """
    return club_accounting_enabled() and active_opening_entry() is not None


# Where each kind of member entry lands when the treasurer doesn't choose.
# Flight charges split across tow, rental and instruction revenue instead.
DEFAULT_OFFSET_ROLES = {
    LedgerEntry.Kind.MISC_CHARGE: Account.Role.DEFAULT_CHARGE_REVENUE,
    LedgerEntry.Kind.MANUAL_CHARGE: Account.Role.DEFAULT_CHARGE_REVENUE,
    LedgerEntry.Kind.GUEST_PAYMENT_PENDING: Account.Role.GUEST_FLIGHT_REVENUE,
    LedgerEntry.Kind.PAYMENT: Account.Role.UNDEPOSITED_FUNDS,
    LedgerEntry.Kind.GUEST_REMITTANCE: Account.Role.UNDEPOSITED_FUNDS,
    LedgerEntry.Kind.CREDIT: Account.Role.MEMBER_CREDITS,
    LedgerEntry.Kind.OPENING_BALANCE: Account.Role.GENERAL_FUND,
}
FLIGHT_REVENUE_ROLES = (
    ("tow_amount", Account.Role.TOW_REVENUE),
    ("rental_amount", Account.Role.RENTAL_REVENUE),
    ("instruction_amount", Account.Role.INSTRUCTION_REVENUE),
)
CASH_KINDS = {LedgerEntry.Kind.PAYMENT, LedgerEntry.Kind.GUEST_REMITTANCE}


def _is_opening_adjustment(entry):
    from billing.services import OPENING_OVERRIDE_KEY_PREFIX

    return entry.kind == LedgerEntry.Kind.OPENING_BALANCE or (
        entry.source_key or ""
    ).startswith(OPENING_OVERRIDE_KEY_PREFIX)


def check_member_offset_account(kind, account):
    """Refuse an account that doesn't fit this kind of member entry."""
    if account.system_role == Account.Role.MEMBER_RECEIVABLES:
        raise ValidationError("Member Receivables can't be the other side.")
    if not account.is_active:
        raise ValidationError(f"{account} is inactive.")
    if kind in CASH_KINDS:
        if not account.is_cash:
            raise ValidationError("Payments must go to a cash or bank account.")
    elif kind == LedgerEntry.Kind.CREDIT:
        if account.type not in {Account.Type.EXPENSE, Account.Type.INCOME}:
            raise ValidationError("Credits come from an expense or income account.")
    elif kind in {LedgerEntry.Kind.MANUAL_CHARGE, LedgerEntry.Kind.MISC_CHARGE}:
        if account.type != Account.Type.INCOME:
            raise ValidationError("Charges go to an income account.")
    else:
        raise ValidationError("This kind of entry always uses its default account.")


def member_entry_lines(entry, account=None):
    """The journal lines for one member-ledger entry (not a reversal)."""
    receivables = get_role_account(Account.Role.MEMBER_RECEIVABLES)
    member = entry.ledger.member
    amount = entry.amount
    if account is None and _is_opening_adjustment(entry):
        account = get_role_account(Account.Role.GENERAL_FUND)
    if entry.effect == LedgerEntry.Effect.DEBIT:
        if account is not None:
            others = [Line(account=account, credit=amount)]
        elif entry.kind == LedgerEntry.Kind.FLIGHT_CHARGE:
            snapshot = entry.flight_snapshot
            others = [
                Line(account=get_role_account(role), credit=getattr(snapshot, field))
                for field, role in FLIGHT_REVENUE_ROLES
                if getattr(snapshot, field)
            ]
        else:
            role = DEFAULT_OFFSET_ROLES[entry.kind]
            others = [Line(account=get_role_account(role), credit=amount)]
        return [Line(account=receivables, debit=amount, member=member), *others]
    if account is None:
        account = get_role_account(DEFAULT_OFFSET_ROLES[entry.kind])
    return [
        Line(account=account, debit=amount),
        Line(account=receivables, credit=amount, member=member),
    ]


def post_member_entry(entry, *, actor, account=None, reference=""):
    """Post the club-books side of a member-ledger entry.

    Does nothing until Finances Setup. An entry dated before the books' start date
    (a late logsheet, say) posts on the start date. Reversals mirror the
    original's journal entry; if the original was folded into the opening
    entry, they mirror its default accounts instead.
    """
    if not member_books_live():
        return None
    existing = JournalEntry.objects.filter(member_entry=entry).first()
    if existing:
        return existing
    start = books_start_date()
    date = max(entry.effective_date, start)
    note = entry.internal_note
    if date != entry.effective_date:
        note = (
            f"{note}\nMember ledger date {entry.effective_date:%Y-%m-%d}; "
            "posted on the books' start date."
        ).strip()
    if entry.kind == LedgerEntry.Kind.REVERSAL:
        original = JournalEntry.objects.filter(member_entry=entry.reverses).first()
        if original:
            return _post_reversal(
                JournalEntry.objects.select_for_update().get(pk=original.pk),
                actor=actor,
                date=max(date, original.date),
                reason=note or "Reversed on the member's ledger.",
                member_entry=entry,
            )
        lines = [
            Line(
                account=line.account,
                debit=line.credit,
                credit=line.debit,
                member=line.member,
            )
            for line in member_entry_lines(entry.reverses)
        ]
    else:
        if account is not None:
            check_member_offset_account(entry.kind, account)
        lines = member_entry_lines(entry, account)
    return post_journal_entry(
        actor=actor,
        date=date,
        lines=lines,
        memo=entry.member_description[:255],
        payee=member_label(entry.ledger.member),
        reference=reference,
        internal_note=note,
        source=JournalEntry.Source.MEMBER_POSTING,
        source_key=f"member-entry:{entry.pk}",
        member_entry=entry,
        allow_receivables=True,
    )


def member_entries_missing_from_books():
    """Member entries the books don't account for yet, oldest first.

    Entries dated before the start date that existed at setup live in the
    opening entry; everything else should have its own journal entry.
    """
    opening = active_opening_entry()
    if opening is None:
        return LedgerEntry.objects.none()
    return (
        LedgerEntry.objects.filter(journal_entry__isnull=True)
        .exclude(effective_date__lt=opening.date, created_at__lt=opening.created_at)
        .select_related("ledger__member", "reverses")
        .order_by("id")
    )


def post_missing_member_entries(*, actor):
    """Post every member entry the books are missing; return how many."""
    posted = 0
    for entry in member_entries_missing_from_books():
        post_member_entry(entry, actor=actor)
        posted += 1
    return posted


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
            "Change opening balances with the Finances Setup wizard instead."
        )
    return _post_reversal(original, actor=actor, date=date, reason=reason)


def _post_reversal(original, *, actor, date, reason, member_entry=None):
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
        member_entry=member_entry,
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


def _member_postings():
    """Journal entries posted from member ledgers, including their reversals."""
    return JournalEntry.objects.filter(
        Q(source=JournalEntry.Source.MEMBER_POSTING) | Q(member_entry__isnull=False)
    )


def go_live_locked():
    """True once the books hold entries the treasurer posted after setup.

    Until then the Finances Setup wizard may be rerun. Replaced opening entries,
    their reversals, and postings from member ledgers don't count.
    """
    return (
        JournalEntry.objects.exclude(source=JournalEntry.Source.OPENING)
        .exclude(
            source=JournalEntry.Source.REVERSAL,
            reverses__source=JournalEntry.Source.OPENING,
        )
        .exclude(pk__in=_member_postings().values("pk"))
        .exists()
    )


def _opening_receivables_lines(start_date):
    """One Member Receivables line per member, for entries dated before setup."""
    balances = defaultdict(lambda: ZERO)
    members = {}
    entries = LedgerEntry.objects.filter(
        effective_date__lt=start_date, journal_entry__isnull=True
    ).select_related("ledger__member")
    for entry in entries:
        member = entry.ledger.member
        members[member.pk] = member
        balances[member.pk] += entry.signed_amount
    receivables = get_role_account(Account.Role.MEMBER_RECEIVABLES)
    lines = []
    for member_pk, balance in sorted(balances.items()):
        if balance > 0:
            lines.append(
                Line(account=receivables, debit=balance, member=members[member_pk])
            )
        elif balance < 0:
            lines.append(
                Line(account=receivables, credit=-balance, member=members[member_pk])
            )
    return lines


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

    Each row's balance is debited to its bank account (credited if overdrawn),
    each member's ledger balance from before the start date goes to Member
    Receivables, and the difference is credited to the General Fund. Member
    entries dated on or after the start date then post one by one.

    Until the treasurer posts any other entry, running this again reverses the
    current opening entry and posts a replacement; after that, opening
    balances are corrected with a general journal entry.
    """
    from siteconfig.models import SiteConfiguration

    _require_club_accounting()
    require_manual_transaction_access(actor)
    config = SiteConfiguration.objects.select_for_update().first()
    if go_live_locked():
        raise ValidationError(
            "The books already have entries posted after setup. Correct opening "
            "balances with a general journal entry."
        )
    if start_date > _club_today():
        raise ValidationError("Future dates are not allowed.")
    current_start = books_start_date()
    if current_start and current_start != start_date and _member_postings().exists():
        raise ValidationError(
            "Member ledger activity is already in the books from "
            f"{current_start:%Y-%m-%d}. Keep that start date."
        )
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
    for line in _opening_receivables_lines(start_date):
        lines.append(line)
        total += line.debit - line.credit
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
            reason="Replaced by the Finances Setup wizard.",
        )
    if config.club_accounting_start_date != start_date:
        config.club_accounting_start_date = start_date
        config.save(update_fields=["club_accounting_start_date"])
    opening = post_journal_entry(
        actor=actor,
        date=start_date,
        lines=lines,
        memo="Opening balances",
        source=JournalEntry.Source.OPENING,
        allow_receivables=True,
    )
    post_missing_member_entries(actor=actor)
    return opening


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
    problems.extend(_receivables_tie_out())
    return problems


def _receivables_tie_out():
    """Compare each member's Member Receivables balance with their ledger."""
    if not member_books_live():
        return []
    books = defaultdict(lambda: ZERO)
    for member_pk, debit, credit in JournalLine.objects.filter(
        account__system_role=Account.Role.MEMBER_RECEIVABLES
    ).values_list("member", "debit", "credit"):
        books[member_pk] += debit - credit
    ledgers = defaultdict(lambda: ZERO)
    for entry in LedgerEntry.objects.select_related("ledger"):
        ledgers[entry.ledger.member_id] += entry.signed_amount
    from members.models import Member

    mismatched = [pk for pk in set(books) | set(ledgers) if books[pk] != ledgers[pk]]
    problems = [
        f"Member Receivables for {member_label(member)} is {books[member.pk]}, "
        f"but their member ledger balance is {ledgers[member.pk]}."
        for member in Member.objects.filter(pk__in=mismatched).order_by("pk")
    ]
    missing = member_entries_missing_from_books().count()
    if missing:
        problems.append(
            f"{missing} member ledger entr{'y is' if missing == 1 else 'ies are'} "
            "missing from the books. Run `manage.py sync_member_books --post`."
        )
    return problems
