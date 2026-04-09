import pytest
from django.urls import reverse

from logsheet.models import CommercialTicket
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
def test_issue_ticket_view_denies_member_without_role(client, django_user_model):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="regular_member",
        password="testpass123",
        email="member@example.com",
        membership_status="Full Member",
    )

    client.force_login(user)
    response = client.get(reverse("logsheet:issue_commercial_ticket"))

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role_field",
    ["duty_officer", "treasurer"],
)
def test_issue_ticket_view_allows_configured_roles(
    client, django_user_model, role_field
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    kwargs = {role_field: True}
    user = django_user_model.objects.create_user(
        username=f"role_{role_field}",
        password="testpass123",
        email=f"{role_field}@example.com",
        membership_status="Full Member",
        **kwargs,
    )

    client.force_login(user)
    response = client.get(reverse("logsheet:issue_commercial_ticket"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_issue_ticket_post_creates_available_ticket_with_entered_by(
    client, django_user_model
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="treasurer_user",
        password="testpass123",
        email="treasurer@example.com",
        membership_status="Full Member",
        treasurer=True,
    )

    client.force_login(user)
    response = client.post(
        reverse("logsheet:issue_commercial_ticket"),
        data={
            "ride_type": CommercialTicket.RideType.EXTENDED,
            "amount_paid": "125.00",
            "gift_certificate_number": "GC-001",
            "gift_certificate_expires_on": "2030-01-01",
            "remarks": "Issued at front desk",
        },
    )

    assert response.status_code == 200
    ticket = CommercialTicket.objects.get()
    assert ticket.status == CommercialTicket.Status.AVAILABLE
    assert ticket.entered_by == user
    assert ticket.ride_type == CommercialTicket.RideType.EXTENDED
    assert ticket.ticket_number.startswith("T-")


@pytest.mark.django_db
def test_issue_ticket_post_auto_numbers_sequentially(client, django_user_model):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="duty_officer_user",
        password="testpass123",
        email="dutyofficer@example.com",
        membership_status="Full Member",
        duty_officer=True,
    )

    CommercialTicket.objects.create(ticket_number="T-000009")

    client.force_login(user)
    response = client.post(
        reverse("logsheet:issue_commercial_ticket"),
        data={"ride_type": CommercialTicket.RideType.STANDARD},
    )

    assert response.status_code == 200
    new_ticket = CommercialTicket.objects.exclude(ticket_number="T-000009").get()
    assert new_ticket.ticket_number == "T-000010"


@pytest.mark.django_db
def test_commercial_ticket_register_denies_member_without_role(
    client, django_user_model
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="regular_register_member",
        password="testpass123",
        email="member-register@example.com",
        membership_status="Full Member",
    )

    client.force_login(user)
    response = client.get(reverse("logsheet:commercial_ticket_register"))

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role_field",
    ["duty_officer", "treasurer"],
)
def test_commercial_ticket_register_allows_configured_roles(
    client, django_user_model, role_field
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    kwargs = {role_field: True}
    user = django_user_model.objects.create_user(
        username=f"register_role_{role_field}",
        password="testpass123",
        email=f"register-{role_field}@example.com",
        membership_status="Full Member",
        **kwargs,
    )

    client.force_login(user)
    response = client.get(reverse("logsheet:commercial_ticket_register"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_commercial_ticket_register_redirects_when_feature_disabled(
    client, django_user_model
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=False,
    )
    user = django_user_model.objects.create_user(
        username="register_treasurer",
        password="testpass123",
        email="register-treasurer@example.com",
        membership_status="Full Member",
        treasurer=True,
    )

    client.force_login(user)
    response = client.get(reverse("logsheet:commercial_ticket_register"))

    assert response.status_code == 302
    assert response.url == reverse("logsheet:index")
