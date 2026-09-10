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

## LogsheetTowplaneForm and LogsheetTowplaneFormSet
- `LogsheetTowplaneForm` edits the day-level roster fields: `towplane`, `tow_pilot`, and `start_tach`.
- New-row towplane choices include active, non-virtual towplanes; an existing inactive non-virtual towplane remains selectable during closeout edits.
- New-row tow-pilot choices include active members with the `towpilot` role; an existing assigned pilot remains selectable during closeout edits even if no longer active.
- `LogsheetTowplaneFormSet` supports one extra row and deletion, and rejects duplicate towplane selections before persistence.
- Create-logsheet rows use the formset to assign each plane's pilot and starting tach; closeout rows use it to adjust the day-level pilot roster.

## MaintenanceIssueForm
- ModelForm for reporting maintenance issues.

## MemberChargeForm
- ModelForm for adding miscellaneous member charges during logsheet management (Issue #615).
- **Fields**: member, chargeable_item, quantity, notes
- **Member Dropdown**: Groups members by active/inactive status with optgroup labels
- **Item Filtering**: Only shows active ChargeableItem entries, ordered by sort_order
- **Bootstrap5 Styling**: All fields use `form-select` or `form-control` classes
- **Notes Optional**: Notes field is not required

---

## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Views](views.md)
- [Signals](signals.md)
- [Management Commands](management.md)
