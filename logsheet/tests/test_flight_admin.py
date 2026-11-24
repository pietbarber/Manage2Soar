"""Regression tests for Issue #1163: remove the obsolete ``flight_type`` field
from the Flight admin add/change forms.

``Flight.flight_type`` is a required ``CharField`` with no default. Because
``FlightAdmin`` previously declared no ``exclude``, Django auto-rendered the
field as required on the add/change forms, so every admin save failed with
"Flight Type is required." The fix excludes the field from the admin form while
leaving it on the model for existing data and downstream consumers.
"""

import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from logsheet.models import Flight


@pytest.mark.django_db
def test_flight_admin_registered():
    """FlightAdmin is registered for the Flight model."""
    from logsheet.admin import FlightAdmin

    assert isinstance(admin.site._registry.get(Flight), FlightAdmin)


@pytest.mark.django_db
def test_flight_type_excluded_from_admin_form(django_user_model):
    """``flight_type`` must not appear on the admin add/change form."""
    user = django_user_model.objects.create_user(
        username="form_admin",
        email="form_admin@example.com",
        password="testpass123",
        membership_status="Full Member",
        is_staff=True,
        is_superuser=True,
    )
    request = RequestFactory().get("/admin/logsheet/flight/add/")
    request.user = user

    flight_admin = admin.site._registry[Flight]
    form_class = flight_admin.get_form(request=request)
    assert "flight_type" not in form_class().fields


@pytest.mark.django_db
def test_flight_admin_add_saves_without_flight_type(
    client, django_user_model, logsheet, active_member, glider, airfield
):
    """A flight can be saved through the admin add form without ``flight_type``.

    Regression test: before the fix, this POST failed validation with
    "Flight Type is required." After the fix, the save succeeds and redirects
    to the changelist.
    """
    admin_user = django_user_model.objects.create_user(
        username="flight_admin",
        email="flight_admin@example.com",
        password="testpass123",
        membership_status="Full Member",
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(admin_user)

    url = reverse("admin:logsheet_flight_add")
    response = client.post(
        url,
        {
            "logsheet": logsheet.id,
            "pilot": active_member.id,
            "glider": glider.id,
            "launch_method": "tow",
            "airfield": airfield.id,
            "_save": "Save",
        },
        follow=True,
    )

    # A successful admin save redirects to the changelist.
    assert response.status_code == 200
    assert response.redirect_chain, "Expected a redirect after a successful save"
    assert Flight.objects.filter(logsheet=logsheet).exists()
