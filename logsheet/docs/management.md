
# Management Commands for logsheet

This page documents all custom Django management commands in `logsheet/management/commands/`.

---

## Legacy Database Reference

When importing historical data, the following legacy tables are used as sources:

### flight_info2
Tracks individual flight records in the legacy system.

| Column              | Type                    | Description                                 |
|---------------------|-------------------------|---------------------------------------------|
| flight_tracking_id  | integer (PK)            | Unique flight record ID                     |
| flight_date         | date                    | Date of flight                              |
| pilot               | varchar                 | Pilot name                                  |
| passenger           | varchar                 | Passenger name                              |
| glider              | varchar(20)             | Glider tail number or name                  |
| instructor          | varchar(20)             | Instructor name                             |
| towpilot            | varchar(20)             | Towpilot name                               |
| towplane            | varchar(20)             | Towplane tail number or name                |
| flight_type         | varchar(20)             | Type of flight (e.g., solo, dual, intro)    |
| takeoff_time        | time                    | Takeoff time                                |
| landing_time        | time                    | Landing time                                |
| flight_time         | time                    | Duration (may be redundant)                 |
| release_altitude    | integer                 | Release altitude (ft)                       |
| flight_cost         | money                   | Flight cost                                 |
| tow_cost            | money                   | Tow cost                                    |
| total_cost          | money                   | Total cost                                  |
| field               | varchar(4)              | Airfield code (default 'KFRR')              |

### ops_days
Tracks daily operations and duty assignments.

| Column      | Type           | Description                        |
|-------------|----------------|------------------------------------|
| flight_date | date           | Date of operation                  |
| dutyofficer | varchar(20)    | Duty officer name                  |
| instructor  | varchar(20)    | Instructor name                    |
| towpilot    | varchar(20)    | Towpilot name                      |
| assistant   | varchar(20)    | Assistant name                     |
| field       | varchar(4)     | Airfield code (default 'KFRR')     |
| am_towpilot | varchar(20)    | AM towpilot name                   |
| pm_towpilot | varchar(20)    | PM towpilot name                   |

### towplane_data
Tracks towplane usage and fuel for each ops day.

| Column            | Type           | Description                        |
|-------------------|----------------|------------------------------------|
| flight_date       | date           | Date of operation                  |
| towplane          | varchar(20)    | Towplane tail number or name       |
| start_tach        | real           | Starting tachometer reading        |
| stop_tach         | real           | Ending tachometer reading          |
| tach_time         | real           | Tach time for the day              |
| gas_added         | real           | Gallons of fuel added              |
| towpilot_comments | varchar        | Comments from towpilot             |
| tows              | integer        | Number of tows                     |
| field             | varchar(4)     | Airfield code (default 'KFRR')     |

---

---

## import_legacy_flights
- Imports legacy flight records into the current logsheet models.

## import_ops_days
- Imports historical operations days into the logsheet system.

## import_towplane_closeouts
- Imports towplane closeout records from legacy data.

## load_sample_logsheets
- Loads sample logsheet data for development/testing.

## tow_rate_import
- Imports or updates tow rates for aircraft.

## update_flight_costs
- Recalculates flight costs for all flights in the system.

---

## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Forms](forms.md)
- [Views](views.md)
- [Signals](signals.md)
