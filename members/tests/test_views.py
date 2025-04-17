import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from members.models import Biography

User = get_user_model()


@pytest.mark.django_db
def test_biography_view_shows_biography(client):
    user = User.objects.create_user(username="jdoe", password="password", first_name="John", last_name="Doe", membership_status="Full Member")
    Biography.objects.create(member=user, content="<p>Hello!</p>")
    client.force_login(user)  # ✅ log in as the test user
    url = reverse("members:biography_view", args=[user.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Hello!" in response.content

@pytest.mark.django_db
def test_biography_view_returns_404_for_missing_user(client):
    user = User.objects.create_user(username="testuser", password="pass", membership_status="Full Member")
    client.force_login(user)  # ✅ Must be logged in to even trigger the 404
    url = reverse("members:biography_view", args=[99999])  # assuming this ID doesn't exist
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_set_password_get_shows_form(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="tester", 
        password="oldpass",
        membership_status="Full Member",  # ✅ Must be one of the items in DEFAULT_ACTIVE_STATUSES
        is_superuser=False
    )
    client.force_login(user)
    url = reverse("members:set_password")
    response = client.get(url)
    assert response.status_code == 200
    assert b"New password" in response.content


@pytest.mark.django_db
def test_set_password_mismatched_passwords(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="tester", 
        password="oldpass",
        membership_status="Full Member",  # ✅ Must be one of the items in DEFAULT_ACTIVE_STATUSES
        is_superuser=False
    )
    client.force_login(user)
    url = reverse("members:set_password")
    response = client.post(url, {"new_password1": "abc123", "new_password2": "wrong123"})
    print(response.content.decode())
    assert b"The two password fields didn't match" in response.content
    assert b"Passwords must match" in response.content
    assert response.status_code == 200

@pytest.mark.django_db
def test_set_password_mismatched_passwords(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="tester2",
        password="initial",
        membership_status="Full Member",
        is_superuser=False
    )
    client.force_login(user)
    url = reverse("members:set_password")

    response = client.post(url, {
        "new_password1": "newpass123",
        "new_password2": "wrongpass456",  # mismatch on purpose
    })

    assert response.status_code == 200  # Form should re-render with errors

    # 🕵️ Use this temporarily to inspect what error string is returned
    print(response.content.decode())

    # ✅ Adjust this to match the actual error message used in your form
    assert b"Passwords must match" in response.content or b"do not match" in response.content.lower()


from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.mark.django_db
def test_tinymce_upload_rejects_anonymous(client):
    url = reverse("members:tinymce_image_upload")
    image_data = SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg")
    response = client.post(url, {"file": image_data})
    assert response.status_code in (302, 403)

@pytest.mark.django_db
def test_tinymce_upload_accepts_image(client, django_user_model, settings):
    user = django_user_model.objects.create_user(
        username="tester", 
        password="oldpass",
        membership_status="Full Member",  # ✅ Must be one of the items in DEFAULT_ACTIVE_STATUSES
        is_superuser=False
    )
    client.force_login(user)
    url = reverse("members:tinymce_image_upload")

    image_data = SimpleUploadedFile("test.jpg", b"fake-image-content", content_type="image/jpeg")
    response = client.post(url, {"file": image_data})

    assert response.status_code == 200
    assert "location" in response.json()
    assert response.json()["location"].startswith("/media/")
