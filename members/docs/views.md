# Views in the Members App

This document describes the views defined in `members/views.py`, `members/views_applications.py`, and `members/views_safety_reports.py` and their purpose in the app.

## Member Management Views (`members/views.py`)

### `member_list`
- **Purpose:** Displays a paginated list of all members with filtering and search.
- **Template:** `members/member_list.html`
- **Access:** Public

### `member_view` / `member_detail`
- **Purpose:** Shows detailed profile information for a specific member.
- **Template:** `members/member_detail.html`
- **Access:** Public

### `biography_view`
- **Purpose:** Shows and allows editing of a member's biography.
- **Template:** `members/biography_view.html`
- **Access:** Public viewing, authenticated editing

### `home`
- **Purpose:** Member dashboard/homepage with personalized content.
- **Template:** `members/home.html`
- **Access:** Authenticated members only

### `set_password`
- **Purpose:** Custom password setting/resetting functionality.
- **Template:** `members/set_password.html`
- **Access:** Authenticated members only

### `tinymce_image_upload`
- **Purpose:** Handles image uploads for rich text fields in biographies.
- **Access:** Authenticated members only

### `badge_board`
- **Purpose:** Displays all badges and member achievements.
- **Template:** `members/badge_board.html`
- **Access:** Public

## Membership Application Views (`members/views_applications.py`)

### `membership_application`
- **Purpose:** Public membership application form for non-logged-in users (Issue #245).
- **Template:** `members/membership_application.html`
- **Access:** Public (anonymous users only)
- **Features:**
  - Comprehensive application form with international support
  - Foreign pilot validation and conditional field requirements
  - Dynamic JavaScript for country-specific address formatting
  - Form submission with email notifications to membership managers

### `membership_application_status`
- **Purpose:** Status page for submitted applications with withdrawal functionality.
- **Template:** `members/membership_application_status.html`
- **Access:** Public (via application_id UUID)
- **Features:**
  - Application status tracking and display
  - User-initiated withdrawal with comprehensive notifications
  - Status updates and review timeline

### `membership_applications_list`
- **Purpose:** Administrative list view of all membership applications.
- **Template:** `members/membership_applications_list.html`
- **Access:** Staff with member_manager permissions
- **Features:**
  - Paginated list with status filtering
  - Bulk actions and application management
  - Links to detailed review interface

### `membership_application_detail`
- **Purpose:** Administrative detailed view and review interface for applications.
- **Template:** `members/membership_application_detail.html`
- **Access:** Staff with member_manager permissions
- **Features:**
  - Complete application details display
  - Review actions (approve, reject, waitlist, withdraw)
  - Member account creation for approved applications
  - Administrative notes and status management

### `membership_waitlist`
- **Purpose:** Public view of current membership waitlist status.
- **Template:** `members/membership_waitlist.html`
- **Access:** Public
- **Features:**
  - Anonymous waitlist position display
  - General club membership information
  - No personal information exposed

## Also See

## Safety Officer Views (`members/views_safety_reports.py`)

### `safety_officer_dashboard`
- **Purpose:** Consolidated safety dashboard combining suggestion box reports and ops report safety sections (Issue #622).
- **Template:** `members/safety_reports/dashboard.html`
- **Access:** Safety officers (`safety_officer=True`) and superusers only
- **Features:**
  - Statistics cards for suggestion box reports (total, new, in progress, resolved)
  - Tabbed interface: Suggestion Box Reports + Ops Report Safety Sections
  - Ops safety sections pulled from `LogsheetCloseout.safety_issues` for the last 12 months
  - Automatic filtering of "nothing to report" entries (N/A, None, No issues, etc.)
  - Toggle to show/hide filtered entries
  - Independent pagination for both tabs
  - Links to full report detail pages

### `safety_report_list`
- **Purpose:** Paginated, filterable list of all safety suggestion box reports (Issue #585).
- **Template:** `members/safety_reports/list.html`
- **Access:** Safety officers and superusers only
- **Features:**
  - Filter by status (new, reviewed, in_progress, resolved, closed)
  - Sort by date, status, or observation date
  - Statistics dashboard cards
  - Pagination (20 per page)

### `safety_report_detail`
- **Purpose:** View and manage a single safety report with officer actions (Issue #585).
- **Template:** `members/safety_reports/detail.html`
- **Access:** Safety officers and superusers only
- **Features:**
  - Full report details display
  - Officer form for adding notes, updating status, recording actions taken
  - Automatic tracking of reviewer and review timestamp

## Also See
- [README.md](README.md)
- [models.md](models.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [management.md](management.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
