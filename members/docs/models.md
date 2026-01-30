# Members App Models

This document describes the models in the `members` app and their relationships. See the database schema below for a visual overview.

## Database Schema

```mermaid
erDiagram
    Member {
        int id PK
        string username UK
        string email
        string first_name
        string last_name
        string middle_initial
        string name_suffix
        string nickname
        string phone
        string mobile_phone
        string emergency_contact
        string address
        string city
        string state_code
        string zip_code
        string country
        string membership_status
        string SSA_member_number
        string glider_rating
        text public_notes
        text private_notes
        image profile_photo
        image profile_photo_medium
        image profile_photo_small
        boolean instructor
        boolean towpilot
        boolean duty_officer
        boolean assistant_duty_officer
        boolean director
        boolean treasurer
        boolean secretary
        boolean webmaster
        boolean member_manager
        boolean rostermeister
        boolean safety_officer
        string legacy_username
        datetime date_joined
        int last_updated_by_id FK
        string pilot_certificate_number
        date private_glider_checkride_date
        string home_club
    }

    MembershipApplication {
        int id PK
        uuid application_id UK
        string status
        datetime submitted_at
        datetime last_updated
        int reviewed_by_id FK
        datetime reviewed_at
        string first_name
        string middle_initial
        string last_name
        string name_suffix
        string email
        string phone
        string mobile_phone
        string address_line1
        string address_line2
        string city
        string state
        string zip_code
        string country
        string emergency_contact_name
        string emergency_contact_relationship
        string emergency_contact_phone
        string pilot_certificate_number
        boolean has_private_pilot
        boolean has_commercial_pilot
        boolean has_cfi
        string glider_rating
        int total_flight_hours
        int glider_flight_hours
        int recent_flight_hours
        string ssa_member_number
        text previous_club_memberships
        boolean previous_member_at_this_club
        text previous_membership_details
        boolean insurance_rejection_history
        text insurance_rejection_details
        boolean club_rejection_history
        text club_rejection_details
        boolean aviation_incidents
        text aviation_incident_details
        text soaring_goals
        text availability
        boolean agrees_to_terms
        boolean agrees_to_safety_rules
        boolean agrees_to_financial_obligations
        text additional_comments
        text admin_notes
        int waitlist_position
        int member_account_id FK
    }

    Biography {
        int id PK
        int member_id FK
        text content
        image uploaded_image
        datetime updated_at
    }

    Badge {
        int id PK
        string name UK
        image image
        text description
        int order
        int parent_badge_id FK "nullable - for legs"
    }

    MemberBadge {
        int id PK
        int member_id FK
        int badge_id FK
        date date_awarded
        text notes
    }

    Badge ||--o{ Badge : parent_badge
    Member ||--o| Biography : has_biography
    Member ||--o{ MemberBadge : earned_badges
    Badge ||--o{ MemberBadge : awarded_to_members
    Member ||--o{ Member : last_updated_by
    Member ||--o| MembershipApplication : created_from_application
    Member ||--o{ MembershipApplication : reviewed_applications
    Member ||--o{ SafetyReport : submitted_reports
    Member ||--o{ SafetyReport : reviewed_by

    SafetyReport {
        int id PK
        int reporter_id FK "nullable for anonymous"
        boolean is_anonymous
        text observation
        date observation_date
        string location
        string status "new/reviewed/in_progress/resolved/closed"
        int reviewed_by_id FK
        datetime reviewed_at
        text officer_notes
        text actions_taken
        datetime created_at
        datetime updated_at
    }
```

## Models

### `Member`
- Extends Django's `AbstractUser`.
- Stores all member profile data, authentication info, and group/role logic.
- Methods for profile image, display name, group syncing, and status.
- Includes `home_club` field for visiting pilots from other soaring clubs.
- Can be linked to a `MembershipApplication` that created the account.
- **Performance Optimization (Issue #285)**: Added database indexes on `membership_status` and `(last_name, first_name)` for faster filtering and sorting in logsheet operations.
- **Photo Thumbnails (Issue #286)**: Added `profile_photo_medium` (200x200) and `profile_photo_small` (64x64) fields for optimized page loading. Thumbnails are auto-generated when photos are uploaded via admin. URL properties (`profile_image_url_medium`, `profile_image_url_small`) provide graceful fallback chains.

See also: [Redaction of Personal Contact Information](redaction.md)

### `MembershipApplication`
- Stores membership applications from non-logged-in users (Issue #245).
- Comprehensive application form with personal info, aviation experience, and club history.
- Status tracking: pending, under review, waitlisted, approved, rejected, withdrawn.
- Links to `Member` account upon approval via `member_account` field.
- Includes waitlist management with position tracking.
- Administrative notes and review tracking for membership managers.

### `Biography`
- Stores member biographies, including rich text and upload path logic.
- Linked to `Member` via a foreign key.

### `Badge`
- Represents a badge that can be earned by a member.
- Includes badge name, description, and image.
- **Leg Support (Issue #560)**: Optional `parent_badge` FK allows badges to be designated as "legs" of a parent badge.
  - Example: "Silver Duration" is a leg of "FAI Silver Badge"
  - On the badge board, legs are suppressed for members who have already earned the parent badge.
  - This prevents showing redundant leg achievements when the full badge has been earned.

### `MemberBadge`
- Through model linking `Member` and `Badge`.
- Tracks which badges a member has earned and when.

### `SafetyReport`
- Stores safety observations, suggestions, and near-miss reports from members.
- Supports fully anonymous submissions: when `is_anonymous=True`, the `reporter` field is intentionally left null to honor anonymity.
- Reports go through a status workflow: new → reviewed → in_progress → resolved → closed.
- Safety officers (members with `safety_officer=True`) can review reports, add notes, and track actions taken.
- Linked to `Member` via optional `reporter` FK (null for anonymous) and `reviewed_by` FK.
- Uses TinyMCE HTMLField for rich text observations and officer notes.

## Also See
- [README.md](README.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [management.md](management.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
