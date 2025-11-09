import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from members.models import Member
from members.views import visiting_pilot_signup
from siteconfig.forms import VisitingPilotSignupForm
from siteconfig.models import SiteConfiguration

User = get_user_model()


@pytest.fixture
def visiting_pilot_config():
    """Create a SiteConfiguration with visiting pilot enabled."""
    from siteconfig.models import MembershipStatus

    # Create an active "Affiliate Member" status for auto-approval testing
    affiliate_status, _ = MembershipStatus.objects.get_or_create(
        name="Affiliate Member", defaults={"is_active": True, "sort_order": 90}
    )
    affiliate_status.is_active = True  # Ensure it's active
    affiliate_status.save()

    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        domain_name="test.example.com",
        club_abbreviation="TSC",
        visiting_pilot_enabled=True,
        visiting_pilot_status="Affiliate Member",
        visiting_pilot_welcome_text="Welcome to our club!",
        visiting_pilot_require_ssa=False,
        visiting_pilot_require_rating=False,
        visiting_pilot_auto_approve=True,
    )


@pytest.fixture
def visiting_pilot_config_strict():
    """Create a SiteConfiguration with strict visiting pilot requirements."""
    from siteconfig.models import MembershipStatus

    # Create an inactive "Affiliate Member" status for manual approval testing
    affiliate_status, _ = MembershipStatus.objects.get_or_create(
        name="Affiliate Member", defaults={"is_active": False, "sort_order": 90}
    )
    affiliate_status.is_active = False  # Ensure it's inactive
    affiliate_status.save()

    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        domain_name="test.example.com",
        club_abbreviation="TSC",
        visiting_pilot_enabled=True,
        visiting_pilot_status="Affiliate Member",
        visiting_pilot_welcome_text="Welcome to our club!",
        visiting_pilot_require_ssa=True,
        visiting_pilot_require_rating=True,
        visiting_pilot_auto_approve=False,
    )


@pytest.mark.django_db
def test_visiting_pilot_form_valid_basic(visiting_pilot_config):
    """Test valid visiting pilot form with minimal required fields."""
    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
    }
    form = VisitingPilotSignupForm(form_data)
    assert form.is_valid()


@pytest.mark.django_db
def test_visiting_pilot_form_valid_complete(visiting_pilot_config_strict):
    """Test valid visiting pilot form with all fields."""
    form_data = {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.smith@example.com",
        "phone": "555-123-4567",
        "ssa_member_number": "12345",
        "glider_rating": "private",
        "home_club": "Another Soaring Club",
    }
    form = VisitingPilotSignupForm(form_data)
    assert form.is_valid()


@pytest.mark.django_db
def test_visiting_pilot_form_requires_fields_when_configured(
    visiting_pilot_config_strict,
):
    """Test that form validates required SSA and rating when configured."""
    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        # Missing SSA number and rating
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "SSA membership number is required" in str(form.errors)
    assert "Glider rating is required" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_form_duplicate_email():
    """Test that form rejects duplicate email addresses."""
    # Create existing member
    Member.objects.create_user(
        username="existing@example.com",
        email="existing@example.com",
        first_name="Existing",
        last_name="Member",
    )

    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "existing@example.com",
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "email address is already registered" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_form_duplicate_ssa_number(visiting_pilot_config):
    """Test that form rejects duplicate SSA numbers."""
    # Create existing member with SSA number
    Member.objects.create_user(
        username="existing@example.com",
        email="existing@example.com",
        first_name="Existing",
        last_name="Member",
        SSA_member_number="12345",
    )

    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "ssa_member_number": "12345",
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert (
        "You appear to already be registered as Existing Member with SSA #12345"
        in str(form.errors)
    )


@pytest.mark.django_db
def test_visiting_pilot_form_invalid_ssa_number():
    """Test that form validates SSA number format."""
    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "ssa_member_number": "abc123",  # Invalid - contains letters
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "should contain only numbers" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_config_disabled():
    """Test that form validation fails when signup is disabled."""
    # Create config with visiting pilot disabled
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        visiting_pilot_enabled=False,
    )

    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "registration is currently disabled" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_member_creation_direct(visiting_pilot_config):
    """Test direct member creation with visiting pilot form data."""
    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "phone": "555-123-4567",
        "home_club": "Remote Soaring Club",
    }
    form = VisitingPilotSignupForm(form_data)
    assert form.is_valid()

    # Create member with form data
    member = Member.objects.create_user(
        username=form.cleaned_data["email"],
        email=form.cleaned_data["email"],
        first_name=form.cleaned_data["first_name"],
        last_name=form.cleaned_data["last_name"],
        phone=form.cleaned_data.get("phone", ""),
        home_club=form.cleaned_data.get("home_club", ""),
        membership_status=visiting_pilot_config.visiting_pilot_status,
    )
    member.is_active = visiting_pilot_config.visiting_pilot_auto_approve
    member.save()

    assert member.first_name == "John"
    assert member.last_name == "Doe"
    assert member.phone == "555-123-4567"
    assert member.home_club == "Remote Soaring Club"
    assert member.membership_status == "Affiliate Member"
    assert member.is_active is True  # Auto-approved
    assert member.username == "john.doe@example.com"


@pytest.mark.django_db
def test_visiting_pilot_member_creation_manual_approval(visiting_pilot_config_strict):
    """Test member creation with manual approval configured."""
    form_data = {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.smith@example.com",
        "ssa_member_number": "54321",
        "glider_rating": "commercial",
    }
    form = VisitingPilotSignupForm(form_data)
    assert form.is_valid()

    # Create member with form data
    member = Member.objects.create_user(
        username=form.cleaned_data["email"],
        email=form.cleaned_data["email"],
        first_name=form.cleaned_data["first_name"],
        last_name=form.cleaned_data["last_name"],
        SSA_member_number=form.cleaned_data.get("ssa_member_number", ""),
        glider_rating=form.cleaned_data.get("glider_rating", ""),
        membership_status=visiting_pilot_config_strict.visiting_pilot_status,
    )

    # Since we configured "Affiliate Member" as inactive, member should not be active
    # (overridden by the Member.save() method based on membership status)
    assert member.is_active is False  # Inactive because "Affiliate Member" is inactive
    assert member.membership_status == "Affiliate Member"
    assert member.SSA_member_number == "54321"
    assert member.glider_rating == "commercial"


@pytest.mark.django_db
def test_visiting_pilot_form_disabled_when_not_configured():
    """Test that form validates against disabled service."""
    # No SiteConfiguration exists
    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "registration is currently disabled" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_form_rejects_zero_ssa_number(visiting_pilot_config):
    """Test that form rejects '0' as SSA number."""
    form_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "ssa_member_number": "0",
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "cannot be" in str(form.errors)
    assert "0" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_form_detects_duplicate_by_name_and_ssa(visiting_pilot_config):
    """Test that form detects duplicate member by name and SSA number."""
    # Create existing member
    Member.objects.create_user(
        username="existing@example.com",
        email="existing@example.com",
        first_name="Jane",
        last_name="Smith",
        SSA_member_number="12345",
    )

    # Try to register same person
    form_data = {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.new@example.com",  # Different email
        "ssa_member_number": "12345",  # Same SSA number
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "appear to already be registered as Jane Smith" in str(form.errors)
    assert "12345" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_form_allows_same_name_different_ssa(visiting_pilot_config):
    """Test that form allows same name with different SSA numbers (different people)."""
    # Create existing member
    Member.objects.create_user(
        username="existing@example.com",
        email="existing@example.com",
        first_name="John",
        last_name="Smith",
        SSA_member_number="11111",
    )

    # Try to register different person with same name
    form_data = {
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.different@example.com",
        "ssa_member_number": "22222",  # Different SSA number
    }
    form = VisitingPilotSignupForm(form_data)
    assert form.is_valid()  # Should be allowed - different people


@pytest.mark.django_db
def test_visiting_pilot_form_warns_about_same_name_no_ssa(visiting_pilot_config):
    """Test that form warns when names match but SSA numbers are missing."""
    # Create existing member without SSA number
    Member.objects.create_user(
        username="existing@example.com",
        email="existing@example.com",
        first_name="Bob",
        last_name="Johnson",
        # No SSA number
    )

    # Try to register same name without SSA number
    form_data = {
        "first_name": "Bob",
        "last_name": "Johnson",
        "email": "bob.new@example.com",
        # No SSA number
    }
    form = VisitingPilotSignupForm(form_data)
    assert not form.is_valid()
    assert "Bob Johnson is already registered" in str(form.errors)
    assert "provide your SSA member number" in str(form.errors)


@pytest.mark.django_db
def test_visiting_pilot_signup_logic_for_authenticated_users(visiting_pilot_config):
    """Test the view logic for authenticated users using RequestFactory."""

    # Create a test user
    user = Member.objects.create_user(
        username="testmember@example.com",
        email="testmember@example.com",
        first_name="Test",
        last_name="Member",
    )

    # Use RequestFactory to create request with authenticated user
    factory = RequestFactory()
    # Generate daily token for testing
    token = visiting_pilot_config.get_or_create_daily_token()
    request = factory.get(reverse("members:visiting_pilot_signup", args=[token]))
    request.user = user  # Manually set authenticated user

    # Test the view directly
    response = visiting_pilot_signup(request, token)

    # Should show the member redirect page (status 200)
    assert response.status_code == 200

    # Should contain member-specific content
    assert b"Already a Club Member" in response.content
    assert b"already logged in as a club member" in response.content


@pytest.mark.django_db
def test_visiting_pilot_security_token_validation(visiting_pilot_config):
    """Test that invalid tokens are rejected with 404."""
    from django.http import Http404

    factory = RequestFactory()

    # Test with invalid token should raise Http404
    with pytest.raises(Http404):
        request = factory.get("/members/visiting-pilot/signup/INVALID/")
        visiting_pilot_signup(request, "INVALID")

    # Test with valid token should work
    # Generate a daily token first
    token = visiting_pilot_config.get_or_create_daily_token()
    request = factory.get(f"/members/visiting-pilot/signup/{token}/")
    from django.contrib.auth.models import AnonymousUser

    request.user = AnonymousUser()  # Simulate anonymous user
    response = visiting_pilot_signup(request, token)
    assert response.status_code == 200

    # Test token generation
    assert token is not None
    assert len(token) == 12

    # Test token regeneration
    old_token = visiting_pilot_config.visiting_pilot_token
    new_token = visiting_pilot_config.refresh_visiting_pilot_token()
    assert new_token != old_token
    assert len(new_token) == 12
