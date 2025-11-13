# CMS App Testing Guide

This document covers testing patterns and pytest usage for the CMS app, with focus on the role-based access control system (Issue #239).

## Test Structure

The CMS app includes comprehensive test coverage with 42 test cases covering:

### Core Test Categories

1. **Model Tests**: Database constraints, validation, and business logic
2. **Access Control Tests**: Role-based permission verification
3. **View Tests**: HTTP responses, authentication, and authorization
4. **Admin Tests**: Django admin interface functionality
5. **Form Tests**: Input validation and security
6. **Integration Tests**: End-to-end workflows

## Role-Based Access Control Tests (Issue #239)

### Model Tests (`PageRolePermissionModelTests`)

```python
# Test creating role permissions
def test_create_role_permission(self):
    """Test creating a PageRolePermission with valid data."""

# Test role choices validation  
def test_role_choices(self):
    """Test that role_name field accepts valid choices."""

# Test unique constraints
def test_unique_constraint(self):
    """Test that duplicate role permissions are prevented."""
```

**Key Testing Patterns:**
- **Constraint Validation**: Ensure unique_together constraints work
- **Choice Field Validation**: Verify only valid roles are accepted
- **String Representations**: Test `__str__` methods for admin display

### Access Control Tests (`PageAccessControlTests`)

```python
# Test public page access (always allowed)
def test_public_page_access(self):
    """Test that public pages are accessible to all users."""

# Test member-only access
def test_private_page_no_roles_access(self):
    """Test private pages without role restrictions allow active members."""

# Test role-restricted access
def test_role_restricted_page_access(self):
    """Test that role-restricted pages enforce role requirements."""

# Test multiple role access (OR logic)
def test_multiple_role_access(self):
    """Test that users with ANY required role gain access."""

# Test validation (public + roles = invalid)
def test_page_validation_public_with_roles(self):
    """Test that public pages cannot have role restrictions."""
```

**Key Testing Patterns:**
- **Permission Matrix**: Test all combinations of user types vs access levels
- **OR Logic Verification**: Ensure users with ANY role (not ALL) gain access
- **Edge Cases**: Anonymous users, inactive members, role transitions
- **Validation Logic**: Test model clean() methods and constraints

### View Tests (`CMSRoleBasedViewTests`)

```python
# Test view-level access control
def test_role_restricted_page_allows_authorized_roles(self):
    """Test that views enforce role-based access control."""

def test_role_restricted_page_denies_regular_members(self):
    """Test that views deny access to members without required roles."""

# Test page filtering in index views
def test_cms_index_filters_inaccessible_pages(self):
    """Test that CMS index only shows accessible pages."""
```

**Key Testing Patterns:**
- **HTTP Status Codes**: 200 (allowed), 302 (redirect to login), 404 (hidden)
- **Content Filtering**: Verify restricted content doesn't appear in listings
- **Redirect Behavior**: Test login redirects for unauthorized access

## Test Data Setup Patterns

### User Creation with Roles

```python
def create_user_with_role(self, username, role_name, **kwargs):
    """Helper to create users with specific roles for testing."""
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        membership_status="Full Member",
        **kwargs
    )
    # Set the specific role boolean field
    setattr(user, role_name, True)
    user.save()
    return user

def test_director_access(self):
    director = self.create_user_with_role("director1", "director")
    # Test director-only page access...
```

### Page Creation with Role Restrictions

```python
def create_restricted_page(self, title, roles=None):
    """Helper to create pages with role restrictions."""
    page = Page.objects.create(
        title=title,
        slug=title.lower().replace(" ", "-"),
        content=f"Content for {title}",
        is_public=False
    )

    if roles:
        for role in roles:
            PageRolePermission.objects.create(
                page=page,
                role_name=role
            )

    return page
```

### Test Fixtures and Data

```python
@classmethod
def setUpTestData(cls):
    """Set up test data for the entire test class."""
    # Create standard test users
    cls.anonymous_user = AnonymousUser()
    cls.regular_member = cls.create_user_with_role("member", None)
    cls.director = cls.create_user_with_role("director", "director")
    cls.treasurer = cls.create_user_with_role("treasurer", "treasurer")

    # Create test pages
    cls.public_page = Page.objects.create(...)
    cls.member_page = Page.objects.create(is_public=False)
    cls.director_only_page = cls.create_restricted_page(
        "Director Resources", ["director"]
    )
```

## Running Tests

### All CMS Tests
```bash
# Run all CMS tests with coverage
pytest cms/tests.py --cov=cms --cov-report=html

# Run with verbose output
pytest cms/tests.py -v

# Run specific test classes
pytest cms/tests.py::PageRolePermissionModelTests -v
pytest cms/tests.py::PageAccessControlTests -v
pytest cms/tests.py::CMSRoleBasedViewTests -v
```

### Role-Based Access Control Tests Only
```bash
# Run only the role-based access control tests
pytest cms/tests.py -k "RolePermission or AccessControl or RoleBased" -v

# Run specific test methods
pytest cms/tests.py::PageAccessControlTests::test_role_restricted_page_access -v
```

### Test Coverage Analysis
```bash
# Generate detailed coverage report
pytest cms/tests.py --cov=cms --cov-report=html --cov-report=term-missing

# Check coverage for specific modules
pytest cms/tests.py --cov=cms.models --cov=cms.views --cov-report=term
```

## Test Configuration

### pytest.ini Settings
```ini
[tool:pytest]
DJANGO_SETTINGS_MODULE = manage2soar.settings
python_files = tests.py test_*.py *_tests.py
addopts = --tb=short --strict-markers
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    access_control: marks tests related to role-based access control
```

### Custom Test Markers
```python
import pytest

@pytest.mark.access_control
class PageAccessControlTests(TestCase):
    """Tests for role-based access control functionality."""

@pytest.mark.integration  
def test_complete_role_workflow(self):
    """End-to-end test of role assignment and access."""
```

## Testing Anti-Patterns to Avoid

### ❌ Don't Test Django Framework Code
```python
# Don't test Django's ORM functionality
def test_page_save(self):  # BAD
    page = Page(title="Test")
    page.save()
    assert Page.objects.count() == 1  # Testing Django, not our code
```

### ❌ Don't Use Complex Test Data Factories
```python
# Keep test data simple and focused
def test_access_control(self):  # GOOD
    user = User.objects.create_user("test", membership_status="Full Member")
    user.director = True
    user.save()
    # Test specific behavior...
```

### ❌ Don't Test Implementation Details
```python
# Test behavior, not implementation
def test_can_user_access_calls_correct_methods(self):  # BAD
    # Testing internal method calls instead of behavior

def test_director_can_access_restricted_page(self):  # GOOD  
    # Testing the actual business requirement
```

## Best Practices

### ✅ Use Descriptive Test Names
```python
def test_director_can_access_board_meeting_minutes(self):
def test_regular_member_cannot_access_financial_reports(self):
def test_multiple_roles_grant_access_with_or_logic(self):
```

### ✅ Test Edge Cases
```python
def test_inactive_member_with_director_role_denied_access(self):
def test_page_with_no_role_restrictions_allows_all_active_members(self):
def test_anonymous_user_redirected_to_login_for_private_pages(self):
```

### ✅ Use setUp Methods for Common Data
```python
def setUp(self):
    """Set up test data that varies between test methods."""
    self.client = Client()
    self.page = Page.objects.create(...)
```

### ✅ Test Both Positive and Negative Cases
```python
def test_authorized_user_gets_200_status(self):
    # Test successful access

def test_unauthorized_user_gets_302_redirect(self):
    # Test denied access
```

## Debugging Test Failures

### Common Issues and Solutions

**Role Permission Not Working:**
```python
# Check user has membership_status AND role boolean
user.membership_status = "Full Member"  # Required for active member check
user.director = True                    # Required for role check
user.save()
```

**Access Control Logic:**
```python
# Remember: it's OR logic, not AND logic
# User needs ANY of the required roles, not ALL roles
roles = ["director", "treasurer"]  # User needs director OR treasurer
```

**Test Database State:**
```python
# Use setUpTestData for immutable data, setUp for mutable data
@classmethod
def setUpTestData(cls):
    # Data that won't change during tests

def setUp(self):
    # Data that might be modified by individual tests
```

## Integration with Continuous Integration

### GitHub Actions Integration
```yaml
- name: Run CMS Tests
  run: |
    source .venv/bin/activate
    pytest cms/tests.py --cov=cms --cov-fail-under=90

- name: Test Role-Based Access Control
  run: |
    source .venv/bin/activate  
    pytest cms/tests.py -k "RolePermission or AccessControl" -v
```

This testing approach ensures robust coverage of the role-based access control system while maintaining fast, reliable test execution.
