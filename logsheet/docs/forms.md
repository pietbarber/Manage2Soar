# Forms in logsheet/forms.py

This document describes all forms in `logsheet/forms.py`.

---

## FlightForm
- ModelForm for entering and validating flight log entries.

## CreateLogsheetForm
- ModelForm for creating a new daily logsheet.

## LogsheetCloseoutForm
- ModelForm for closing out a logsheet.

## LogsheetDutyCrewForm
- ModelForm for entering duty crew assignments.
- **Bootstrap5 Styling**: All dropdown fields use `form-select` class for modern appearance
- **Conditional Validation**: Duty officer optional for rental-only days (no flights)
- **Role-based Filtering**: Member querysets filtered by appropriate roles

## TowplaneCloseoutForm
- ModelForm for closing out a towplane.
- **Conditional Fields**: Rental fields only appear when `allow_towplane_rental` is enabled
- **Clean UI**: Towplane selector hidden in closeout edit context (shown in card header)
- **Member Filtering**: Rental charge assignment limited to active members

## MaintenanceIssueForm
- ModelForm for reporting maintenance issues.

---

## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Views](views.md)
- [Signals](signals.md)
- [Management Commands](management.md)
