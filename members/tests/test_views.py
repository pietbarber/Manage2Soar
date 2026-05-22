import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from members.models import Biography
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.models import MembershipStatus

User = get_user_model()


@pytest.mark.django_db
def test_biography_view_shows_biography(client):
    user = User.objects.create_user(
        username="jdoe",
        password="password",
        first_name="John",
        last_name="Doe",
        membership_status="Full Member",
    )
    Biography.objects.create(member=user, content="<p>Hello!</p>")
    client.force_login(user)  # ✅ log in as the test user
    url = reverse("members:biography_view", args=[user.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Hello!" in response.content


@pytest.mark.django_db
def test_biography_view_returns_404_for_missing_user(client):
    user = User.objects.create_user(
        username="testuser", password="pass", membership_status="Full Member"
    )
    client.force_login(user)  # ✅ Must be logged in to even trigger the 404
    # assuming this ID doesn't exist
    url = reverse("members:biography_view", args=[99999])
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_set_password_get_shows_form(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="tester",
        password="oldpass",
        # Must be an active status in siteconfig.MembershipStatus
        membership_status="Full Member",
        is_superuser=False,
    )
    client.force_login(user)
    url = reverse("members:set_password")
    response = client.get(url)
    assert response.status_code == 200
    assert b"New password" in response.content


@pytest.mark.django_db
def test_set_password_mismatched_passwords(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="tester2",
        password="initial",
        membership_status="Full Member",
        is_superuser=False,
    )
    client.force_login(user)
    url = reverse("members:set_password")

    response = client.post(
        url,
        {
            "new_password1": "newpass123",
            "new_password2": "wrongpass456",  # mismatch on purpose
        },
    )

    assert response.status_code == 200  # Form should re-render with errors

    # 🕵️ Use this temporarily to inspect what error string is returned
    print(response.content.decode())

    # ✅ Adjust this to match the actual error message used in your form
    assert (
        b"Passwords must match" in response.content
        or b"do not match" in response.content.lower()
    )


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
        # Must be an active status in siteconfig.MembershipStatus
        membership_status="Full Member",
        is_superuser=False,
    )
    client.force_login(user)
    url = reverse("members:tinymce_image_upload")

    image_data = SimpleUploadedFile(
        "test.jpg", b"fake-image-content", content_type="image/jpeg"
    )
    response = client.post(url, {"file": image_data})

    assert response.status_code == 200
    assert "location" in response.json()
    location = response.json()["location"]
    # Accept either local or cloud storage URLs
    assert (
        location.startswith("/media/")
        or location.startswith("http://")
        or location.startswith("https://")
    )


@pytest.mark.django_db
def test_member_list_uses_dynamic_configured_status_checkboxes(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    MembershipStatus.objects.create(name="Guest Pilot", is_active=False, sort_order=20)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="activeperson",
        password="password",
        first_name="Active",
        last_name="Person",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="guestperson",
        password="password",
        first_name="Guest",
        last_name="Person",
        membership_status="Guest Pilot",
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"))

    assert response.status_code == 200
    assert b'value="Aero Member"' in response.content
    assert b'value="Guest Pilot"' in response.content
    assert b"Active Person" in response.content
    assert b"Guest Person" not in response.content


@pytest.mark.django_db
def test_member_list_filters_by_custom_status_value(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    MembershipStatus.objects.create(name="Guest Pilot", is_active=False, sort_order=20)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer2",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="activeonly",
        password="password",
        first_name="Active",
        last_name="Only",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="guestonly",
        password="password",
        first_name="Guest",
        last_name="Only",
        membership_status="Guest Pilot",
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"), {"status": "Guest Pilot"})

    assert response.status_code == 200
    assert b"Guest Only" in response.content
    assert b"Active Only" not in response.content


@pytest.mark.django_db
def test_member_list_supports_legacy_active_status_filter_value(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    MembershipStatus.objects.create(name="Guest Pilot", is_active=False, sort_order=20)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer_legacy_active",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="legacyactive",
        password="password",
        first_name="Legacy",
        last_name="Active",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="legacyinactive",
        password="password",
        first_name="Legacy",
        last_name="Inactive",
        membership_status="Guest Pilot",
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"), {"status": "active"})

    assert response.status_code == 200
    assert b"Legacy Active" in response.content
    assert b"Legacy Inactive" not in response.content


@pytest.mark.django_db
def test_member_list_supports_legacy_inactive_status_filter_value(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    MembershipStatus.objects.create(name="Guest Pilot", is_active=False, sort_order=20)
    MembershipStatus.objects.create(name="Visitor", is_active=False, sort_order=30)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer_legacy_inactive",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="legacyactive2",
        password="password",
        first_name="Legacy",
        last_name="Active Two",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="legacyguest",
        password="password",
        first_name="Legacy",
        last_name="Guest",
        membership_status="Guest Pilot",
    )
    User.objects.create_user(
        username="legacyvisitor",
        password="password",
        first_name="Legacy",
        last_name="Visitor",
        membership_status="Visitor",
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"), {"status": "inactive"})

    assert response.status_code == 200
    assert b"Legacy Active Two" not in response.content
    assert b"Legacy Guest" in response.content
    assert b"Legacy Visitor" in response.content


@pytest.mark.django_db
def test_member_list_uses_dynamic_role_checkboxes(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer3",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="mgruser",
        password="password",
        first_name="Manager",
        last_name="Person",
        membership_status="Aero Member",
        member_manager=True,
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"))

    assert response.status_code == 200
    assert b'value="member_manager"' in response.content


@pytest.mark.django_db
def test_member_list_filters_by_dynamic_role_value(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer4",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="mgronly",
        password="password",
        first_name="Manager",
        last_name="Only",
        membership_status="Aero Member",
        member_manager=True,
    )
    User.objects.create_user(
        username="norole",
        password="password",
        first_name="No",
        last_name="Role",
        membership_status="Aero Member",
        member_manager=False,
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"), {"role": "member_manager"})

    assert response.status_code == 200
    assert b"Manager Only" in response.content
    assert b"No Role" not in response.content


@pytest.mark.django_db
def test_member_list_supports_legacy_dutyofficer_role_filter_value(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer_legacy_role",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="legacyduty",
        password="password",
        first_name="Legacy",
        last_name="Duty",
        membership_status="Aero Member",
        duty_officer=True,
    )
    User.objects.create_user(
        username="legacynotduty",
        password="password",
        first_name="Legacy",
        last_name="Not Duty",
        membership_status="Aero Member",
        duty_officer=False,
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"), {"role": "dutyofficer"})

    assert response.status_code == 200
    assert b"Legacy Duty" in response.content
    assert b"Legacy Not Duty" not in response.content


@pytest.mark.django_db
def test_member_list_hides_roles_without_members(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer5",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="mgrpresent",
        password="password",
        first_name="Manager",
        last_name="Present",
        membership_status="Aero Member",
        member_manager=True,
    )

    client.force_login(viewer)
    response = client.get(reverse("members:member_list"))

    assert response.status_code == 200
    assert b'value="member_manager"' in response.content
    assert b'value="towpilot"' not in response.content


@pytest.mark.django_db
def test_member_list_explicit_empty_status_selection_shows_no_members(client):
    MembershipStatus.objects.create(name="Aero Member", is_active=True, sort_order=10)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="viewer6",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Aero Member",
    )
    User.objects.create_user(
        username="activevisible",
        password="password",
        first_name="Active",
        last_name="Visible",
        membership_status="Aero Member",
    )

    client.force_login(viewer)
    response = client.get(
        reverse("members:member_list"),
        {"status_filter_applied": "1"},
    )

    assert response.status_code == 200
    assert b"Active Visible" not in response.content
    assert b"No members found" in response.content


@pytest.mark.django_db
def test_member_view_status_badge_uses_configured_active_statuses(client):
    MembershipStatus.objects.create(name="Club Pilot", is_active=True, sort_order=10)
    MembershipStatus.objects.create(name="Grounded", is_active=False, sort_order=20)
    clear_active_membership_statuses_cache()

    viewer = User.objects.create_user(
        username="memberviewviewer",
        password="password",
        first_name="View",
        last_name="User",
        membership_status="Club Pilot",
    )
    active_member = User.objects.create_user(
        username="activeprofile",
        password="password",
        first_name="Active",
        last_name="Profile",
        membership_status="Club Pilot",
    )
    inactive_member = User.objects.create_user(
        username="inactiveprofile",
        password="password",
        first_name="Inactive",
        last_name="Profile",
        membership_status="Grounded",
    )

    client.force_login(viewer)

    active_response = client.get(
        reverse("members:member_view", args=[active_member.pk])
    )
    assert active_response.status_code == 200
    assert b"badge bg-light text-dark fs-6" in active_response.content
    assert b"Club Pilot" in active_response.content

    inactive_response = client.get(
        reverse("members:member_view", args=[inactive_member.pk])
    )
    assert inactive_response.status_code == 200
    assert b"badge bg-secondary fs-6" in inactive_response.content
    assert b"Grounded" in inactive_response.content
