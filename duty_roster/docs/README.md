# Duty Roster App

[→ Duty Roster AppConfig (apps.py)](apps.md) | [→ Management Commands](management.md) | [→ Views](views.md)

## Database Schema

```mermaid
erDiagram
    Member ||--o{ MemberBlackout : blackouts
    Member ||--o{ DutyPreference : preferences  
    Member ||--o{ DutyAssignment : assignments
    Member ||--o{ InstructionSlot : instructor
    Member ||--o{ DutySwapRequest : requester
    Member ||--o{ DutySwapOffer : offerer
    Member ||--o{ OpsIntent : creator
    
    DutyDay {
        int id PK
        date duty_date
        string day_type
        boolean finalized
        text notes
    }
    
    DutySlot {
        int id PK
        int duty_day_id FK
        string role_type
        time start_time
        time end_time
        int min_members
        int max_members
        boolean required
        text description
    }
    
    MemberBlackout {
        int id PK
        int member_id FK
        date start_date
        date end_date
        text reason
        boolean approved
    }
    
    DutyPreference {
        int id PK
        int member_id FK
        string role_type
        int preference_level
        text notes
        boolean active
    }
    
    DutyAssignment {
        int id PK
        int duty_slot_id FK
        int member_id FK
        string assignment_status
        datetime assigned_at
        int assigned_by_id FK
        text notes
    }
    
    InstructionSlot {
        int id PK
        int duty_day_id FK
        int instructor_id FK
        time start_time
        time end_time
        int max_students
        boolean available
    }
    
    DutySwapRequest {
        int id PK
        int original_assignment_id FK
        int requester_id FK
        text reason
        string status
        datetime created_at
    }
    
    DutySwapOffer {
        int id PK
        int swap_request_id FK
        int offerer_id FK
        int offered_assignment_id FK
        string status
        datetime created_at
    }
    
    OpsIntent {
        int id PK
        date ops_date
        int creator_id FK
        string status
        text description
        datetime created_at
        boolean finalized
    }
    
    DutyDay ||--o{ DutySlot : contains
    DutyDay ||--o{ InstructionSlot : instruction_slots
    DutySlot ||--o{ DutyAssignment : assignments
    DutyAssignment ||--o{ DutySwapRequest : swap_requests
    DutySwapRequest ||--o{ DutySwapOffer : offers
```

The **Duty Roster** app manages scheduling and assignments for Duty Officers (DO), Assistant Duty Officers (ADO), and other operational roles. It integrates with members, logsheet, and notification systems to ensure smooth club operations.

- **Audience:** authenticated members (view), rostermeisters/admins (edit)
- **Route:** `/duty_roster/`
- **Nav:** included via the main navbar.

---

## Quick Start

1. Log in as a member or rostermeister.
2. Visit `/duty_roster/` to view your assignments or the full calendar.
3. Rostermeisters can generate, edit, or publish rosters via the admin or web interface.

---

## Pages & Permissions

- `duty_roster.views.duty_calendar` (all members, calendar view)
- `duty_roster.views.blackout_manage` (members, manage blackout dates)
- `duty_roster.views.propose_roster` (rostermeisters, propose/generate roster)
- `duty_roster.views.duty_list` (all members, list view)
- `duty_roster.views.duty_detail` (all members, assignment detail)

---

## URL Patterns

- `/duty_roster/` – calendar view
- `/duty_roster/blackout/` – manage blackout dates
- `/duty_roster/propose/` – propose/generate roster (rostermeister only)
- `/duty_roster/list/` – list of all assignments
- `/duty_roster/<pk>/` – assignment detail

---

## Core Models

- **DutyAssignment**: assignment of a member to a DO/ADO role on a specific date
- **BlackoutDate**: member-submitted unavailable dates
- **DutyRoster**: a published or draft roster for a period
- **DutyRole**: defines roles (DO, ADO, etc.)

---

## Implementation Notes

- **Templates:** `templates/duty_roster/` (calendar, list, blackout, propose)
- **Models:** `duty_roster/models.py` (see database schema above)
- **Admin:** all core models are editable via Django admin
- **Permissions:** only rostermeisters can generate or edit rosters; all can view
- **Roster Generation:** see `duty_roster/roster_generator.py` for logic

---

## See Also
- [AppConfig](apps.md)
- [Management Commands](management.md)
- [Views](views.md)
