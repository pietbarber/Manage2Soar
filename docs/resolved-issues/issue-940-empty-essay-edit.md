# Issue #940: Instruction Report Not Editable When Essay Is Empty

## Status

Complete.

- Date: 2026-06-04
- Branch: feature/issue-940-empty-essay-edit

## Problem Summary

Instructors could create a flight instruction report without entering essay text, but then had no visible way to edit that report from the member instruction record page.

This looked like a same-date/multi-instructor routing problem at first, but the actual root cause was a UI rendering condition.

## Root Cause

The edit button in the member instruction record template was only rendered inside the essay-content block.

- If `report_text` existed, the section (including Edit) was shown.
- If `report_text` was empty, the section did not render at all.
- Result: no edit affordance for an otherwise valid report.

## Solution Implemented

A minimal, low-risk template fix was applied.

### Template behavior change

File updated:
- `templates/shared/member_instruction_record.html`

Changes:
1. The flight report header/edit section now renders when either:
   - essay text exists, or
   - the current user is the report instructor and report is within the 7-day edit window.
2. For empty essay reports that are still editable, a neutral placeholder is shown:
   - "No essay written yet."
3. Existing edit policy is preserved:
   - owner-only visibility
   - 7-day time limit
   - same report edit URL path

### What did not change

- No model changes
- No database migration
- No new route required
- No changes to report save semantics

## Test Coverage Added

File updated:
- `instructors/tests/test_member_instruction_record.py`

New regression class:
- `TestMemberInstructionRecordEmptyEssayEdit`

New test scenarios:
1. Owner sees edit link for empty-essay report within 7 days.
2. Owner does not see edit link for empty-essay report after 7 days.
3. Non-owner instructor does not see edit link for another instructor's empty-essay report.

## Validation

Targeted tests executed successfully:

- `pytest instructors/tests/test_member_instruction_record.py -k EmptyEssay -q`
- `pytest instructors/tests/test_member_instruction_record.py instructors/tests/test_obsolete_qualification_visibility.py -q`

Result: all relevant tests passed.

## Business Impact

- Prevents a real workflow dead-end for instructors.
- Reduces support noise from reports that appear "uneditable" after submission.
- Keeps behavior predictable while preserving existing authorization and timing rules.
