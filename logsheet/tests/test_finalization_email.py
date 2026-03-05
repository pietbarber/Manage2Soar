"""
Tests for logsheet.utils.finalization_email
"""

from datetime import date, time, timedelta
from unittest.mock import patch

import pytest
from django.test import SimpleTestCase

from logsheet.models import (
    Airfield,
    Glider,
    Logsheet,
    LogsheetCloseout,
    MaintenanceIssue,
)
from logsheet.utils.finalization_email import (
    get_finalization_email_context,
    html_to_text_preserve_links,
    sanitize_closeout_html_for_email,
    send_finalization_summary_email,
)
from members.models import Member
from siteconfig.models import MembershipStatus
from utils.url_helpers import get_canonical_url

# ---------------------------------------------------------------------------
# sanitize_closeout_html_for_email
# ---------------------------------------------------------------------------


class TestSanitizeCloseoutHtml(SimpleTestCase):
    def test_empty_string_returns_empty(self):
        assert sanitize_closeout_html_for_email("") == ""

    def test_none_returns_none(self):
        assert sanitize_closeout_html_for_email(None) is None

    def test_plain_html_unchanged(self):
        html = "<p>All good today. No issues.</p>"
        assert sanitize_closeout_html_for_email(html) == html

    def test_youtube_iframe_replaced_with_thumbnail_link(self):
        html = (
            "<p>Watch the video:</p>"
            '<iframe width="560" height="315" '
            'src="https://www.youtube.com/embed/dQw4w9WgXcQ" '
            'frameborder="0"></iframe>'
        )
        result = sanitize_closeout_html_for_email(html)
        assert "<iframe" not in result
        assert "dQw4w9WgXcQ" in result
        assert "youtube.com/watch" in result
        assert "img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg" in result
        assert "Watch on YouTube" in result

    def test_youtube_nocookie_iframe_replaced(self):
        html = (
            '<iframe src="https://www.youtube-nocookie.com/embed/abc123">' "</iframe>"
        )
        result = sanitize_closeout_html_for_email(html)
        assert "<iframe" not in result
        assert "abc123" in result

    def test_google_docs_pdf_viewer_replaced(self):
        pdf_url = "https://example.com/document.pdf"
        html = (
            f'<iframe src="https://docs.google.com/viewer?url={pdf_url}&embedded=true">'
            "</iframe>"
        )
        result = sanitize_closeout_html_for_email(html)
        assert "<iframe" not in result
        assert pdf_url in result
        assert "View PDF" in result

    def test_bare_pdf_embed_replaced(self):
        html = '<embed src="/media/uploads/manual.pdf" type="application/pdf">'
        result = sanitize_closeout_html_for_email(html)
        assert "<embed" not in result
        assert "/media/uploads/manual.pdf" in result
        assert "View PDF" in result

    def test_pdf_embed_with_query_string_is_replaced(self):
        html = (
            '<embed src="/media/uploads/manual.pdf?version=1" type="application/pdf">'
        )
        result = sanitize_closeout_html_for_email(html)
        assert "<embed" not in result
        assert "/media/uploads/manual.pdf?version=1" in result
        assert "View PDF" in result

    def test_pdf_embed_with_fragment_is_replaced(self):
        html = '<object data="/media/uploads/manual.pdf#page=2"></object>'
        result = sanitize_closeout_html_for_email(html)
        assert "<object" not in result
        assert "/media/uploads/manual.pdf#page=2" in result
        assert "View PDF" in result

    def test_mixed_youtube_and_pdf_in_same_content(self):
        html = (
            "<p>Video below</p>"
            '<iframe src="https://www.youtube.com/embed/testVideoId"></iframe>'
            "<p>And a doc</p>"
            '<embed src="/media/report.pdf">'
        )
        result = sanitize_closeout_html_for_email(html)
        assert "<iframe" not in result
        assert "<embed" not in result
        assert "testVideoId" in result
        assert "/media/report.pdf" in result

    def test_untrusted_img_source_is_removed(self):
        html = '<p>Test<img src="https://evil.example.com/tracker.png" alt="x"></p>'
        result = sanitize_closeout_html_for_email(html)
        assert "evil.example.com" not in result
        assert "tracker.png" not in result

    def test_background_url_is_stripped_from_inline_style(self):
        html = (
            '<p style="background:url(https://evil.example.com/bg.png);'
            'color:#111;">Safe text</p>'
        )
        result = sanitize_closeout_html_for_email(html)
        assert "background:url" not in result
        assert "evil.example.com/bg.png" not in result
        assert "Safe text" in result


class TestHtmlToTextPreserveLinks(SimpleTestCase):
    def test_converts_links_to_label_and_url(self):
        html = '<p>See <a href="https://example.com/doc.pdf">View PDF Document</a></p>'
        result = html_to_text_preserve_links(html)
        assert "View PDF Document (https://example.com/doc.pdf)" in result


class TestEmailSiteUrlResolution(SimpleTestCase):
    def test_resolves_domain_name_to_https_origin(self):
        class DummyConfig:
            domain_name = "tenant-demo.skylinesoaring.org"
            canonical_url = ""

        resolved = get_canonical_url(config=DummyConfig())
        assert resolved == "https://tenant-demo.skylinesoaring.org"


# ---------------------------------------------------------------------------
# get_finalization_email_context
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetFinalizationEmailContext:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.airfield = Airfield.objects.create(identifier="KFOO", name="Foo Field")
        self.member = Member.objects.create_user(
            username="do_user",
            password="test",
            first_name="Duty",
            last_name="Officer",
            membership_status="Full Member",
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date(2025, 7, 4),
            airfield=self.airfield,
            created_by=self.member,
            duty_officer=self.member,
        )
        self.glider = Glider.objects.create(
            n_number="N111AA", club_owned=True, is_active=True
        )
        # Minimal closeout
        LogsheetCloseout.objects.create(
            logsheet=self.logsheet,
            safety_issues="<p>All clear.</p>",
            equipment_issues="",
            operations_summary="<p>Good day.</p>",
        )

    def test_context_has_required_keys(self):
        ctx = get_finalization_email_context(self.logsheet)
        expected = [
            "logsheet",
            "ops_report_url",
            "flights",
            "maintenance_issues",
            "safety_issues_html",
            "equipment_issues_html",
            "operations_summary_html",
            "safety_issues_text",
            "equipment_issues_text",
            "operations_summary_text",
            "club_name",
            "club_nickname",
            "club_logo_url",
            "site_url",
        ]
        for key in expected:
            assert key in ctx, f"Missing context key: {key}"

    def test_ops_report_url_contains_logsheet_pk(self):
        ctx = get_finalization_email_context(self.logsheet)
        assert str(self.logsheet.pk) in ctx["ops_report_url"]

    def test_closeout_html_passed_through(self):
        ctx = get_finalization_email_context(self.logsheet)
        assert "All clear." in ctx["safety_issues_html"]
        assert "Good day." in ctx["operations_summary_html"]
        assert ctx["equipment_issues_html"] == ""

    def test_flights_list_is_empty_when_no_flights(self):
        ctx = get_finalization_email_context(self.logsheet)
        assert ctx["flights"] == []

    def test_flights_list_sorted_and_enriched(self):
        from logsheet.models import Flight

        pilot = Member.objects.create_user(
            username="pilot1",
            password="test",
            first_name="Pilot",
            last_name="One",
            membership_status="Full Member",
            is_active=True,
        )
        Flight.objects.create(
            logsheet=self.logsheet,
            pilot=pilot,
            glider=self.glider,
            airfield=self.airfield,
            flight_type="solo",
            launch_time=time(10, 0),
            landing_time=time(11, 30),
            duration=timedelta(hours=1, minutes=30),
            release_altitude=2000,
        )
        ctx = get_finalization_email_context(self.logsheet)
        assert len(ctx["flights"]) == 1
        row = ctx["flights"][0]
        assert row["pilot_name"] == "Pilot One"
        assert row["duration_str"] == "1:30"
        assert row["is_longest"] is True
        assert row["launch_time"] == "10:00"
        assert row["landing_time"] == "11:30"
        assert row["release_altitude"] == 2000

    def test_longest_flight_highlighted(self):
        from logsheet.models import Flight

        pilot = Member.objects.create_user(
            username="p2",
            password="test",
            first_name="P",
            last_name="Two",
            membership_status="Full Member",
            is_active=True,
        )
        pilot2 = Member.objects.create_user(
            username="p3",
            password="test",
            first_name="P",
            last_name="Three",
            membership_status="Full Member",
            is_active=True,
        )
        glider2 = Glider.objects.create(
            n_number="N222BB", club_owned=True, is_active=True
        )
        Flight.objects.create(
            logsheet=self.logsheet,
            pilot=pilot,
            glider=self.glider,
            airfield=self.airfield,
            flight_type="solo",
            launch_time=time(9, 0),
            landing_time=time(9, 45),
            duration=timedelta(minutes=45),
            release_altitude=1500,
        )
        Flight.objects.create(
            logsheet=self.logsheet,
            pilot=pilot2,
            glider=glider2,
            airfield=self.airfield,
            flight_type="dual",
            launch_time=time(10, 0),
            landing_time=time(11, 30),
            duration=timedelta(hours=1, minutes=30),
            release_altitude=2000,
        )
        ctx = get_finalization_email_context(self.logsheet)
        rows = ctx["flights"]
        assert len(rows) == 2
        shortest = next(r for r in rows if r["duration_str"] == "0:45")
        longest = next(r for r in rows if r["duration_str"] == "1:30")
        assert shortest["is_longest"] is False
        assert longest["is_longest"] is True

    def test_maintenance_issues_included(self):
        MaintenanceIssue.objects.create(
            logsheet=self.logsheet,
            description="Brake squeaking",
            glider=self.glider,
            grounded=False,
            resolved=False,
        )
        ctx = get_finalization_email_context(self.logsheet)
        assert len(ctx["maintenance_issues"]) == 1


# ---------------------------------------------------------------------------
# send_finalization_summary_email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSendFinalizationSummaryEmail:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        MembershipStatus.objects.update_or_create(
            name="Full Member",
            defaults={"is_active": True},
        )
        MembershipStatus.objects.update_or_create(
            name="Inactive Member",
            defaults={"is_active": False},
        )
        self.airfield = Airfield.objects.create(identifier="KBAR", name="Bar Field")
        self.member = Member.objects.create_user(
            username="do2",
            password="test",
            first_name="D",
            last_name="O",
            membership_status="Full Member",
            is_active=True,
            email="do@example.com",
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date(2025, 8, 1),
            airfield=self.airfield,
            created_by=self.member,
        )
        LogsheetCloseout.objects.create(
            logsheet=self.logsheet,
            safety_issues="",
            equipment_issues="",
            operations_summary="<p>Great flying day.</p>",
        )

    @patch("logsheet.utils.finalization_email.send_mail")
    def test_email_sent_to_active_members(self, mock_send):
        Member.objects.create_user(
            username="active2",
            password="test",
            membership_status="Full Member",
            is_active=True,
            email="member2@example.com",
        )
        send_finalization_summary_email(self.logsheet)
        # send_mail is called once per recipient (individual sends to avoid
        # disclosing member addresses to each other via the To: header).
        assert mock_send.call_count == 2
        all_recipients = [
            call.kwargs.get(
                "recipient_list",
                call.args[3] if len(call.args) > 3 else [],
            )
            for call in mock_send.call_args_list
        ]
        # Each call should target exactly one address
        assert all(len(r) == 1 for r in all_recipients)
        called_addresses = {r[0] for r in all_recipients}
        assert "do@example.com" in called_addresses
        assert "member2@example.com" in called_addresses

    @patch("logsheet.utils.finalization_email.send_mail")
    def test_email_excludes_inactive_membership_status(self, mock_send):
        Member.objects.create_user(
            username="inactive_status_user",
            password="test",
            membership_status="Inactive Member",
            is_active=True,
            email="inactive-status@example.com",
        )
        Member.objects.create_user(
            username="active3",
            password="test",
            membership_status="Full Member",
            is_active=True,
            email="member3@example.com",
        )

        send_finalization_summary_email(self.logsheet)

        called_addresses = {
            call.kwargs.get(
                "recipient_list",
                call.args[3] if len(call.args) > 3 else [],
            )[0]
            for call in mock_send.call_args_list
        }
        assert "do@example.com" in called_addresses
        assert "member3@example.com" in called_addresses
        assert "inactive-status@example.com" not in called_addresses

    @patch("logsheet.utils.finalization_email.send_mail")
    def test_email_not_sent_when_no_active_members_with_email(self, mock_send):
        # Remove email from all members
        Member.objects.all().update(email="")
        send_finalization_summary_email(self.logsheet)
        mock_send.assert_not_called()

    @patch("logsheet.utils.finalization_email.send_mail")
    def test_subject_contains_club_name_and_date(self, mock_send):
        send_finalization_summary_email(self.logsheet)
        assert mock_send.called
        subject = mock_send.call_args.kwargs.get(
            "subject", mock_send.call_args.args[0] if mock_send.call_args.args else ""
        )
        # The date portion should appear in the subject
        assert "2025" in subject or "August" in subject

    @patch(
        "logsheet.utils.finalization_email.send_mail",
        side_effect=Exception("SMTP error"),
    )
    def test_exception_does_not_propagate(self, mock_send):
        # Errors must be caught and logged, never raised
        send_finalization_summary_email(self.logsheet)  # should not raise

    @patch("logsheet.utils.finalization_email.send_mail")
    def test_renders_html_and_text_templates(self, mock_send):
        send_finalization_summary_email(self.logsheet)
        assert mock_send.called
        kwargs = mock_send.call_args.kwargs
        assert kwargs.get("html_message") is not None
        assert "Operations Summary" in kwargs.get("html_message", "")
        assert kwargs.get("message") is not None
        assert "Great flying day" in kwargs.get("message", "")

    @patch("logsheet.utils.finalization_email.send_mail")
    def test_text_template_preserves_link_urls(self, mock_send):
        self.logsheet.closeout.operations_summary = (
            '<p>Read <a href="https://example.com/manual.pdf">Manual</a></p>'
        )
        self.logsheet.closeout.save()

        send_finalization_summary_email(self.logsheet)

        kwargs = mock_send.call_args.kwargs
        assert "Manual (https://example.com/manual.pdf)" in kwargs.get("message", "")

    @patch(
        "logsheet.utils.finalization_email.render_to_string",
        side_effect=Exception("Template rendering error"),
    )
    def test_template_render_exception_does_not_propagate(self, mock_render):
        send_finalization_summary_email(self.logsheet)
        assert mock_render.called
