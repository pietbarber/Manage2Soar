
# Models in logsheet/models.py

![Logsheet ERD](logsheet.png)

This document describes all models in `logsheet/models.py`.

---

## Flight
- Represents a single flight log entry, including pilots, aircraft, launch method, times, and costs.

## RevisionLog
- Tracks changes to logsheet entries for audit/history.

## Towplane
- Represents a towplane, including status and maintenance.

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
