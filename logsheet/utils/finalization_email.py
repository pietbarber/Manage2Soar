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

from django.template.loader import render_to_string
from django.urls import reverse

from members.models import Member
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url

logger = logging.getLogger(__name__)


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

# Matches <embed> or <object> tags whose src/data attribute ends with .pdf
_PDF_EMBED_RE = re.compile(
    r'<(?:embed|object)\b[^>]*(?:src|data)=["\'][^"\']*\.pdf["\'][^>]*(?:>.*?</object>|/?>)',
    re.IGNORECASE | re.DOTALL,
)


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


def _gdocs_pdf_replacement(match):
    """Return an email-safe link for a Google Docs PDF viewer embed."""
    params = match.group(1)
    # Extract the original document URL from the query string
    url_match = re.search(r"url=([^&\"']+)", params)
    pdf_url = (
        url_match.group(1) if url_match else f"https://docs.google.com/viewer?{params}"
    )
    return (
        f'<a href="{pdf_url}" style="display:inline-block;text-decoration:none;'
        f"padding:12px 16px;background:#f44336;color:#ffffff;border-radius:4px;"
        f'font-size:14px;font-weight:600;">&#128196; View PDF Document</a>'
    )


def _pdf_embed_replacement(match):
    """Return an email-safe link for a bare PDF embed/object."""
    # Try to extract src / data URL from the matched text
    src_match = re.search(
        r'(?:src|data)=["\']([^"\']+)["\']', match.group(0), re.IGNORECASE
    )
    pdf_url = src_match.group(1) if src_match else "#"
    return (
        f'<a href="{pdf_url}" style="display:inline-block;text-decoration:none;'
        f"padding:12px 16px;background:#f44336;color:#ffffff;border-radius:4px;"
        f'font-size:14px;font-weight:600;">&#128196; View PDF Document</a>'
    )


def sanitize_closeout_html_for_email(html):
    """
    Strip unrenderable embeds from TinyMCE HTML and replace them with
    email-safe equivalents.

    Replacements performed:
    - YouTube ``<iframe>`` → linked thumbnail image
    - Google Docs PDF viewer ``<iframe>`` → styled "View PDF" link
    - Bare ``<embed>``/``<object>`` for .pdf files → styled "View PDF" link

    Args:
        html (str): Raw HTML from a TinyMCE HTMLField.

    Returns:
        str: HTML safe for rendering inside an email.
    """
    if not html:
        return html
    html = _YOUTUBE_IFRAME_RE.sub(_youtube_replacement, html)
    html = _GDOCS_IFRAME_RE.sub(_gdocs_pdf_replacement, html)
    html = _PDF_EMBED_RE.sub(_pdf_embed_replacement, html)
    return html


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def get_finalization_email_context(logsheet):
    """
    Build the full template context for the finalization summary email.

    Args:
        logsheet: Finalized ``Logsheet`` instance.

    Returns:
        dict: Template context.
    """
    config = SiteConfiguration.objects.first()
    site_url = get_canonical_url()

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
    for f in raw_flights:
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
        flights.append(
            {
                "flight": f,
                "pilot_name": pilot_name,
                "instructor_name": instructor_name,
                "glider_label": glider_label,
                "launch_time": _fmt_time(f.launch_time),
                "landing_time": _fmt_time(f.landing_time),
                "duration_str": _fmt_duration(f.duration),
                "release_altitude": f.release_altitude if f.release_altitude else "—",
                "flight_type": f.flight_type,
                "is_longest": (
                    max_duration is not None
                    and f.duration is not None
                    and f.duration == max_duration
                ),
            }
        )

    # Maintenance issues created for this logsheet
    maintenance_issues = logsheet.maintenance_issues.select_related(
        "glider", "towplane", "reported_by"
    ).order_by("grounded", "description")

    # Closeout content – sanitised for email rendering
    closeout = getattr(logsheet, "closeout", None)
    safety_issues_html = ""
    equipment_issues_html = ""
    operations_summary_html = ""
    if closeout:
        safety_issues_html = sanitize_closeout_html_for_email(
            closeout.safety_issues or ""
        )
        equipment_issues_html = sanitize_closeout_html_for_email(
            closeout.equipment_issues or ""
        )
        operations_summary_html = sanitize_closeout_html_for_email(
            closeout.operations_summary or ""
        )

    return {
        "logsheet": logsheet,
        "ops_report_url": ops_report_url,
        "flights": flights,
        "maintenance_issues": maintenance_issues,
        "safety_issues_html": safety_issues_html,
        "equipment_issues_html": equipment_issues_html,
        "operations_summary_html": operations_summary_html,
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
    from django.conf import settings

    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    if "@" in default_from:
        domain = default_from.split("@")[-1]
        return f"noreply@{domain}"
    if config and config.domain_name:
        return f"noreply@{config.domain_name}"
    return "noreply@manage2soar.com"


def send_finalization_summary_email(logsheet):
    """
    Send the post-finalization HTML summary email to all active members
    who have an email address on file.

    Called immediately after a logsheet is set to ``finalized=True`` and
    saved.  Failures are logged but never bubble up to the calling view so
    that a mail problem cannot prevent a logsheet from being finalized.

    Args:
        logsheet: The ``Logsheet`` instance that has just been finalized.
    """
    config = SiteConfiguration.objects.first()
    from_email = _get_from_email(config)

    # Fetch all active members with a valid email address
    recipients = list(
        Member.objects.filter(is_active=True)
        .exclude(email="")
        .exclude(email__isnull=True)
        .values_list("email", flat=True)
    )

    if not recipients:
        logger.warning(
            "Finalization email for logsheet %s: no active members with email found, skipping.",
            logsheet.pk,
        )
        return

    context = get_finalization_email_context(logsheet)

    subject = (
        f"{context['club_name']} Operations Summary – "
        f"{logsheet.log_date.strftime('%A, %B %-d, %Y')}"
    )

    html_message = render_to_string(
        "logsheet/emails/logsheet_summary_email.html", context
    )
    text_message = render_to_string(
        "logsheet/emails/logsheet_summary_email.txt", context
    )

    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
        )
        logger.info(
            "Sent finalization summary email for logsheet %s to %d recipient(s).",
            logsheet.pk,
            len(recipients),
        )
    except Exception:
        logger.exception(
            "Failed to send finalization summary email for logsheet %s.",
            logsheet.pk,
        )
