# Skyline Soaring Club Member Portal - Roadmap

This roadmap outlines current and future development goals for the Skyline Soaring Club Member Portal. Items marked as ✅ are complete.

## Completed Tasks ✅
1. Move Django SECRET_KEY to `.env` file and rotate it.
2. Replace `@login_required` with `@active_member_required` for superuser access.
3. Set up Google OAuth2 login, including:
   - Safe credential storage in `.env`
   - First login with Google OAuth creates an account with default status
   - First login with username/password then allows later OAuth2 login (email match)
   - OAuth2 login can import Google profile photo
4. Enforce profile photo uploads to be resized and aspect-ratio checked.
5. Add support for rich biography field with TinyMCE and image upload.
6. Enable users to upload profile photos; allow self-service photo edits.
7. Add vCard QR code to member_view.html with proper home contact tagging.
8. Add badge management system:
   - Admin-editable badges with HTML descriptions
   - Member-badge relationship with award date
   - Badge board with thumbnails of recipients
   - Accordion-style badge descriptions
   - Ordered badge display
9. Add member name formatting helper (`get_display_name`)
10. Improve navigation UI and add responsive hamburger menu.
11. Setup flatpickr calendar popup for ISO 8601 date input.
12. Automated profile photos using Pydenticon instead of the static image. 
13. States should be a pull-down.  (Complicated by the fact that we have non-US ex members)
14. Hyphenate phone numbers so the phone numbers don't look like barbaric strings of digits
15. members_list page: differentiate home vs cell phone numbers. 
16. members_list page: sort by lastname in a default view.  
- Create restricted site for Instructors

---

## On Hold tasks 🛑
- Migration tooling for importing legacy member data from PostgreSQL JSON export
- create flight log tables in preparation for logsheet program. 

---

## In Progress 🔄
- Improve member import with robust date parsing and dry-run validation

---

## Abandoned Tasks ⚰️
1. Allow uploading vCard files to populate members (**deprioritized**)


---

## Upcoming Tasks 🚀
1. Add support for importing badge achievements from legacy system
2. Set up OAuth2 login for providers other than Google (Yahoo, Microsoft, Facebook)
3. Admin UI for editing badge recipients in a non-admin interface
4. Integrate legacy usernames (handle) to link historical flight log data
5. Customize Django admin list display to show additional fields like `membership_status`, `towpilot`, `glider_rating`, etc.
6. Allow members to view but not edit their own membership records (except photo & biography)
7. Add glider image thumbnails to members who own gliders
8. Add contact group management (for targeted emails)
9. Add flight history viewer (imported legacy data + new log uploads)
- Import Training Syllabus

---

## Nice-to-Haves / Stretch Goals
- Add calendar of events (duty roster, instructor availability, club events)
- Member activity timeline (badge earned, glider flights, etc.)
- CSV, XLS or PDF export of member list for club use
- Automatic backup and restore scripts for database/media
- Dockerize deployment

---

If you have questions, suggestions, or contributions, please open an issue or reach out to Piet Barber!

