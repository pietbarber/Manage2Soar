"""
Tests for cms.context_processors — specifically the google_oauth_configured flag
and its effect on the login page template.
"""

import pytest
from django.test import override_settings
from django.urls import reverse


@pytest.mark.django_db
def test_google_oauth_configured_true_when_key_set(client):
    """google_oauth_configured is True when SOCIAL_AUTH_GOOGLE_OAUTH2_KEY is set."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="fake-key"):
        response = client.get(reverse("login"))
    assert response.context["google_oauth_configured"] is True


@pytest.mark.django_db
def test_google_oauth_configured_false_when_key_missing(client):
    """google_oauth_configured is False when SOCIAL_AUTH_GOOGLE_OAUTH2_KEY is None."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=None):
        response = client.get(reverse("login"))
    assert response.context["google_oauth_configured"] is False


@pytest.mark.django_db
def test_login_page_shows_google_button_when_configured(client):
    """The login page renders the Sign in with Google button when OAuth is configured."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="fake-key"):
        response = client.get(reverse("login"))
    assert b"Sign in with Google" in response.content


@pytest.mark.django_db
def test_login_page_hides_google_button_when_not_configured(client):
    """The login page omits the Sign in with Google button when OAuth is not configured."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=None):
        response = client.get(reverse("login"))
    assert b"Sign in with Google" not in response.content
