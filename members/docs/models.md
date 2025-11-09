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
        boolean instructor
        boolean towpilot
        boolean duty_officer
        boolean assistant_duty_officer
        boolean director
        boolean treasurer
        boolean secretary
        boolean webmaster
        boolean member_manager
        string legacy_username
        datetime date_joined
        int last_updated_by_id FK
        string pilot_certificate_number
        date private_glider_checkride_date
        string home_club
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
    }

    MemberBadge {
        int id PK
        int member_id FK
        int badge_id FK
        date date_awarded
        text notes
    }

    Member ||--o| Biography : has_biography
    Member ||--o{ MemberBadge : earned_badges
    Badge ||--o{ MemberBadge : awarded_to_members
    Member ||--o{ Member : last_updated_by
```

## Models

### `Biography`
- Stores member biographies, including rich text and upload path logic.
- Linked to `Member` via a foreign key.

### `Member`
- Extends Django's `AbstractUser`.
- Stores all member profile data, authentication info, and group/role logic.
- Methods for profile image, display name, group syncing, and status.
- Includes `home_club` field for visiting pilots from other soaring clubs.

See also: [Redaction of Personal Contact Information](redaction.md)

### `Badge`
- Represents a badge that can be earned by a member.
- Includes badge name, description, and image.

### `MemberBadge`
- Through model linking `Member` and `Badge`.
- Tracks which badges a member has earned and when.

## Also See
- [README.md](README.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [management.md](management.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
