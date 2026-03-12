# Issue #746 - Resources Drawer and Navbar Information Architecture

## Status
- Complete
- Date: 2026-03-10
- Branch: feature/issue-746-resources-navbar

## Summary
Issue #746 redesigned navbar information architecture to keep high-value links discoverable while reducing top-level clutter.

The implementation introduced webmaster-controlled CMS promotion metadata, a new top-level Resources drawer, and a simplified anonymous navbar. Navigation links previously scattered across Members, Equipment, Safety, and footer content are consolidated into Resources with role-aware visibility.

## Key Changes

### 1) CMS promotion model and admin controls
- Added page fields for navbar promotion in `cms.Page`:
  - `promote_to_navbar`
  - `navbar_title`
  - `navbar_rank` (1..100)
- Added validation requiring rank when promotion is enabled.
- Added helper to resolve effective navbar title with fallback to page title.
- Updated CMS admin to expose promotion fields and restrict edits to webmasters/superusers.

### 2) Resources drawer composition
- Added `resources_nav_items` composition in `cms/context_processors.py`.
- Included deterministic ordering with rank + title fallback sorting.
- Added fixed `Document Root` entry.
- Included promoted CMS pages using existing page access controls.
- Moved utility links into Resources with role-aware visibility:
  - Gliders and Towplanes
  - Report Website Issue
  - Safety Suggestion Box
  - Safety Dashboard
  - Suggestion Box Reports
  - Webcam (feature-config + active member)

### 3) Footer link consolidation
- Extracted anchor links from member footer CMS content and merged them into Resources.
- Added URL-level deduplication to avoid duplicates (for example feedback/report issue).
- Removed duplicated hardcoded footer navigation link now represented in Resources.

### 4) Navbar template refactor
- Added top-level Resources drawer.
- Removed duplicate/legacy placements now covered by Resources.
- Moved Admin Interface and Logout under user dropdown.
- Removed "Welcome" prefix from user dropdown text.
- Implemented simplified anonymous navbar with:
  - Duty Roster
  - Training Syllabus
  - Contact Us
  - Membership Application
  - Resources
  - Login

## Testing

### Django tests
- Added/updated targeted coverage in:
  - `cms/tests/test_navbar_promotion.py`
  - `cms/tests/test_context_processors.py`
  - `cms/tests/test_navbar_resources.py`
- Coverage includes:
  - Promotion validation and admin field restrictions
  - Public vs private resource visibility
  - Footer link ingestion and deduplication
  - Simplified anonymous navbar behavior

### E2E tests
- Added `e2e_tests/e2e/test_navbar_resources_drawer.py` for guest/member navbar behavior in mobile offcanvas flow.
- Updated `e2e_tests/e2e/test_user_dropdown.py` to match the new user-label behavior.

## Notes
- The Resources drawer intentionally serves as a single discovery surface for high-value content.
- Role-gating behavior follows existing project permission helpers, reducing risk of permission drift.
- Existing CMS access control remains source-of-truth for promoted page visibility.
