# CMS authorization baseline

This is a characterization of the CMS authorization that exists today. It is
not a proposed policy and it does not move any CMS check to
`members.authorization.resolve_authorization`. The tests in
`cms/tests/test_authorization_baseline.py` intentionally exercise the current
implementation rather than an intended future design.

## Decision points

### Page view (`Page.can_user_access(user, request=None)`)

The checks are effectively OR-ed as follows:

1. `is_public=True` allows everyone, including anonymous users, without
   checking `is_active`, membership, roles, or the request.
2. On a private page, a matching `PageMemberPermission` grants access because
   `can_user_edit()` is checked first. This is true for public and private
   pages, and is the editor-implied-view behavior.
3. A request whose session has `is_kiosk_authenticated=True` bypasses the
   membership-status gate for a private page. The user must still be
   authenticated for the eventual role check; the kiosk flag is not validated
   by this method.
4. Otherwise `members.utils.is_active_member(user)` must be true. The helper
   uses configured active membership statuses and treats superusers as active
   by default.
5. A private page with no role rows is then visible to any active member.
6. A private page with role rows uses OR semantics: any one matching boolean
   member attribute is enough. `active_member` is a special role that means
   any user who passed the active-member gate.

`cms_page` walks every URL segment and redirects to login (302) if *any*
resolved page or ancestor fails `can_user_access`. Thus a public child under a
private/restricted ancestor is not public through the child URL. The resources
index filters top-level pages with the same method; inaccessible pages are
omitted rather than returned as forbidden.

`document_pdf` repeats the complete ancestor-chain check before serving a PDF.
It is GET-only. Public valid PDFs return 200; a denied page/ancestor redirects
to login (302); a missing/non-PDF/invalid PDF returns 403. The response is an
inline `FileResponse` with the current security headers (see the focused tests
for the exact headers).

### Page edit/create (`Page.can_user_edit`, view helpers, site editor)

`Page.can_user_edit(user)` grants edit when **any** of these is true:

* authenticated superuser;
* explicit `PageMemberPermission` for that page; or
* authenticated user with `director`, `secretary`, or `webmaster` set.

There is no membership-status check inside `can_user_edit`; the
`edit_cms_page` and `create_cms_page` routes are wrapped in
`active_member_required` first (except that the decorator deliberately lets a
valid kiosk session through). `can_edit_page` additionally treats a
superuser/webmaster as an unconditional editor. `is_public` does not reduce
edit access. A member editor can edit a public page and a private page.

`can_create_in_directory` grants superuser/webmaster creation anywhere;
top-level creation (`parent=None`) is otherwise false; child creation requires
edit access on the parent. The child-create view copies the parent's member
editor rows, and copies role rows only when the new child is private.

The site editor accepts GET and POST and is CSRF-protected. Anonymous users are
redirected to login (302), an authenticated non-active non-kiosk user gets the
403 template from the decorator, and an active/kiosk user without edit access
gets a 403 response from the view. Successful edits redirect to the page
(302), save the page/document changes, set missing `Document.uploaded_by` to
the request user, and emit a success message. Homepage editing is separate:
only an authenticated superuser or webmaster may edit it; it also uses the
active-member decorator, accepts GET/POST, and redirects home after success.

### Homepage, public/private forms, and non-editor routes

`homepage` selects the public `home` content by default. An authenticated
non-kiosk user may request `?view=public`; otherwise an authenticated
superuser, kiosk session, or active member selects member-home content. The
`can_edit_page` template flag is webmaster/superuser-only. If legacy homepage
content is absent it falls back to the accessible CMS index.

`/cms/` is deliberately a public navigable index; it does not require login.
`contact/` and `contact/success/` are public. `feedback/` and
`feedback/success/` use `active_member_required`: anonymous redirects to
login, inactive authenticated users get 403, and kiosk sessions bypass the
membership-status check. A successful feedback POST saves the feedback and
creates notifications for active (`is_active=True`) webmasters. A successful
contact POST saves the submission and notifies active member managers, falling
back to active webmasters when no managers exist. Honeypot/spam submissions
redirect successfully without saving or notifying.

The external PDF proxy is GET-only and does not use page membership checks; it
requires a valid signed, allowlisted URL. Signing is GET-only, login-required,
and additionally requires superuser or the legacy `webmaster` flag. Invalid
signing/proxy input returns 403. Bundled PDF viewer assets are GET-only and
path-confined; invalid paths are 404.

## Django admin checks

These are separate from the site editor and do not consistently use page
membership status.

* `PageAdmin.has_module_permission`, `has_view_permission`,
  `has_add_permission`, and `has_delete_permission` use Django's normal
  permission checks **OR** authenticated `webmaster` access.
* `PageAdmin.has_change_permission(obj=page)` delegates to
  `page.can_user_edit(request.user)`. It therefore honors superuser,
  `PageMemberPermission`, director, secretary, and webmaster, without an
  explicit active-membership check. For a list view (`obj=None`) it allows a
  superuser or an authenticated webmaster/director/secretary.
* Navbar promotion fields are writable only by superusers/webmasters; other
  users see them read-only and forged changes are rejected in `save_model`.
* `PageRolePermissionAdmin`, `DocumentAdmin`, `ExternalPdfCacheAdmin`,
  `HomePageContentAdmin`, and `HomePageImageAdmin` use normal Django model
  permissions OR authenticated webmaster access. External PDF cache is
  read/delete-only: add and change always return false.
* `SiteFeedbackAdmin` and `VisitorContactAdmin` use Django's normal admin
  permission checks (there is no webmaster override in these classes).
  Visitor contacts cannot be added manually. Editing feedback response sets
  `responded_by`; editing contact status/notes sets `handled_by`.

The exact effective result of a normal admin check can therefore also depend
on `is_staff`, assigned Django permissions, and the auth backend. The baseline
does not infer a new role-to-codename mapping from those defaults.

## Suggested (unapproved) permission codenames

These names are design prompts only, not policy and not migrations:

* `cms.view_page`, `cms.edit_page`, `cms.create_page`, `cms.delete_page`
* `cms.view_document`, `cms.manage_document`
* `cms.manage_page_access`
* `cms.edit_homepage`
* `cms.view_feedback`, `cms.manage_feedback`
* `cms.view_visitorcontact`, `cms.manage_visitorcontact`
* `cms.sign_external_pdf`

Open questions before any migration include whether editor-implied-view
should survive inactive membership, whether kiosk should be allowed to edit
(the current decorator allows it but page edit still needs a grant), whether
admin page edits should enforce active membership, whether document-admin
access should honor the parent page, and whether public pages should remain
editor-assignable. The current code also has two authorities for “active”:
the configured membership status helper and Django `is_active`; they are not
interchangeable.
