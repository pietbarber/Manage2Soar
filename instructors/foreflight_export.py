"""ForeFlight logbook import template schema and row helpers (Issue #921).

The headers, ordering, datatype rows and 69-cell physical row width mirror
ForeFlight's ``logbook_template_faa.csv``; the copy under
``instructors/tests/fixtures/foreflight/`` is the authority the tests compare to.
"""

from decimal import ROUND_HALF_UP, Decimal

from utils.csv import sanitize_csv_cell

ROW_WIDTH = 69

PREAMBLE_ROW = [
    "ForeFlight Logbook Import",
    "This row is required for importing into ForeFlight. Do not delete or modify.",
]

AIRCRAFT_FIELDS = [
    "AircraftID",
    "equipType",
    "TypeCode",
    "Year",
    "Make",
    "Model",
    "GearType",
    "EngineType",
    "Category/Class",
    "complexAircraft",
    "highPerformance",
    "pressurized",
    "taa",
]

AIRCRAFT_TYPES = [
    "Text",
    "Text",
    "Text",
    "YYYY",
    "Text",
    "Text",
    "Text",
    "Text",
    "Text",
    "Boolean",
    "Boolean",
    "Boolean",
    "Boolean",
]

CUSTOM_LAUNCH_METHOD = "[Text]Launch Method"
CUSTOM_RELEASE_ALTITUDE = "[Numeric]Release Altitude"

FLIGHT_FIELDS = [
    "Date",
    "AircraftID",
    "From",
    "To",
    "Route",
    "TimeOut",
    "TimeOff",
    "TimeOn",
    "TimeIn",
    "OnDuty",
    "OffDuty",
    "TotalTime",
    "PIC",
    "SIC",
    "Night",
    "Solo",
    "CrossCountry",
    "PICUS",
    "MultiPilot",
    "IFR",
    "Examiner",
    "NVG",
    "NVGOps",
    "Distance",
    "Takeoff Day",
    "Takeoff Night",
    "Landing Full-Stop Day",
    "Landing Full-Stop Night",
    "Landing Touch-and-Go Day",
    "Landing Touch-and-Go Night",
    "ActualInstrument",
    "SimulatedInstrument",
    "GroundTraining",
    "GroundTrainingGiven",
    "HobbsStart",
    "HobbsEnd",
    "TachStart",
    "TachEnd",
    "Holds",
    "Approach1",
    "Approach2",
    "Approach3",
    "Approach4",
    "Approach5",
    "Approach6",
    "DualGiven",
    "DualReceived",
    "SimulatedFlight",
    "InstructorName",
    "InstructorComments",
    "Person1",
    "Person2",
    "Person3",
    "Person4",
    "Person5",
    "Person6",
    "PilotComments",
    "Flight Review",
    "IPC",
    "Checkride",
    "FAA 61.58",
    "NVG Proficiency",
    CUSTOM_LAUNCH_METHOD,
    CUSTOM_RELEASE_ALTITUDE,
    "[Hours]CustomFieldName",
    "[Counter]CustomFieldName",
    "[Date]CustomFieldName",
    "[DateTime]CustomFieldName",
    "[Toggle]CustomFieldName",
]

FLIGHT_TYPES = (
    ["Date"]
    + ["Text"] * 4
    + ["HH:MM"] * 6
    + ["Decimal or HH:MM"] * 11
    + ["Number", "Decimal"]
    + ["Number"] * 6
    + ["Decimal or HH:MM"] * 4
    + ["Decimal"] * 4
    + ["Number"]
    + ["Packed Detail"] * 6
    + ["Decimal or HH:MM"] * 3
    + ["Text", "Text"]
    + ["Packed Detail"] * 6
    + ["Text"]
    + ["Boolean"] * 5
    + ["Text", "Decimal", "Decimal or HH:MM", "Number", "Date", "DateTime", "Boolean"]
)

APPROACH_HINT = "#;type;runway;airport;comments"
PERSON_HINT = "name;role;email;phone"

assert len(AIRCRAFT_FIELDS) == len(AIRCRAFT_TYPES) == 13
assert len(FLIGHT_FIELDS) == len(FLIGHT_TYPES) == ROW_WIDTH

LAUNCH_METHOD_LABELS = {
    "tow": "Aerotow",
    "winch": "Winch",
    "self": "Self-launch",
    "other": "Other",
}


def _pad(cells):
    if len(cells) > ROW_WIDTH:
        raise ValueError(f"ForeFlight row has {len(cells)} cells; max is {ROW_WIDTH}")
    return list(cells) + [""] * (ROW_WIDTH - len(cells))


def format_hours(minutes):
    """Whole minutes as decimal hours at hundredths precision (e.g. 1 -> '0.02')."""
    hours = Decimal(int(minutes or 0)) / Decimal(60)
    return str(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_hours_or_blank(minutes):
    return format_hours(minutes) if minutes else ""


def format_clock(value):
    return f"{value.hour:02d}:{value.minute:02d}" if value else ""


def packed_person(name, role):
    """Pack an occupant as ``name;role;email;phone``; semicolons in names would break it."""
    clean = (name or "").replace(";", ",").strip()
    return f"{clean};{role};;" if clean else ""


def _row_from_values(fields, values):
    unknown = set(values) - set(fields)
    if unknown:
        raise KeyError(f"Unknown ForeFlight columns: {sorted(unknown)}")
    return _pad([sanitize_csv_cell(values.get(name, "")) for name in fields])


def aircraft_row(values):
    return _row_from_values(AIRCRAFT_FIELDS, values)


def flight_row(values):
    return _row_from_values(FLIGHT_FIELDS, values)


def write_aircraft_table(writer, aircraft_rows):
    """Write the preamble and Aircraft Table section, ending with a blank row."""
    writer.writerow(_pad(PREAMBLE_ROW))
    writer.writerow(_pad([]))
    writer.writerow(_pad(["Aircraft Table"]))
    writer.writerow(_pad(AIRCRAFT_TYPES))
    writer.writerow(_pad(AIRCRAFT_FIELDS))
    for row in aircraft_rows:
        writer.writerow(row)
    writer.writerow(_pad([]))


def write_flights_table_header(writer):
    """Write the Flights Table marker, datatype and header rows."""
    marker = _pad(["Flights Table"])
    marker[FLIGHT_FIELDS.index("Approach1")] = APPROACH_HINT
    marker[FLIGHT_FIELDS.index("Person1")] = PERSON_HINT
    writer.writerow(marker)
    writer.writerow(_pad(FLIGHT_TYPES))
    writer.writerow(_pad(FLIGHT_FIELDS))
