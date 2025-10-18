import pytest
from django.contrib.auth import get_user_model

from members.forms import BiographyForm, MemberProfilePhotoForm, SetPasswordForm

User = get_user_model()


def test_set_password_form_valid():
    form = SetPasswordForm(
        data={"new_password1": "testing123", "new_password2": "testing123"}
    )
    assert form.is_valid()


def test_set_password_form_mismatch():
    form = SetPasswordForm(data={"new_password1": "abc123", "new_password2": "xyz789"})
    assert not form.is_valid()
    assert "__all__" in form.errors
    assert "Passwords do not match" in form.errors["__all__"][0]


@pytest.mark.django_db
def test_biography_form_accepts_html(django_user_model):
    user = django_user_model.objects.create_user(
        username="tester",
        password="oldpass",
        membership_status="Full Member",  # ✅ Must be one of the items in DEFAULT_ACTIVE_STATUSES
        is_superuser=False,
    )
    form = BiographyForm(data={"content": "<p>Hello, world!</p>"})
    assert form.is_valid()
    instance = form.save(commit=False)
    instance.member = user
    instance.save()
    assert instance.content == "<p>Hello, world!</p>"
