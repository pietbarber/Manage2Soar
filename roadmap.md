# Skyline Soaring Club Member Portal - Roadmap

This roadmap outlines current and future development goals for the Skyline Soaring Club Member Portal. Items marked as ✅ are complete.

## Completed Tasks ✅
- Move Django SECRET_KEY to `.env` file and rotate it.
- Replace `@login_required` with `@active_member_required` for superuser access.
- Set up Google OAuth2 login, including:
   - Safe credential storage in `.env`
   - First login with Google OAuth creates an account with default status
   - First login with username/password then allows later OAuth2 login (email match)
   - OAuth2 login can import Google profile photo
- Enforce profile photo uploads to be resized and aspect-ratio checked.
- Add support for rich biography field with TinyMCE and image upload.
- Enable users to upload profile photos; allow self-service photo edits.
- Add vCard QR code to member_view.html with proper home contact tagging.
- Add badge management system:
   - Admin-editable badges with HTML descriptions
   - Member-badge relationship with award date
   - Badge board with thumbnails of recipients
   - Accordion-style badge descriptions
   - Ordered badge display
- Add member name formatting helper (`get_display_name`)
- Improve navigation UI and add responsive hamburger menu.
- Setup flatpickr calendar popup for ISO 8601 date input.
- Automated profile photos using Pydenticon instead of the static image. 
- States should be a pull-down.  (Complicated by the fact that we have non-US ex members)
- Hyphenate phone numbers so the phone numbers don't look like barbaric strings of digits
- members_list page: differentiate home vs cell phone numbers. 
- members_list page: sort by lastname in a default view.  
- Create restricted site for Instructors
- Support logging of passengers:
  - Passenger may be a member (dropdown) or a non-member (plain text).
  - Field is only visible if no instructor is present on the flight.
- Implement logsheet-level finances:
  - Add a Finances modal or section, accessible via a dedicated button.
  - Completion of finances is required before finalizing a logsheet.
- Define tow altitude rate model:
  - Create a model under `logsheet` to store tow altitude → cost mappings.
  - Combine with existing glider rental rates.
- Add support for payment methods:
  - "On account" or handwritten check.
  - Payments may be assigned to a member other than the pilot.
  - Support 50/50 cost splits or split by component (tow vs rental).
- Require duty officer log/essay before logsheet finalization.
- Block finalization unless all gliders are marked as landed.
- Centralized validation logic before allowing logsheet finalization:
  - Gliders landed
  - Finances completed
  - Duty officer essay entered
 - Optionally add a “pending” flight status for pre-launch queue logging
- Migration tool for legacy flight logs:
  - Import historical PostgreSQL data going back to 2005.
  - Must integrate with current Member, Glider, and Towplane models.
- Paginated or limited logsheet list:
  - Include search or filter capability for older logsheets.
- Add support for importing badge achievements from legacy system
- Integrate legacy usernames (handle) to link historical flight log data
- Admin UI for editing badge recipients in a non-admin interface

### 🔁 Legacy Data Import
- Imported 29,000+ historical flights from legacy `flight_info` table.
- Created logsheet entries automatically during flight import if none existed.
- Imported towplane closeouts from legacy `towplane_data`, handling:
  - Tach start/stop
  - Tach time
  - Fuel added
  - Comments
- Imported duty crews from legacy `ops_days`, auto-creating logsheets if missing.
- Linked flights and logsheets to `Member` records using `legacy_username`.
- Cleaned up glider references using a custom contest-ID-to-N-number mapping.
- Deleted the `import_bot` user after import to avoid security issues.

### 🛩️ Flight & Logsheet Enhancements
- `manage_logsheet` now shows `full_display_name` for members.
- Fallback to `legacy_pilot_name` if pilot FK is null.
- Prevent or warn on edits to imported logsheets (from `import_bot`).
- Winch launches recognized from `"N-A Winch"` towpilot entries.
- `airfield` now properly displayed in the logsheet list view.
- Year dropdown UI fixed (not full-width).
- Location search bug fixed (was incorrectly using nonexistent `location` field).
- Closeout summary now shows full duty crew (DO, ADO, DI, surge, tow).

### 👤 Member Profile Enhancements
- Added "Flights by Member" page showing all flights in reverse chronological order.
- Linked from `member_list` with a flight icon button.
- User’s own flight history available via navbar profile dropdown.
- `member_view` includes a summary of all gliders flown by that member.
- Added ability to export a member’s logbook to Excel in 14 CFR §61.51 format.

---

## 🚧 In Progress

- Adding support for multiple towplanes with unique tow rates (independent contractor support).
- Additional filters for `member_list` by roles and activity.
- Better search and filtering on logsheets and flight lists.
- Winch launch representation in cost calculations and flight display.
- Optional local/offline mode for flight logging.

---

## 📝 Upcoming To-Dos

- Add missing pilots/instructors to imported flights using `legacy_*_name`.
- Build admin UI to manage Towplane-specific pricing.
- Automatically generate financial records for historical flights (optional).
- Ensure only active members can appear in duty roles post-import.
- Polish logsheet closeout UI to support tach time entry.
- Add QuickBooks Online CSV export for finalized logsheets.

---

## 🪦 Abandoned or Deferred

- vCard upload to populate members (dropped due to data quality/control).
- Attempting to match all legacy passengers to `Member` records (manual cleanup preferred).

---
