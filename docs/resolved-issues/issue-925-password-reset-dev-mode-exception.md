# Issue #925: Fix Forgot-Password Delivery for OAuth-Only Users and Dev-Mode Exception

**Resolution Date**: May 22, 2026
**Branch**: `bugfix/issue-925-password-reset-dev-mode-exception`
**PR**: #926
**Status**: Complete ✅

## Problem

The forgot-password flow was not delivering reset emails in a real tenant scenario for an active member account.

Two behaviors combined into user-visible failure:

- Django's default password reset user selection excludes users with unusable passwords.
- In this project, many accounts begin OAuth-first and therefore have unusable local passwords until they explicitly set one.

Additionally, product policy for this project requires a special-case rule:

- Forgot-password emails must always go directly to the member requesting reset.
- General app emails should continue to honor `EMAIL_DEV_MODE` redirection during tenant construction/testing.

## Root Cause

### 1. Unusable-password accounts filtered out

Default `PasswordResetForm.get_users()` omits users where `has_usable_password()` is false. This blocked reset email generation for OAuth-first members.

### 2. Forgot-password email routing policy mismatch

During investigation, password-reset email sending was aligned with the dev-mode wrapper path. That behavior conflicts with the explicit requirement that password-reset is an exception to dev-mode redirection.

## Solution

### 1. Include active OAuth-first accounts in password reset eligibility

`DevModePasswordResetForm.get_users()` now returns active users matching the submitted email using case-insensitive Unicode-safe comparison, including those with unusable local passwords.

### 2. Bypass dev-mode redirection for forgot-password emails

Password reset email sending now uses `EmailMultiAlternatives` directly for this flow so recipient delivery is to the real member email address.

This keeps the policy boundary clear:

- Forgot-password: direct recipient delivery
- Other operational emails: continue using existing dev-mode redirection utilities

## Files Changed

- `members/forms.py`
- `members/views.py`
- `members/tests/test_password_reset.py`

## Validation

Executed focused tests:

- `pytest members/tests/test_password_reset.py -q`

Result:

- 5 passed

Coverage included:

- Reset email sends for active user with unusable password
- Forgot-password bypasses dev-mode recipient redirection
- Existing password reset behavior and canonical URL assertions

## Outcome

Tenant dev mode can remain enabled for construction/testing emails, while forgot-password now behaves as a user-account recovery path and delivers reset links to the actual member address as required.
