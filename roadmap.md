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

---

## In Progress 🔄
- Migration tooling for importing legacy member data from PostgreSQL JSON export
- Improve member import with robust date parsing and dry-run validation

---

## Upcoming Tasks 🚀
1. Add support for importing badge achievements from legacy system
2. Allow uploading vCard files to populate members (**deprioritized**)
3. Set up OAuth2 login for providers other than Google (Yahoo, Microsoft, Facebook)
4. Admin UI for editing badge recipients in a non-admin interface
5. Integrate legacy usernames (handle) to link historical flight log data
6. Customize Django admin list display to show additional fields like `membership_status`, `towpilot`, `glider_rating`, etc.
7. Allow members to view but not edit their own membership records (except photo & biography)
8. Add glider image thumbnails to members who own gliders
9. Add contact group management (for targeted emails)
10. Add flight history viewer (imported legacy data + new log uploads)

---

## Nice-to-Haves / Stretch Goals
- Add calendar of events (duty roster, instructor availability, club events)
- Member activity timeline (badge earned, glider flights, etc.)
- CSV or PDF export of member list for club use
- Automatic backup and restore scripts for database/media
- Dockerize deployment

---

If you have questions, suggestions, or contributions, please open an issue or reach out to Piet Barber!

