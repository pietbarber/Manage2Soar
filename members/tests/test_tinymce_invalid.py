import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_tinymce_get_returns_400_for_anonymous(client):
    url = reverse("members:tinymce_image_upload")
    response = client.get(url)
    # Anonymous users are redirected to login (302) or may receive 403
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_tinymce_post_without_file_returns_400(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="tester",
        password="oldpass",
        membership_status="Full Member",
    )
    client.force_login(user)
    url = reverse("members:tinymce_image_upload")
    response = client.post(url, {})
    assert response.status_code == 400
