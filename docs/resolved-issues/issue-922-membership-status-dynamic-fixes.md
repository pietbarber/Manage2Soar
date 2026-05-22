# Issue #922: Replace Remaining Hard-Coded Membership Status Logic

**Resolution Date**: May 21, 2026
**Branch**: `feature/issue-922-membership-status-dynamic-fixes`
**PR**: (to be created)
**Status**: Complete ✅

## Problem

Although membership statuses had already been made configurable in core data models, several runtime views and templates still used hard-coded status names such as `Full Member`, `Pending`, and `Inactive`.

For clubs that use custom status taxonomies, this created incorrect behavior and inconsistent UX:

- Member-only homepage routing could fail for valid active members with custom statuses.
- Member profile badges assumed specific status names.
- Duty delinquent detail UI text and highlighting implied `Full Member` as canonical.
- Members directory filter controls consumed too much vertical space on busy pages.
- Pylance reported diagnostics in migration `0022` for callable `choices` typing.

## Root Cause

The issue was not one single code path but a set of legacy assumptions spread across templates and view logic:

- Hard-coded list of allowed statuses in `cms.homepage`.
- Template branching by literal status strings in member profile pages.
- Duty delinquent template copy and conditional display tied to `Full Member`.
- Filter layout growth as status/role option sets became more dynamic.
- Type checker mismatch between Django runtime-accepted callable `choices` and Pylance stubs.

## Solution

### 1. CMS Homepage Status Routing

Updated homepage member/public selection logic to use the centralized dynamic helper:

- Replaced hard-coded list with `members.utils.is_active_member(user)`.
- This now follows active statuses configured in `siteconfig.MembershipStatus`.

### 2. Member Profile Status Badge Rendering

Updated `member_view` rendering behavior to be dynamic:

- Added `active_statuses` context from `get_active_membership_statuses()`.
- Replaced hard-coded status-name comparisons in template with membership-in-active-set checks.
- Retained clear visual distinction between active and non-active statuses.

### 3. Duty Delinquent Detail Template Cleanup

Removed `Full Member`-specific assumptions in duty delinquent detail UI:

- Summary text now references configured active statuses.
- Status label is always displayed directly from member data rather than conditionally hidden for `Full Member`.

### 4. Members Directory Filter UX Improvement

Refactored the members list filter panel:

- Converted combined "Filter by Status" and "Filter by Role" controls into a Bootstrap accordion section.
- Preserved all existing query parameter behavior and selected-state handling.

### 5. Migration Typing / Pylance Fix

Resolved Pylance diagnostics in migration `members/migrations/0022_alter_member_membership_status.py`:

- Used `typing.cast(Any, ...)` for callable `choices` in migration field definition.
- Preserved migration runtime semantics while satisfying static type analysis.

## Files Changed

- `cms/views.py`
- `cms/tests/test_cms.py`
- `members/models.py`
- `members/views.py`
- `members/templates/members/member_list.html`
- `members/templates/members/member_view.html`
- `members/tests/test_models.py`
- `members/tests/test_views.py`
- `duty_roster/templates/duty_roster/duty_delinquents_detail.html`
- `members/migrations/0022_alter_member_membership_status.py`

## Validation

Targeted validation was run after the fixes:

- `pytest cms/tests/test_cms.py -q`
- `pytest members/tests/test_models.py::MembershipStatusIntegrationTests -q`
- `pytest members/tests/test_views.py -q`
- `pytest members/tests/test_views.py -k member_list -q`
- `python manage.py check`

All completed successfully.

## Business Value

- Custom-club membership models now behave correctly across key user flows.
- Reduced risk of hidden access/visibility bugs tied to legacy status names.
- Improved maintainability by consolidating status semantics around configured active-status helpers.
- Cleaner members-directory UI for clubs with larger status/role sets.
- Keeps migration files editor-clean without changing database behavior.
