import pytest
from django.core.exceptions import ValidationError
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


@pytest.mark.django_db
def test_issue_ticket_post_handles_allocation_validation_error(
    client, django_user_model, monkeypatch
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="error_treasurer",
        password="testpass123",
        email="error-treasurer@example.com",
        membership_status="Full Member",
        treasurer=True,
    )

    def _raise_allocation_error(**_kwargs):
        raise ValidationError(
            "Could not allocate a unique commercial ticket number. Please try again."
        )

    monkeypatch.setattr(
        "logsheet.views.CommercialTicket.issue_next_available", _raise_allocation_error
    )

    client.force_login(user)
    response = client.post(
        reverse("logsheet:issue_commercial_ticket"),
        data={"ride_type": CommercialTicket.RideType.STANDARD},
    )

    assert response.status_code == 200
    assert (
        b"Could not allocate a unique commercial ticket number. Please try again."
        in response.content
    )


@pytest.mark.django_db
def test_commercial_ticket_register_paginates_results(client, django_user_model):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="pagination_treasurer",
        password="testpass123",
        email="pagination-treasurer@example.com",
        membership_status="Full Member",
        treasurer=True,
    )

    for i in range(55):
        CommercialTicket.objects.create(ticket_number=f"T-{i + 1:06d}")

    client.force_login(user)
    response = client.get(reverse("logsheet:commercial_ticket_register"))

    assert response.status_code == 200
    assert len(response.context["tickets"]) == 50
    assert response.context["page_obj"].has_next()


@pytest.mark.django_db
def test_commercial_ticket_register_renders_entered_at_and_blank_amount(
    client, django_user_model
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="render_duty_officer",
        password="testpass123",
        email="render-duty-officer@example.com",
        membership_status="Full Member",
        duty_officer=True,
    )
    ticket = CommercialTicket.objects.create(ticket_number="T-000111", amount_paid=None)

    client.force_login(user)
    response = client.get(reverse("logsheet:commercial_ticket_register"))

    assert response.status_code == 200
    assert b"T-000111" in response.content
    assert b"$None" not in response.content
    assert response.context["tickets"][0].entered_at == ticket.entered_at


@pytest.mark.django_db
def test_issue_ticket_page_renders_zero_amount_values(client, django_user_model):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )
    user = django_user_model.objects.create_user(
        username="zero_amount_treasurer",
        password="testpass123",
        email="zero-amount@example.com",
        membership_status="Full Member",
        treasurer=True,
    )
    CommercialTicket.objects.create(ticket_number="T-000222", amount_paid="0.00")

    client.force_login(user)
    response = client.get(reverse("logsheet:issue_commercial_ticket"))

    assert response.status_code == 200
    assert b"$0.00" in response.content
