
# Models in logsheet/models.py

## Database Schema

```mermaid
erDiagram
    Member ||--o{ Flight : pilot
    Member ||--o{ Flight : instructor
    Member ||--o{ Flight : passenger
    Member ||--o{ Flight : tow_pilot
    Member ||--o{ Logsheet : created_by
    Member ||--o{ Logsheet : duty_officer
    Member ||--o{ Logsheet : assistant_duty_officer
    Member ||--o{ Logsheet : duty_instructor
    Member ||--o{ LogsheetPayment : paid_by
    Member ||--o{ MaintenanceIssue : reported_by
    Member ||--o{ AircraftMeister : member

    Logsheet {
        int id PK
        date log_date
        int airfield_id FK
        int created_by_id FK
        datetime created_at
        boolean finalized
        int duty_officer_id FK
        int assistant_duty_officer_id FK
        int duty_instructor_id FK
    }

    Flight {
        int id PK
        int logsheet_id FK
        time launch_time
        time landing_time
        int pilot_id FK
        int instructor_id FK
        int glider_id FK
        int tow_pilot_id FK
        int towplane_id FK
        duration duration
        int passenger_id FK
        string guest_pilot_name
        string guest_instructor_name
        string guest_towpilot_name
        string passenger_name
        int release_altitude
        decimal tow_cost_override
        decimal rental_cost_override
        text remarks
    }

    Glider {
        int id PK
        string registration
        string competition_id
        string manufacturer
        string model
        decimal rental_rate
        string status
        boolean available
        image photo
        text description
    }

    Towplane {
        int id PK
        string registration
        string manufacturer
        string model
        string status
        boolean available
        image photo
        text description
    }

    Airfield {
        int id PK
        string name
        string icao_code
        text description
        image photo
    }

    TowRate {
        int id PK
        int altitude
        decimal rate
        string aircraft_type
        boolean active
    }

    LogsheetPayment {
        int id PK
        int logsheet_id FK
        int paid_by_id FK
        decimal amount
        string payment_method
        text notes
    }

    LogsheetCloseout {
        int id PK
        int logsheet_id FK
        int total_flights
        decimal total_revenue
        text notes
        text safety_issues
        datetime created_at
    }

    TowplaneCloseout {
        int id PK
        int logsheet_id FK
        int towplane_id FK
        decimal tach_start
        decimal tach_end
        decimal fuel_added
        text notes
    }

    MaintenanceIssue {
        int id PK
        int aircraft_id
        int reported_by_id FK
        string aircraft_type
        string status
        string severity
        text description
        text resolution
        datetime reported_at
        datetime resolved_at
    }

    MaintenanceDeadline {
        int id PK
        int aircraft_id
        string aircraft_type
        string deadline_type
        date due_date
        int hours_remaining
        text description
        boolean active
    }

    AircraftMeister {
        int id PK
        int member_id FK
        string aircraft_type
        int aircraft_id
    }

    RevisionLog {
        int id PK
        string model_name
        int object_id
        string action
        text changes
        int user_id FK
        datetime timestamp
    }

    Logsheet ||--o{ Flight : contains
    Logsheet ||--o{ LogsheetPayment : payments
    Logsheet ||--o{ LogsheetCloseout : closeout
    Logsheet ||--o{ TowplaneCloseout : towplane_closeouts
    Airfield ||--o{ Logsheet : location
    Glider ||--o{ Flight : aircraft
    Towplane ||--o{ Flight : tow_aircraft
    Towplane ||--o{ TowplaneCloseout : closeout_data
    Glider ||--o{ MaintenanceIssue : maintenance
    Towplane ||--o{ MaintenanceIssue : maintenance
    Glider ||--o{ MaintenanceDeadline : deadlines
    Towplane ||--o{ MaintenanceDeadline : deadlines
    Glider ||--o{ AircraftMeister : maintained_by
    Towplane ||--o{ AircraftMeister : maintained_by
```

This document describes all models in `logsheet/models.py`.

---

## Flight
- Represents a single flight log entry, including pilots, aircraft, launch method, times, and costs.

## RevisionLog
- Tracks changes to logsheet entries for audit/history.

## Towplane
- Represents a towplane, including status and maintenance.
- **New in Issue 123**: Added `hourly_rental_rate` field to support charging for non-towing flights like sightseeing, flight reviews, and retrieval missions.

## Glider
- Represents a glider, including status and maintenance.

## Airfield
- Represents an airfield where operations occur.

## Logsheet
- Represents a daily logsheet, including flights, crew, and closeout.

## TowRate
- Defines tow rates for different aircraft and altitudes.

## LogsheetPayment
- Tracks payments for logsheet entries.

## LogsheetCloseout
- Records the closeout summary for a logsheet.

## TowplaneCloseout
- Records the closeout summary for a towplane.
- **New in Issue 123**: Includes `rental_hours_chargeable` field and `charged_to` field to track non-towing towplane usage (sightseeing, flight reviews, retrieval flights).
- **Rental Cost Calculation**: The `rental_cost` property automatically calculates charges based on `rental_hours_chargeable * towplane.hourly_rental_rate`.

## MaintenanceIssue
- Tracks maintenance issues for aircraft.

## MaintenanceDeadline
- Tracks maintenance deadlines for aircraft.

---

## Also See
- [README (App Overview)](README.md)
- [Forms](forms.md)
- [Views](views.md)
- [Signals](signals.md)
- [Management Commands](management.md)
