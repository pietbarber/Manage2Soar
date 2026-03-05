"""
Utility functions for sending the post-finalization logsheet summary email.

When a logsheet is finalized by the duty officer, an HTML summary email is sent
to all active members with:
  - Link to the Ops Report
  - Safety / Equipment summaries (if present)
  - Maintenance issues created for the day
  - Operations summary
  - Duty crew list
  - Full flights table, with the longest-duration flight(s) highlighted yellow
  - YouTube iframes and PDF embeds replaced with linked logos / placeholders
"""

import logging
import re
from html import unescape
from urllib.parse import unquote, urlparse

import bleach
from bleach.css_sanitizer import CSSSanitizer
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format as django_date_format

from logsheet.models import FinalizationEmailOutbox
from members.models import Member
from members.utils.membership import get_active_membership_statuses
from siteconfig.models import MailingList, SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url

logger = logging.getLogger(__name__)


class FinalizationEmailDeliveryError(Exception):
    """Raised when delivery fails while processing durable outbox jobs."""


# ---------------------------------------------------------------------------
# HTML sanitisation helpers
# ---------------------------------------------------------------------------

# Matches <iframe> tags that contain a YouTube embed URL.
_YOUTUBE_IFRAME_RE = re.compile(
    r'<iframe[^>]*src=["\']https?://(?:www\.)?youtube(?:-nocookie)?\.com/embed/'
    r'([A-Za-z0-9_\-]+)[^"\']*["\'][^>]*>.*?</iframe>',
    re.IGNORECASE | re.DOTALL,
)

# Matches <iframe> tags that contain a Google Docs PDF viewer URL
# (e.g. https://docs.google.com/viewer?url=…&embedded=true).
_GDOCS_IFRAME_RE = re.compile(
    r'<iframe[^>]*src=["\']https?://docs\.google\.com/viewer\?([^"\']+)["\'][^>]*>.*?</iframe>',
    re.IGNORECASE | re.DOTALL,
)

# Matches <embed> or <object> tags whose src/data attribute points to a PDF,
# allowing optional query strings or fragments after .pdf.
_PDF_EMBED_RE = re.compile(
    r'<(?:embed|object)\b[^>]*(?:src|data)=["\'][^"\']*\.pdf(?:[?#][^"\']*)?["\'][^>]*(?:>.*?</object>|/?>)',
    re.IGNORECASE | re.DOTALL,
)

_ANCHOR_TAG_RE = re.compile(
    r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _youtube_replacement(match):
    """Return an email-safe linked thumbnail for a YouTube embed."""
    video_id = match.group(1)
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    return (
        f'<a href="{video_url}" style="display:inline-block;text-decoration:none;">'
        f'<img src="{thumbnail_url}" alt="Watch on YouTube" width="320" height="180" '
        f'style="display:block;border:0;max-width:100%;height:auto;">'
        f'<div style="margin-top:4px;font-size:13px;color:#cc0000;font-weight:600;">'
        f"&#9654; Watch on YouTube</div>"
        f"</a>"
    )


def _make_pdf_link_from_gdocs_params(params, site_url):
    """Extract a PDF URL from Google Docs viewer query params and return a link."""
    url_match = re.search(r"url=([^&\"']+)", params)
    if url_match:
        raw_pdf_url = unquote(url_match.group(1))
    else:
        raw_pdf_url = f"https://docs.google.com/viewer?{params}"
    parsed = urlparse(raw_pdf_url)
    if parsed.scheme in ("http", "https"):
        pdf_url = raw_pdf_url
    elif not parsed.scheme:
        # Relative URL — make absolute so it resolves in email clients.
        pdf_url = (
            build_absolute_url(raw_pdf_url, canonical=site_url)
            if site_url
            else raw_pdf_url
        )
    else:
        # Reject javascript:, data:, etc.
        pdf_url = "#"
    return (
        f'<a href="{pdf_url}" style="display:inline-block;text-decoration:none;'
        f"padding:12px 16px;background-color:#f44336;color:#ffffff;border-radius:4px;"
        f'font-size:14px;font-weight:600;">&#128196; View PDF Document</a>'
    )


def _make_pdf_link_from_embed(match, site_url):
    """Extract the PDF URL from an embed/object match and return a link."""
    src_match = re.search(
        r'(?:src|data)=["\']([^"\']+)["\']', match.group(0), re.IGNORECASE
    )
    raw_url = src_match.group(1) if src_match else ""
    if raw_url:
        parsed = urlparse(raw_url)
        if parsed.scheme in ("http", "https"):
            pdf_url = raw_url
        elif not parsed.scheme:
            # Relative URL — make absolute so it resolves in email clients.
            pdf_url = (
                build_absolute_url(raw_url, canonical=site_url) if site_url else raw_url
            )
        else:
            # Reject javascript:, data:, etc.
            pdf_url = "#"
    else:
        pdf_url = "#"
    return (
        f'<a href="{pdf_url}" style="display:inline-block;text-decoration:none;'
        f"padding:12px 16px;background-color:#f44336;color:#ffffff;border-radius:4px;"
        f'font-size:14px;font-weight:600;">&#128196; View PDF Document</a>'
    )


# Bleach allowlist for closeout HTML rendered inside emails.
# Permits common formatting and table tags produced by TinyMCE while
# stripping any script, object, or embed elements not already handled by
# the embed-replacement functions above.
_EMAIL_ALLOWED_TAGS = [
    # Text / inline formatting
    "a",
    "abbr",
    "acronym",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "u",
    "ul",
    # Headings
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    # Tables (TinyMCE frequently produces these)
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    # Images (inline / logo)
    "img",
    # Divs / horizontal rules
    "div",
    "hr",
]


def _email_allowed_attribute(tag, name, value):
    """
    Callable bleach attribute filter for email-bound HTML.

    Restricts ``img[src]`` to trusted image CDN hosts so that remote tracking
    pixels embedded in TinyMCE content cannot reach member inboxes.

    Attributes are allowlisted per tag (plus a small global set); any attribute
    not explicitly permitted is rejected.
    """
    # Global attributes permitted on every element
    if name in ("style", "class", "title"):
        return True
    if tag == "a":
        return name in ("href", "target", "rel")
    if tag == "img":
        if name == "src":
            # Only allow images served from trusted CDN hosts (e.g. YouTube
            # thumbnails added by the embed-replacement functions above).
            parsed = urlparse(value)
            return parsed.scheme in ("http", "https") and (parsed.hostname or "") in (
                "img.youtube.com",
                "i.ytimg.com",
            )
        return name in ("alt", "width", "height", "style")
    if tag in ("td", "th"):
        return name in ("colspan", "rowspan", "align", "valign", "style")
    if tag == "table":
        return name in ("border", "cellpadding", "cellspacing", "width", "style")
    return False


_EMAIL_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        # Note: "background" shorthand is intentionally omitted; it can carry
        # external url() references.  Use "background-color" instead.
        "background-color",
        "border",
        "border-collapse",
        "border-color",
        "border-radius",
        "border-spacing",
        "border-style",
        "border-width",
        "color",
        "display",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "height",
        "line-height",
        "margin",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "margin-top",
        "max-width",
        "min-width",
        "padding",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "padding-top",
        "text-align",
        "text-decoration",
        "vertical-align",
        "white-space",
        "width",
    ]
)


def _bleach_clean_email_html(html: str) -> str:
    """Run bleach allowlist sanitization on HTML intended for email delivery."""
    return bleach.clean(
        html,
        tags=_EMAIL_ALLOWED_TAGS,
        attributes=_email_allowed_attribute,
        css_sanitizer=_EMAIL_CSS_SANITIZER,
        strip=True,
    )


def sanitize_closeout_html_for_email(html, site_url=None):
    """
    Strip unrenderable embeds from TinyMCE HTML and replace them with
    email-safe equivalents.

    Replacements performed:
    - YouTube ``<iframe>`` → linked thumbnail image
    - Google Docs PDF viewer ``<iframe>`` → styled "View PDF" link
    - Bare ``<embed>``/``<object>`` for .pdf files → styled "View PDF" link

    Relative PDF URLs (e.g. ``/media/uploads/doc.pdf``) are converted to
    absolute using ``site_url`` so they resolve correctly in email clients.
    In production, pass the canonical site origin (an absolute site URL);
    ``get_finalization_email_context`` already provides this via its
    resolved ``site_url`` argument.

    Args:
        html (str): Raw HTML from a TinyMCE HTMLField.
        site_url (str | None): Canonical site origin used to absolutise
            relative PDF URLs.  When ``None``, relative URLs are left as-is.

    Returns:
        str: HTML safe for rendering inside an email.
    """
    if not html:
        return html
    html = _YOUTUBE_IFRAME_RE.sub(_youtube_replacement, html)
    html = _GDOCS_IFRAME_RE.sub(
        lambda m: _make_pdf_link_from_gdocs_params(m.group(1), site_url), html
    )
    html = _PDF_EMBED_RE.sub(lambda m: _make_pdf_link_from_embed(m, site_url), html)
    # Allowlist-sanitize the remaining HTML.  Unknown tags are stripped
    # (strip=True), img[src] is restricted to trusted CDN hosts only (see
    # _email_allowed_attribute), and the CSS shorthand "background" is
    # excluded to prevent url()-based beacons.
    html = _bleach_clean_email_html(html)
    return html


def html_to_text_preserve_links(html):
    """Convert sanitized HTML to plain text while preserving link targets."""
    if not html:
        return ""

    def _anchor_to_text(match):
        href = unescape(match.group(1)).strip()
        label = unescape(_HTML_TAG_RE.sub("", match.group(2))).strip()
        label = re.sub(r"\s+", " ", label)

        if not href:
            return label
        if not label:
            return href
        if label == href:
            return href
        return f"{label} ({href})"

    text = _ANCHOR_TAG_RE.sub(_anchor_to_text, html)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.IGNORECASE)
    text = _HTML_TAG_RE.sub("", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def get_finalization_email_context(logsheet, config=None, site_url=None):
    """
    Build the full template context for the finalization summary email.

    Args:
        logsheet: Finalized ``Logsheet`` instance.

    Returns:
        dict: Template context.
    """
    if config is None:
        config = SiteConfiguration.objects.first()
    if site_url is None:
        site_url = get_canonical_url(config=config)

    # Absolute URL for the ops report page
    ops_report_path = reverse("logsheet:manage", kwargs={"pk": logsheet.pk})
    ops_report_url = build_absolute_url(ops_report_path, canonical=site_url)

    # All flights for the day, ordered by launch time
    raw_flights = list(
        logsheet.flights.select_related(
            "pilot", "instructor", "glider", "tow_pilot", "towplane"
        ).order_by("launch_time")
    )

    # Determine the maximum duration (for highlighting)
    max_duration = None
    for flight in raw_flights:
        if flight.duration is not None:
            if max_duration is None or flight.duration > max_duration:
                max_duration = flight.duration

    # Build enriched flight rows with pre-formatted values for the template.
    def _fmt_time(t):
        return t.strftime("%H:%M") if t else "—"

    def _fmt_duration(d):
        if d is None:
            return "—"
        total_seconds = int(d.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"{hours}:{minutes:02d}"

    flights = []
    for idx, f in enumerate(raw_flights, start=1):
        pilot_name = (
            f.pilot.full_display_name
            if f.pilot
            else (f.guest_pilot_name or f.legacy_pilot_name or "—")
        )
        instructor_name = (
            f.instructor.full_display_name
            if f.instructor
            else (f.guest_instructor_name or f.legacy_instructor_name or "")
        )
        glider_label = str(f.glider) if f.glider else "—"
        is_longest = (
            max_duration is not None
            and f.duration is not None
            and f.duration == max_duration
        )
        # Row colours are rendered in the template via {% if row.is_longest %}
        # conditional blocks with hardcoded inline style values, so that no
        # Django template expression appears inside a style="" attribute and
        # the VS Code CSS linter does not report false positives.
        flights.append(
            {
                "flight": f,
                "index": idx,
                "pilot_name": pilot_name,
                "instructor_name": instructor_name,
                "glider_label": glider_label,
                "launch_time": _fmt_time(f.launch_time),
                "landing_time": _fmt_time(f.landing_time),
                "duration_str": _fmt_duration(f.duration),
                "release_altitude": (
                    f.release_altitude if f.release_altitude is not None else "—"
                ),
                "flight_type": f.flight_type,
                "is_longest": is_longest,
            }
        )

    # Maintenance issues created for this logsheet
    maintenance_issues = list(
        logsheet.maintenance_issues.select_related(
            "glider", "towplane", "reported_by"
        ).order_by("grounded", "description")
    )

    # Closeout content – sanitised for email rendering
    try:
        closeout = logsheet.closeout
    except ObjectDoesNotExist:
        closeout = None
    safety_issues_html = ""
    equipment_issues_html = ""
    operations_summary_html = ""
    safety_issues_text = ""
    equipment_issues_text = ""
    operations_summary_text = ""
    if closeout:
        safety_issues_html = sanitize_closeout_html_for_email(
            closeout.safety_issues or "", site_url=site_url
        )
        equipment_issues_html = sanitize_closeout_html_for_email(
            closeout.equipment_issues or "", site_url=site_url
        )
        operations_summary_html = sanitize_closeout_html_for_email(
            closeout.operations_summary or "", site_url=site_url
        )
        safety_issues_text = html_to_text_preserve_links(safety_issues_html)
        equipment_issues_text = html_to_text_preserve_links(equipment_issues_html)
        operations_summary_text = html_to_text_preserve_links(operations_summary_html)

    return {
        "logsheet": logsheet,
        "ops_report_url": ops_report_url,
        "flights": flights,
        "maintenance_issues": maintenance_issues,
        "safety_issues_html": safety_issues_html,
        "equipment_issues_html": equipment_issues_html,
        "operations_summary_html": operations_summary_html,
        "safety_issues_text": safety_issues_text,
        "equipment_issues_text": equipment_issues_text,
        "operations_summary_text": operations_summary_text,
        "club_name": config.club_name if config else "Soaring Club",
        "club_nickname": config.club_nickname if config else "",
        "club_logo_url": get_absolute_club_logo_url(config),
        "site_url": site_url,
    }


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------


def _get_from_email(config):
    """Return a suitable noreply@ address for the finalization email."""
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    if "@" in default_from:
        domain = default_from.split("@")[-1]
        return f"noreply@{domain}"
    if config and config.domain_name:
        return f"noreply@{config.domain_name}"
    return "noreply@manage2soar.com"


def _sanitize_email_subject(raw_subject, max_length=255):
    """Remove header-unsafe content from an email subject line."""
    subject_no_crlf = re.sub(r"[\r\n]+", " ", raw_subject)
    subject_printable = "".join(ch for ch in subject_no_crlf if ch.isprintable())
    subject = subject_printable.strip()
    if len(subject) > max_length:
        return subject[:max_length]
    return subject


def _normalize_members_alias_domain(domain_name: str | None) -> str:
    """Return a safe bare hostname for members@ aliasing, or empty string."""
    raw = (domain_name or "").strip().lower()
    if not raw:
        return ""

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return ""

    # Email domains must not include URL-style punctuation or whitespace.
    if any(ch in host for ch in "[]/@"):
        return ""

    # Allow common DNS hostnames and local dev hostnames; reject everything
    # else so we can safely fall back to individual member delivery.
    if re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*",
        host,
    ):
        return host

    return ""


def _get_finalization_recipients(config):
    """Resolve recipients for finalization summary delivery."""
    domain_name = _normalize_members_alias_domain(getattr(config, "domain_name", ""))
    members_list_exists = MailingList.objects.filter(
        is_active=True,
        name__iexact="members",
    ).exists()

    if members_list_exists and domain_name:
        return [f"members@{domain_name}"], "mailing-list"

    # Fallback: deliver directly to active members when no members@ list
    # is configured (or when domain_name is unavailable).
    active_statuses = get_active_membership_statuses()
    recipients = list(
        Member.objects.filter(
            membership_status__in=active_statuses,
            is_active=True,
        )
        .exclude(email="")
        .exclude(email__isnull=True)
        .values_list("email", flat=True)
        .distinct()
    )
    return recipients, "individual"


def send_finalization_summary_email(logsheet, raise_on_failure=False):
    """
    Send the post-finalization HTML summary email.

    Delivery target selection:
    1. If an active ``MailingList`` named ``members`` is configured and the
       site has a domain name, send one email to ``members@<domain>``.
    2. Otherwise, fall back to one-email-per-active-member delivery.

    Called after a logsheet is finalized. By default failures are logged and
    not raised so a mail problem cannot block finalization UX. For durable
    outbox processing, ``raise_on_failure=True`` makes failures explicit so the
    outbox row can remain failed instead of being marked sent.

    Args:
        logsheet: The ``Logsheet`` instance that has just been finalized.
        raise_on_failure: If True, raise when any delivery fails.

    Returns:
        tuple[int, int]: ``(sent_count, failure_count)``
    """
    try:
        config = SiteConfiguration.objects.first()
        site_url = get_canonical_url(config=config)
        from_email = _get_from_email(config)

        recipients, delivery_mode = _get_finalization_recipients(config)

        if not recipients:
            logger.warning(
                "Finalization email for logsheet %s: no active members with email found, skipping.",
                logsheet.pk,
            )
            return (0, 0)

        context = get_finalization_email_context(
            logsheet,
            config=config,
            site_url=site_url,
        )

        # Use Django's date_format so the format is locale-aware and avoids the
        # %-d day specifier which is not supported on all platforms (e.g. Windows).
        raw_subject = (
            f"{context['club_name']} Operations Summary – "
            f"{django_date_format(logsheet.log_date, 'l, N j, Y')}"
        )
        subject = _sanitize_email_subject(raw_subject)

        html_message = render_to_string(
            "logsheet/emails/logsheet_summary_email.html", context
        )
        text_message = render_to_string(
            "logsheet/emails/logsheet_summary_email.txt", context
        )

        sent_count = 0
        failure_count = 0
        # Open a single SMTP connection for all sends.
        # For mailing-list mode there is one send; for fallback mode this
        # retains efficient reuse across many individual sends.
        with get_connection() as connection:
            for recipient in recipients:
                # Individual mode sends one-per-member so addresses are not
                # disclosed to each other via To:. Mailing-list mode has a
                # single recipient alias.
                try:
                    send_mail(
                        subject=subject,
                        message=text_message,
                        from_email=from_email,
                        recipient_list=[recipient],
                        html_message=html_message,
                        connection=connection,
                    )
                    sent_count += 1
                except Exception:
                    failure_count += 1
                    logger.exception(
                        "Failed to send finalization summary email for logsheet %s to %s.",
                        logsheet.pk,
                        recipient,
                    )
        logger.info(
            "Finalization summary email for logsheet %s: mode=%s sent to %d recipient(s), %d failure(s).",
            logsheet.pk,
            delivery_mode,
            sent_count,
            failure_count,
        )
        if raise_on_failure and failure_count > 0:
            raise FinalizationEmailDeliveryError(
                f"Failed to deliver {failure_count} recipient email(s) for logsheet {logsheet.pk}."
            )
        return (sent_count, failure_count)
    except Exception:
        logger.exception(
            "Failed to send finalization summary email for logsheet %s.",
            logsheet.pk,
        )
        if raise_on_failure:
            raise
        return (0, 1)


def _process_finalization_email_outbox_job(outbox_id):
    """Process one durable outbox entry and send its summary email."""
    try:
        with transaction.atomic():
            outbox = (
                FinalizationEmailOutbox.objects.select_for_update()
                .select_related("logsheet")
                .get(pk=outbox_id)
            )
            if outbox.status == FinalizationEmailOutbox.STATUS_SENT:
                return

            outbox.attempt_count += 1
            outbox.save(update_fields=["attempt_count"])

        send_finalization_summary_email(outbox.logsheet, raise_on_failure=True)

        FinalizationEmailOutbox.objects.filter(pk=outbox_id).update(
            status=FinalizationEmailOutbox.STATUS_SENT,
            processed_at=timezone.now(),
            last_error="",
        )
    except Exception as exc:
        logger.exception(
            "Failed processing finalization email outbox job %s.",
            outbox_id,
        )
        FinalizationEmailOutbox.objects.filter(pk=outbox_id).update(
            status=FinalizationEmailOutbox.STATUS_FAILED,
            last_error=str(exc)[:2000],
        )


def enqueue_finalization_summary_email_job(logsheet_id):
    """Persist finalization summary delivery for durable outbox processing."""
    outbox, created = FinalizationEmailOutbox.objects.get_or_create(
        logsheet_id=logsheet_id,
        defaults={"status": FinalizationEmailOutbox.STATUS_PENDING},
    )

    # If an outbox entry already exists (whether previously sent or failed),
    # reset it to pending so that a re-finalization will enqueue a fresh job.
    if not created and outbox.status in (
        FinalizationEmailOutbox.STATUS_SENT,
        FinalizationEmailOutbox.STATUS_FAILED,
    ):
        outbox.status = FinalizationEmailOutbox.STATUS_PENDING
        outbox.last_error = ""
        outbox.processed_at = None
        outbox.save(update_fields=["status", "last_error", "processed_at"])

    return outbox
