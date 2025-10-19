import pytest

from datetime import date

from django.urls import reverse

from duty_roster.models import OpsIntent


@pytest.mark.django_db
def test_admin_helper_message_shown_in_changelist(client, django_user_model):
    # create staff user
    admin = django_user_model.objects.create_user(
        username="adminuser", email="admin@example.com", password="pass"
    )
    admin.is_staff = True
    admin.is_superuser = True
    admin.save()

    # login
    logged = client.login(username="adminuser", password="pass")
    assert logged

    url = reverse("admin:duty_roster_dutyassignment_changelist")
    resp = client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    # the AdminHelperMixin message includes 'Duty Assignments'
    assert "Duty Assignments" in content


@pytest.mark.django_db
def test_ops_intent_admin_shows_labels_in_list_display(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="u1", email="u1@example.com", password="pass")
    # create an ops intent and ensure admin changelist doesn't error when rendering
    OpsIntent.objects.create(member=user, date=date(
        2025, 11, 8), available_as=["instruction", "private"])

    admin = django_user_model.objects.create_user(
        username="admin2", email="admin2@example.com", password="pass"
    )
    admin.is_staff = True
    admin.is_superuser = True
    admin.save()
    client.login(username="admin2", password="pass")
    url = reverse("admin:duty_roster_opsintent_changelist")
    resp = client.get(url)
    assert resp.status_code == 200
    assert "Planned activities" in resp.content.decode("utf-8")
