## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Models](models.md)
- [Signals](signals.md)
- [Utilities](utils.md)
- [Decorators](decorators.md)
# Views in instructors/views.py

This document summarizes all classes and functions in `instructors/views.py`.

---

## Main View Functions

- **logbook_loading(request)**: Intermediate loading page for logbook import/export.
- **public_syllabus_overview(request)**: Public view of all available syllabi.
- **public_syllabus_detail(request, code)**: Public detail page for a specific syllabus.
- **instructors_home(request)**: Main dashboard for instructors.
- **syllabus_overview(request)**: Staff view of all syllabi.
- **syllabus_overview_grouped(request)**: Staff view of syllabi grouped by phase/type.
- **syllabus_detail(request, code)**: Staff detail page for a specific syllabus.
- **fill_instruction_report(request, student_id, report_date)**: Enter or edit an instruction report for a student on a given date.
- **select_instruction_date(request, student_id)**: Select a date for instruction report entry.
- **get_instructor_initials(member)**: Helper to get instructor initials for display.
- **member_training_grid(request, member_id)**: Shows a member's training progress grid.
- **log_ground_instruction(request)**: Enter or edit a ground instruction report.
- **is_instructor(user)**: Returns True if user is an instructor.
- **assign_qualification(request, member_id)**: Assigns a qualification to a member.
- **progress_dashboard(request)**: Dashboard of student progress for instructors.
- **edit_syllabus_document(request, slug)**: Edit a syllabus document.
- **member_instruction_record(request, member_id)**: Shows a member's full instruction record.
- **public_syllabus_qr(request, code)**: Returns a QR code for a public syllabus.
- **public_syllabus_full(request)**: Public view of all syllabi (full detail).
- **member_logbook(request)**: Member's logbook view.
- **needed_for_solo(request, member_id)**: Shows requirements needed for solo.
- **needed_for_checkride(request, member_id)**: Shows requirements needed for checkride.
- **instruction_report_detail(request, report_id)**: Detail view for a specific instruction report.
- **export_member_logbook_csv(request)**: Exports a member's logbook as CSV.
- **bulk_assign_qualification(request)**: Bulk-assigns a qualification to multiple members at once. Used by safety officers for recording attendance at mandatory meetings. Access restricted to instructors, safety officers, and superusers.

## Main Classes

- **CreateWrittenTestView (FormView)**: Handles creation of written tests for students.
- **WrittenTestReviewView (DjangoView)**: Allows instructors to review a student's written test.

## Notable Helpers (Inner/Private)

- **get_instructor_meta_for_date(d)**: Helper for instructor metadata by date.
- **format_hhmm(duration)**: Formats a duration as HH:MM (used in logbook and CSV export).
- **_build_signoff_records(student, threshold_scores, requirement_check)**: Internal helper for signoff logic.

---

## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Models](models.md)
- [Signals](signals.md)
- [Utilities](utils.md)
- [Decorators](decorators.md)
