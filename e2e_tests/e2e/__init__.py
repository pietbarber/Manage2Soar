"""
End-to-end tests using Playwright for JavaScript/browser testing.

This package contains integration tests that run in a real browser,
validating JavaScript functionality, Bootstrap interactions, and
TinyMCE editor behavior.

Issue #389: Setting up Playwright-pytest for automated browser tests.

IMPORTANT: E2E tests MUST NOT be run in parallel due to DJANGO_ALLOW_ASYNC_UNSAFE
environment variable affecting the entire Python process. Use:
    pytest e2e_tests/ -n 0    # Explicitly disable parallel execution
    pytest e2e_tests/         # Or omit -n flag (defaults to sequential)
"""
