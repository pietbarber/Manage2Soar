"""Focused django-axes regression tests."""

import pytest
from test_login_throttle_support import trusted_test_proxy  # noqa: F401


@pytest.mark.django_db
class TestClientIpSelection:
    """``get_client_ip`` must pick the client entry the trusted upstream proxy
    observed, not a client-controlled (spoofable) entry and not the shared
    load-balancer IP.

    Per the GCP external Application Load Balancer docs, the LB appends
    ``<client-ip>, <load-balancer-ip>`` to the right of any client-supplied
    ``X-Forwarded-For`` value:

        XFF: <existing spoofable entries>, <client-ip>, <load-balancer-ip>

    So the trustworthy client entry is the second-from-right entry (default
    ``CLIENT_IP_TRAILING_PROXIES = 1``), while the right-most entry is the
    shared LB address.
    """

    @staticmethod
    def _ip(xff, remote="1.1.1.1"):
        from django.test import RequestFactory

        from utils.ip_utils import get_client_ip

        r = RequestFactory().get("/x")
        if xff is not None:
            r.META["HTTP_X_FORWARDED_FOR"] = xff
        r.META["REMOTE_ADDR"] = remote
        return get_client_ip(r)

    @pytest.fixture(autouse=True)
    def gke_proxy(self, settings):
        settings.CLIENT_IP_TRUSTED_PROXIES = ["1.1.1.1/32"]
        settings.CLIENT_IP_TRAILING_PROXIES = 1

    def test_selects_second_from_right_for_gke_header(self):
        """Realistic GKE header: ``<spoof>, <client>, <load-balancer>`` → client."""
        ip = self._ip("8.8.8.8, 203.0.113.5, 198.51.100.99")
        assert ip == "203.0.113.5", (
            "The second-from-right entry is the client the LB observed; the "
            "right-most is the shared LB IP and the left is client-controlled."
        )

    def test_clean_two_entry_header(self):
        """Clean header with no spoofing: ``<client>, <load-balancer>`` → client."""
        assert self._ip("198.51.100.7, 198.51.100.99") == "198.51.100.7"

    def test_short_chain_fails_closed(self):
        assert self._ip("198.51.100.7") == "1.1.1.1"

    @pytest.mark.parametrize(
        "xff",
        ["", " ", "bad, 198.51.100.99", "1.2.3.4,", ", 1.2.3.4", "999.1.1.1, 1.2.3.4"],
    )
    def test_invalid_chain_fails_closed(self, xff):
        assert self._ip(xff) == "1.1.1.1"

    def test_untrusted_peer_cannot_spoof_header(self):
        assert self._ip("203.0.113.5, 198.51.100.99", remote="10.0.0.9") == "10.0.0.9"

    def test_empty_trusted_proxy_list_ignores_spoofed_header(self, settings):
        settings.CLIENT_IP_TRUSTED_PROXIES = []
        assert self._ip("203.0.113.5, 198.51.100.99") == "1.1.1.1"

    def test_no_xff_uses_remote_addr(self):
        """No XFF header (local dev / tests) falls back to REMOTE_ADDR."""
        assert self._ip(None, remote="10.0.0.9") == "10.0.0.9"

    def test_multi_entry_does_not_pick_shared_lb_ip(self):
        """A multi-hop chain must not select the shared (right-most) address."""
        ip = self._ip("1.2.3.4, 5.6.7.8, 9.9.9.9, 10.10.10.10")
        assert ip == "9.9.9.9", (
            "Must select the client entry (second from right), not the shared "
            "load-balancer IP (right-most)."
        )
