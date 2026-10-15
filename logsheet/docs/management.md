
# Management Commands for logsheet

This page documents all custom Django management commands in `logsheet/management/commands/`.

---

## seed_sample_data

Seeds realistic **sample data into the LOCAL dev database** (members, fleet, and
three seasons of flights) for testing and demo purposes.

```bash
# DRY RUN — prints what it would do, writes nothing (safe to run anywhere):
python manage.py seed_sample_data

# Actually seed the database:
python manage.py seed_sample_data --run                  # wipe previously-seeded data, then regenerate
python manage.py seed_sample_data --run --skip-wipe      # append instead of clearing
python manage.py seed_sample_data --run --members-only   # members + fleet only (no flights)
python manage.py seed_sample_data --run --seed 42        # fixed RNG seed (reproducible flights)
```

### What it creates
- **24 members** (22 men / 2 women) in Northern Virginia: 4 instructors (commercial),
  6 tow pilots (commercial), 7 students, 7 private-rated pilots, and 1 member manager
  (private-rated). All use `firstname.lastname@email.invalid` emails, 703/571 phones,
  and the shared dev password **`SoarDev-2026!`**.
- **Fleet**: 2× SGS 2-33 trainers ($40.00/hr), 1× SGS 1-26 ($25.00/hr),
  2 tow planes (Pawnee + SuperCub), and 3 privately-owned gliders (no rental rate).
- **Aero tow charge schemes** on both tow planes: $25.00 hookup, $0.00 for 0–1000 ft,
  $1.00 per 100 ft for 1000–5000 ft.
- **Three seasons** (2024, 2025, 2026→Oct) of weekend, April–November flights honoring
  the club's patterns: training duals, student solos, rated flights, SGS 1-26
  (private-pilots-only), and long private XC soars (after 12:30, ~3 h, 3000 ft).
  A student pilot may solo only after logging **40 duals**; student-solo slots
  rolled before any student reaches that threshold become extra training duals.

### Safety (defense in depth)
- **Dry-run by default**: without `--run` the command only prints what it would
  do and exits — it writes nothing. You must explicitly pass `--run` to modify
  the database, so a casual `python manage.py seed_sample_data` is harmless.
- **Localhost guard**: even with `--run`, it refuses to proceed unless the
  default DB host is `localhost`/`127.0.0.1` (or `--i-meant-it` is passed), so
  it cannot touch production by accident.
- **Idempotent**: by default it clears previously-seeded sample data (identified by
  `@email.invalid` members and the fixed sample N-numbers) before regenerating.
- Runs inside a single transaction and leaves all flights **unfinalized**, so no
  billing, maintenance, or email side effects are produced.

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
