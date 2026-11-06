"""Single-host middleware must allow kiosk re-authentication on CSRF-protected POSTs."""

import ast
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.test import Client, override_settings
from django.urls import path
from jinja2 import Template

from manage2soar.settings import MIDDLEWARE as PRIMARY_MIDDLEWARE

ROOT = Path(__file__).resolve().parents[2]
SINGLE_HOST = ROOT / "manage2soar/settings_single_host.py"
ANSIBLE_TEMPLATE = (
    ROOT / "infrastructure/ansible/roles/m2s-app/templates/settings_single_host.py.j2"
)
AUTH_CHAIN = [
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "utils.middleware.KioskAutoLoginMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]


def middleware_from(source):
    tree = ast.parse(source)
    return next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "MIDDLEWARE"
            for target in node.targets
        )
    )


def test_single_host_middleware_matches_rendered_template_and_primary_order():
    local = middleware_from(SINGLE_HOST.read_text())
    rendered = Template(ANSIBLE_TEMPLATE.read_text()).render(
        m2s_import_export_tmp_dir="/opt/m2s/import-export-tmp"
    )
    deployed = middleware_from(rendered)

    assert local == deployed
    for middleware in (PRIMARY_MIDDLEWARE, local, deployed):
        assert [item for item in middleware if item in AUTH_CHAIN] == AUTH_CHAIN


def csrf_test_view(request):
    if request.method == "GET":
        get_token(request)
        return HttpResponse("CSRF cookie ready")
    return JsonResponse(
        {
            "username": request.user.username,
            "kiosk": request.session.get("is_kiosk_authenticated", False),
        }
    )


urlpatterns = [path("kiosk-csrf-check/", csrf_test_view)]


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_kiosk_auto_login_accepts_valid_csrf_post_and_rejects_missing_token(settings):
    from members.models import KioskToken

    settings.MIDDLEWARE = middleware_from(SINGLE_HOST.read_text())
    member = get_user_model().objects.create_user(
        username="single-host-kiosk",
        email="single-host-kiosk@example.com",
        password="testpass123!",
        first_name="Kiosk",
        last_name="User",
        is_staff=True,
        is_superuser=True,
    )
    token = KioskToken.objects.create(user=member, name="Single-host CSRF test")
    token.bind_device("test-fingerprint")

    client = Client(enforce_csrf_checks=True)
    url = "/kiosk-csrf-check/"
    assert client.get(url).status_code == 200
    csrf_token = client.cookies["csrftoken"].value
    client.cookies["kiosk_token"] = token.token
    client.cookies["kiosk_fingerprint"] = "test-fingerprint"

    # This POST is the first kiosk-authenticated request: login() rotates the
    # CSRF secret before CsrfViewMiddleware reads the original cookie secret.
    response = client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
    assert response.status_code == 200
    assert response.json() == {"username": member.username, "kiosk": True}

    assert client.post(url).status_code == 403
