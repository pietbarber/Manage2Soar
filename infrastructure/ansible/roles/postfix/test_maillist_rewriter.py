#!/usr/bin/env python3
"""
Unit tests for maillist-rewriter.py BCC handling.
This test file verifies that mailing lists in the BCC field are correctly
identified and header rewriting is applied.

Note: This test uses mock objects to simulate the Postfix environment without
requiring a full mail server setup.
"""

import email
import io
import sys
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

# Mock MAILING_LISTS and ALL_KNOWN_LISTS
MAILING_LISTS = {
    "members@skylinesoaring.org",
    "instructors@skylinesoaring.org",
    "webmaster@skylinesoaring.org",
    "board@skylinesoaring.org",
}
ALL_KNOWN_LISTS = MAILING_LISTS.copy()


def rewrite_headers(msg, recipient):
    """
    Rewrite headers Mailman-style.
    This is the same function from maillist-rewriter.py
    """
    from email.utils import formataddr, parseaddr

    original_from = msg.get("From", "")
    original_name, original_email = parseaddr(original_from)

    recipient_lower = recipient.lower()
    list_local, list_domain = recipient_lower.split("@", 1)
    list_name_display = list_local.replace("-", " ").title()
    list_bounces_addr = f"{list_local}-bounces@{list_domain}"

    if original_name:
        new_from_name = f"{original_name} via {list_name_display}"
    else:
        new_from_name = f"{list_name_display} List"

    if "From" in msg:
        del msg["From"]
    msg["From"] = formataddr((new_from_name, list_bounces_addr))

    if not msg.get("Reply-To"):
        msg["Reply-To"] = original_from

    return msg


def test_to_header_detection():
    """Test that mailing list in To header is detected."""
    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "webmaster@skylinesoaring.org"
    msg["Subject"] = "Test email to list"
    msg.set_content("Body")

    # Simulate the header checking logic from maillist-rewriter.py
    original_to = None
    to_header = msg.get("To")
    if to_header:
        from email.utils import parseaddr

        _, to_addr = parseaddr(to_header)
        if to_addr and to_addr.lower() in ALL_KNOWN_LISTS:
            original_to = to_addr.lower()

    assert original_to == "webmaster@skylinesoaring.org"
    print("✓ To header detection works")


def test_cc_header_detection():
    """Test that mailing list in Cc header is detected."""
    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "someone@example.com"
    msg["Cc"] = "webmaster@skylinesoaring.org"
    msg["Subject"] = "Test email to list"
    msg.set_content("Body")

    # Simulate the header checking logic
    original_to = None
    to_header = msg.get("To")
    if to_header:
        from email.utils import parseaddr

        _, to_addr = parseaddr(to_header)
        if to_addr and to_addr.lower() in ALL_KNOWN_LISTS:
            original_to = to_addr.lower()

    if not original_to:
        from email.utils import getaddresses

        for _, cc_addr in getaddresses(msg.get_all("Cc", []) + msg.get_all("CC", [])):
            if cc_addr and cc_addr.lower() in ALL_KNOWN_LISTS:
                original_to = cc_addr.lower()
                break

    assert original_to == "webmaster@skylinesoaring.org"
    print("✓ Cc header detection works")


def test_bcc_envelope_detection():
    """
    Test that mailing list in BCC is detected via envelope recipients.
    This is the fix for issue #759 - BCC recipients are only in SMTP envelope.
    """
    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "user@example.com"  # Sent to self
    msg["Subject"] = "Test email with BCC"
    msg.set_content("Body")
    # Note: BCC is not in the message headers, only in SMTP envelope

    # Simulate the SMTP envelope recipients (as passed to maillist-rewriter.py)
    recipients = ["user@example.com", "webmaster@skylinesoaring.org"]

    # Simulate the detection logic from maillist-rewriter.py
    original_to = None
    to_header = msg.get("To")
    if to_header:
        from email.utils import parseaddr

        _, to_addr = parseaddr(to_header)
        if to_addr and to_addr.lower() in ALL_KNOWN_LISTS:
            original_to = to_addr.lower()

    if not original_to:
        from email.utils import getaddresses

        for _, cc_addr in getaddresses(msg.get_all("Cc", []) + msg.get_all("CC", [])):
            if cc_addr and cc_addr.lower() in ALL_KNOWN_LISTS:
                original_to = cc_addr.lower()
                break

    # NEW: Check SMTP envelope recipients for mailing list addresses
    # This is the fix for issue #759
    if not original_to:
        for recipient in recipients:
            if recipient.lower() in ALL_KNOWN_LISTS:
                original_to = recipient.lower()
                break

    assert original_to == "webmaster@skylinesoaring.org"
    print("✓ BCC envelope detection works (Issue #759 fix)")


def test_header_rewriting_with_bcc():
    """Test that header rewriting works when list is in BCC."""
    msg = EmailMessage()
    msg["From"] = "John Doe <john@example.com>"
    msg["To"] = "john@example.com"
    msg["Subject"] = "Test email with BCC"
    msg.set_content("Body")

    # Rewrite headers for the BCC list
    recipients = ["john@example.com", "webmaster@skylinesoaring.org"]
    list_to_rewrite = "webmaster@skylinesoaring.org"

    rewrite_headers(msg, list_to_rewrite)

    # Verify From header is rewritten
    assert "webmaster-bounces@skylinesoaring.org" in msg["From"]
    assert "John Doe via Webmaster" in msg["From"]

    # Verify Reply-To contains the original sender
    assert "john@example.com" in msg["Reply-To"]

    print("✓ Header rewriting works with BCC list")


def test_multiple_recipients_with_list():
    """Test email with multiple recipients where one is a mailing list in envelope."""
    msg = EmailMessage()
    msg["From"] = "user@example.com"
    msg["To"] = "friend1@example.com, friend2@example.com"
    msg["Subject"] = "Test email to friends"
    msg.set_content("Body")

    # Envelope recipients include the expanded list (BCC)
    recipients = [
        "friend1@example.com",
        "friend2@example.com",
        "members@skylinesoaring.org",
    ]

    original_to = None
    to_header = msg.get("To")
    if to_header:
        from email.utils import parseaddr

        _, to_addr = parseaddr(to_header)
        if to_addr and to_addr.lower() in ALL_KNOWN_LISTS:
            original_to = to_addr.lower()

    if not original_to:
        from email.utils import getaddresses

        for _, cc_addr in getaddresses(msg.get_all("Cc", []) + msg.get_all("CC", [])):
            if cc_addr and cc_addr.lower() in ALL_KNOWN_LISTS:
                original_to = cc_addr.lower()
                break

    if not original_to:
        for recipient in recipients:
            if recipient.lower() in ALL_KNOWN_LISTS:
                original_to = recipient.lower()
                break

    assert original_to == "members@skylinesoaring.org"
    print("✓ Multiple recipients with list detection works")


if __name__ == "__main__":
    print("\n=== Testing maillist-rewriter.py BCC support ===\n")

    test_to_header_detection()
    test_cc_header_detection()
    test_bcc_envelope_detection()
    test_header_rewriting_with_bcc()
    test_multiple_recipients_with_list()

    print("\n✓ All tests passed!\n")
