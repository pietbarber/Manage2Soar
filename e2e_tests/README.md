# E2E and Integration Tests

This directory contains end-to-end (E2E) and integration tests for the Manage2Soar application.

## E2E Tests (`e2e/`)

Browser-based tests using Playwright to validate JavaScript functionality, user interactions, and dynamic content.

### Running E2E Tests

**CRITICAL**: E2E tests MUST be run sequentially (NOT in parallel):

```bash
# Correct - sequential execution
pytest e2e_tests/e2e/ -v

# Correct - explicitly disable parallel execution
pytest e2e_tests/e2e/ -n 0 -v

# INCORRECT - will cause race conditions
pytest e2e_tests/e2e/ -n auto  # ❌ DO NOT USE
```

### Why No Parallel Execution?

The `DjangoPlaywrightTestCase` base class sets the `DJANGO_ALLOW_ASYNC_UNSAFE` environment variable to allow Django ORM operations in Playwright's async context. This setting affects the **entire Python process**, not just individual test classes. Running tests in parallel would cause:

- Race conditions when setting/unsetting the environment variable
- Unintended side effects between test processes
- Unpredictable test failures

### Test Structure

- `conftest.py`: Playwright fixtures and `DjangoPlaywrightTestCase` base class
- `test_basic_setup.py`: Basic Playwright integration tests (homepage, login, Bootstrap JS)
- `test_tinymce.py`: TinyMCE editor tests (initialization, YouTube embedding, media dialog)

### Writing E2E Tests

Use `DjangoPlaywrightTestCase` as your base class:

```python
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase

class TestMyFeature(DjangoPlaywrightTestCase):
    def test_button_click(self):
        admin = self.create_test_member(username="test_admin", is_superuser=True)
        self.login(username="test_admin")

        self.page.goto(f"{self.live_server_url}/my-page/")
        self.page.click("#my-button")

        result = self.page.text_content("#result")
        assert "Expected" in result
```

### Best Practices

1. **Use smart waiting**: Prefer `wait_for_selector()`, `wait_for_function()`, or `wait_for(state="visible")` over `wait_for_timeout()`
2. **Unique usernames**: Create unique test users per test method to improve isolation
3. **Verify login**: The `login()` helper automatically verifies successful authentication
4. **Keep credentials consistent**: Ensure usernames and passwords used in tests match those created by your fixtures or helper methods

### Coverage

Run with coverage:

```bash
pytest e2e_tests/e2e/ --cov=. --cov-report=term-missing -v
```

## Issue References

- Issue #389: Playwright-pytest integration
- Issue #422: TinyMCE YouTube embedding bug (confirmed via xfail test)
