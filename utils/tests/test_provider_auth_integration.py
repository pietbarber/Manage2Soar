"""Exercise the pinned social-django -> Django auth -> Axes/Google chain."""

from types import SimpleNamespace
from unittest import mock

import pytest
from axes.exceptions import AxesBackendPermissionDenied
from django.contrib.auth import authenticate
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory
from django.urls import reverse
from social_core.backends.google import GoogleOAuth2
from social_django.utils import load_backend, load_strategy

from utils.auth_backends import AxesCompatBackend

IP = "203.0.114.41"


@pytest.fixture
def locked_ip(settings):
    settings.CLIENT_IP_TRUSTED_PROXIES = ["127.0.0.1/32"]
    settings.CLIENT_IP_TRAILING_PROXIES = 0
    client = Client()
    # Separate usernames isolate the IP bucket from the username bucket.
    for index in range(settings.AXES_FAILURE_LIMIT):
        client.post(
            reverse("login"),
            {"username": f"provider-ip-failure-{index}", "password": "incorrect"},
            HTTP_X_FORWARDED_FOR=IP,
        )
    request = RequestFactory().get("/complete/google-oauth2/", HTTP_X_FORWARDED_FOR=IP)
    SessionMiddleware(lambda req: None).process_request(request)
    return request


@pytest.mark.django_db
def test_google_strategy_authenticates_despite_password_ip_lockout(locked_ip):
    """Use the actual strategy and configured backend chain, without Google I/O."""
    request = locked_ip
    strategy = load_strategy(request)
    google = load_backend(strategy, "google-oauth2", "/complete/google-oauth2/")
    sentinel_user = SimpleNamespace()

    # BaseAuth.authenticate checks its provider markers before calling pipeline;
    # replacing only the pipeline keeps the real GoogleOAuth2.authenticate path.
    with mock.patch.object(
        GoogleOAuth2, "pipeline", return_value=sentinel_user
    ) as pipeline:
        result = strategy.authenticate(
            google, request=request, response={"email": "a@example.org"}
        )

    assert result is sentinel_user
    pipeline.assert_called_once()
    assert not getattr(request, "axes_locked_out", False)


@pytest.mark.django_db
def test_password_credentials_cannot_claim_provider_exemption(locked_ip):
    """A forged BaseAuth kwarg, even with real strategy markers, cannot bypass Axes."""
    request = locked_ip
    strategy = load_strategy(request)
    google = load_backend(strategy, "google-oauth2", "/complete/google-oauth2/")
    with pytest.raises(AxesBackendPermissionDenied):
        AxesCompatBackend().authenticate(
            request, username="victim", password="guess", backend=google
        )
    with pytest.raises(AxesBackendPermissionDenied):
        AxesCompatBackend().authenticate(
            request,
            username="victim",
            password="guess",
            backend=google,
            strategy=strategy,
            storage=strategy.storage,
            response={"email": "a@example.org"},
        )
    # Django's dispatcher must not authenticate password credentials either.
    assert (
        authenticate(request, username="victim", password="guess", backend=google)
        is None
    )
