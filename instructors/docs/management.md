# Management Commands Reference

This document covers all custom Django management commands in `instructors/management/commands/`.

---

## `backfill_student_progress_snapshot`

**Filename:** `backfill_student_progress_snapshot.py`
**Purpose:** Recomputes `StudentProgressSnapshot` for all active members.
**Usage:**

```bash
python manage.py backfill_student_progress_snapshot
```

* Iterates over members with statuses in `DEFAULT_ACTIVE_STATUSES`.
* Calls `update_student_progress_snapshot(member)` for each.
* Prints progress (`[1/42] Updated snapshot for Alice Smith`).

---

## `import_legacy_instruction`

**Filename:** `import_legacy_instruction.py`
**Purpose:** Migrates legacy instructional records into the new models.
**Usage:**

```bash
python manage.py import_legacy_instruction --source=legacy_db_connection
```

* Reads from a legacy data source (e.g., old database or CSV).
* Creates `InstructionReport` and associated `LessonScore` entries.
* Handles date parsing and duplicate avoidance.
* Options:

  * `--source`: Path or connection string for the legacy dataset.
  * `--dry-run`: Validate without writing.

---

## `import_member_qualifications`

**Filename:** `import_member_qualifications.py`
**Purpose:** Imports member qualification records from legacy data.
**Usage:**

```bash
python manage.py import_member_qualifications --file=quals.csv
```

* Parses a legacy CSV or database table of qualifications.
* Creates `MemberQualification` instances linking `Member` and `ClubQualificationType`.
* Flags imported records and skips duplicates.
* Options:

  * `--file`: Path to the import CSV.
  * `--update-existing`: Overwrite existing records.

---

## `import_legacy_syllabus`

**Filename:** `import_legacy_syllabus.py`
**Purpose:** Loads syllabus content from legacy HTML files into `TrainingLesson`, `TrainingPhase`, and `SyllabusDocument`.
**Usage:**

```bash
python manage.py import_legacy_syllabus --dir=legacy_syllabus/
```

* Scans a directory of legacy `.shtml` files.
* Creates or updates `TrainingPhase`, `TrainingLesson`, and `SyllabusDocument` records.
* Maintains original ordering via filename conventions.
* Options:

  * `--dir`: Directory containing legacy syllabus files.
  * `--override`: Overwrite existing entries.

---

### General Tips

* Always run with `--dry-run` first if available.
* Ensure your Django settings point to the correct database when importing.
* After imports, consider running `backfill_student_progress_snapshot` to refresh snapshots.
* Review logs for errors and duplicate warnings.

---

*End of management commands reference.*

## See Also
- [README (App Overview)](README.md)
- [Models](models.md)
- [Signals](signals.md)
- [Utilities](utils.md)
- [Views](views.md)
- [Decorators](decorators.md)
