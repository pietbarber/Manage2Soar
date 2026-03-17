#!/usr/bin/env python3
"""Tests for maillist-rewriter template logic.

These tests load and execute function logic from
infrastructure/ansible/roles/postfix/templates/maillist-rewriter.py.j2
so test behavior stays aligned with the deployed script.
"""

import re
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, cast
from unittest.mock import mock_open, patch

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "maillist-rewriter.py.j2"


def load_template_namespace():
    """Load executable Python from the Jinja template for unit testing."""
    source = _TEMPLATE_PATH.read_text(encoding="utf-8")

    # Replace Jinja MAILING_LISTS block with deterministic static test data.
    source, mailing_lists_replacements = re.subn(
        r"MAILING_LISTS\s*=\s*\{\n.*?\n\}",
        """MAILING_LISTS = {
    'members@skylinesoaring.org',
    'members@ssc.manage2soar.com',
    'instructors@skylinesoaring.org',
    'webmaster@skylinesoaring.org',
    'board@skylinesoaring.org',
}""",
        source,
        flags=re.DOTALL,
    )
    assert mailing_lists_replacements == 1, (
        "Failed to replace MAILING_LISTS block in maillist-rewriter template; "
        "template structure may have changed"
    )

    # Avoid filesystem dependency during module import.
    source, all_known_lists_replacements = re.subn(
        r"ALL_KNOWN_LISTS\s*=\s*MAILING_LISTS\s*\|\s*_load_lists_from_virtual\(\)",
        "ALL_KNOWN_LISTS = MAILING_LISTS.copy()",
        source,
    )
    assert all_known_lists_replacements == 1, (
        "Failed to replace ALL_KNOWN_LISTS initialization in maillist-rewriter "
        "template; template structure may have changed"
    )

    namespace = {"__name__": "maillist_rewriter_under_test"}
    exec(compile(source, str(_TEMPLATE_PATH), "exec"), namespace)
    return namespace


def get_callable(namespace, name):
    """Return a named callable from dynamic template namespace."""
    return cast(Callable[..., Any], namespace[name])


def test_to_header_detection():
    """List in To header is detected by production logic."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "webmaster@skylinesoaring.org"
    msg["Subject"] = "Test email to list"
    msg.set_content("Body")

    original_to = detect_original_list(msg, ["webmaster@skylinesoaring.org"])
    assert original_to == "webmaster@skylinesoaring.org"


def test_to_header_detection_with_multiple_addresses_list_not_first():
    """List in multi-address To is detected even when not first."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = (
        '"Doe, Jane" <jane@example.com>, '
        '"Club Webmaster" <webmaster@skylinesoaring.org>'
    )
    msg["Subject"] = "Test multi-address To"
    msg.set_content("Body")

    original_to = detect_original_list(
        msg,
        ["jane@example.com", "webmaster@skylinesoaring.org"],
    )
    assert original_to == "webmaster@skylinesoaring.org"


def test_cc_header_detection():
    """List in Cc header is detected by production logic."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "someone@example.com"
    msg["Cc"] = "webmaster@skylinesoaring.org"
    msg["Subject"] = "Test email"
    msg.set_content("Body")

    original_to = detect_original_list(msg, ["someone@example.com"])
    assert original_to == "webmaster@skylinesoaring.org"


def test_bcc_envelope_detection():
    """List in envelope recipients is detected for BCC."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "user@example.com"
    msg["Subject"] = "Test email with BCC"
    msg.set_content("Body")

    recipients = ["user@example.com", "webmaster@skylinesoaring.org"]
    original_to = detect_original_list(msg, recipients)

    assert original_to == "webmaster@skylinesoaring.org"


def test_header_rewriting_with_bcc():
    """Header rewrite function from template preserves expected behavior."""
    ns = load_template_namespace()
    rewrite_headers = get_callable(ns, "rewrite_headers")

    msg = EmailMessage()
    msg["From"] = "John Doe <john@example.com>"
    msg["To"] = "john@example.com"
    msg["Subject"] = "Test email"
    msg.set_content("Body")

    rewrite_headers(msg, "webmaster@skylinesoaring.org")

    assert "webmaster-bounces@skylinesoaring.org" in msg["From"]
    assert "John Doe via Webmaster" in msg["From"]
    assert "john@example.com" in msg["Reply-To"]


def test_reverse_lookup_subset_match_for_bcc_plus_direct_recipient():
    """Fallback reverse lookup handles expanded list members + extra recipient."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "user@skylinesoaring.org"
    msg["Subject"] = "Test email"
    msg.set_content("Body")

    # Simulate post-expansion recipients: list members plus direct To-self recipient.
    recipients = ["member1@example.com", "member2@example.com", "user@example.com"]

    virtual_content = (
        "members@skylinesoaring.org member1@example.com,member2@example.com\n"
        "webmaster@skylinesoaring.org admin@example.com\n"
    )

    with patch("builtins.open", mock_open(read_data=virtual_content)):
        original_to = detect_original_list(msg, recipients)

    assert original_to == "members@skylinesoaring.org"


def test_subset_match_does_not_trigger_for_non_list_direct_group_email():
    """Subset overlap alone should not classify direct group email as list traffic."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "friend@external.example"
    msg["Subject"] = "Direct group email"
    msg.set_content("Body")

    # Looks like board recipients plus an extra direct recipient.
    recipients = ["board1@example.com", "board2@example.com", "friend@external.example"]

    virtual_content = "board@skylinesoaring.org board1@example.com,board2@example.com\n"

    with patch("builtins.open", mock_open(read_data=virtual_content)):
        original_to = detect_original_list(msg, recipients)

    assert original_to is None


def test_reverse_lookup_prefers_most_specific_subset_match_deterministically():
    """Overlapping subset candidates choose the largest alias set consistently."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "user@skylinesoaring.org"
    msg["Subject"] = "Test email"
    msg.set_content("Body")

    # Incoming recipients include a small list (board) and larger list (members).
    recipients = [
        "board1@example.com",
        "board2@example.com",
        "member3@example.com",
        "member4@example.com",
        "user@example.com",
    ]

    virtual_content = (
        "board@skylinesoaring.org board1@example.com,board2@example.com\n"
        "members@skylinesoaring.org board1@example.com,board2@example.com,member3@example.com,member4@example.com\n"
    )

    with patch("builtins.open", mock_open(read_data=virtual_content)):
        original_to = detect_original_list(msg, recipients)

    assert original_to == "members@skylinesoaring.org"


def test_reverse_lookup_domain_preference_is_case_insensitive():
    """Mixed-case To domain still applies preferred-domain filtering."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = '"Pilot" <pilot@SSC.MANAGE2SOAR.COM>'
    msg["Subject"] = "Test domain preference"
    msg.set_content("Body")

    recipients = ["member1@example.com", "member2@example.com"]

    virtual_content = (
        "members@skylinesoaring.org member1@example.com,member2@example.com\n"
        "members@ssc.manage2soar.com member1@example.com,member2@example.com\n"
    )

    with patch("builtins.open", mock_open(read_data=virtual_content)):
        original_to = detect_original_list(msg, recipients)

    assert original_to == "members@ssc.manage2soar.com"


def test_reverse_lookup_uses_exact_alias_token_not_prefix_match():
    """Exact alias key matching avoids members vs members-ops collisions."""
    ns = load_template_namespace()
    detect_original_list = get_callable(ns, "detect_original_list")

    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = '"Pilot" <pilot@skylinesoaring.org>'
    msg["Subject"] = "Test alias exact matching"
    msg.set_content("Body")

    recipients = [
        "member1@example.com",
        "member2@example.com",
        "pilot@skylinesoaring.org",
    ]

    virtual_content = (
        "members-ops@skylinesoaring.org member1@example.com,member2@example.com\n"
        "members@skylinesoaring.org member1@example.com,member2@example.com\n"
    )

    with patch("builtins.open", mock_open(read_data=virtual_content)):
        original_to = detect_original_list(msg, recipients)

    assert original_to == "members@skylinesoaring.org"
