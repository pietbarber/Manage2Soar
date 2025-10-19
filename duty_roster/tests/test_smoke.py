import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_duty_roster_index_renders(client, django_user_model):
    """Basic smoke test: the duty roster index page renders for an anonymous or staff user."""
    url = reverse("duty_roster:roster_home")

    # Try anonymous first
    resp = client.get(url)
    if resp.status_code == 200:
        assert True
        return

    # Otherwise create a staff user and retry
    user = django_user_model.objects.create_user(
        username="teststaff",
        email="teststaff@example.com",
        password="password",
        is_staff=True,
    )
    client.force_login(user)
    resp2 = client.get(url)
    assert resp2.status_code == 200, f"Duty roster index failed: {resp2.status_code}"
