import pytest
from django.contrib import admin
from django.urls import reverse

from logsheet.admin import CommercialRideAdmin, CommercialTicketAdmin
from logsheet.models import CommercialRide, CommercialTicket


@pytest.mark.django_db
def test_commercial_admin_models_registered():
    """Commercial ticket and ride models are exposed in Django admin."""
    assert isinstance(admin.site._registry.get(CommercialTicket), CommercialTicketAdmin)
    assert isinstance(admin.site._registry.get(CommercialRide), CommercialRideAdmin)


@pytest.mark.django_db
def test_commercial_ticket_admin_changelist_accessible(client, django_user_model):
    """Superusers can access the commercial ticket changelist page."""
    admin_user = django_user_model.objects.create_user(
        username="admin_user",
        email="admin@example.com",
        password="testpass123",
        membership_status="Full Member",
        is_staff=True,
        is_superuser=True,
    )

    client.force_login(admin_user)
    url = reverse("admin:logsheet_commercialticket_changelist")
    response = client.get(url)

    assert response.status_code == 200
