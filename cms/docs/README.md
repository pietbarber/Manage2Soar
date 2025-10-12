# CMS App

![CMS ERD](cms.png)

The **CMS** (Content Management System) app manages club news, homepage content, and static pages. It allows admins to update the website’s informational content without code changes.

- **Audience:** authenticated staff/admins (edit), all members/guests (view)
- **Route:** `/cms/`
- **Nav:** included via the main navbar and homepage.

---

## Quick Start

1. Log in as a staff/admin user.
2. Visit `/cms/` to view or edit content.
3. Use the admin interface to add or update news, homepage content, or static pages.

---

## Pages & Permissions

- `cms.views.homepage` (public, shows homepage content)
- `cms.views.news_list` (public, shows news posts)
- `cms.views.page_detail` (public, shows static pages)
- `cms.views.page_edit` (staff only, edit static pages)
- `cms.views.news_edit` (staff only, edit news)

---

## URL Patterns

- `/cms/` – homepage content
- `/cms/news/` – news list
- `/cms/page/<slug>/` – static page detail
- `/cms/page/<slug>/edit/` – edit static page (staff only)
- `/cms/news/<pk>/edit/` – edit news (staff only)

---

## Content Types

- **HomepageContent**: main homepage text, images, and links
- **NewsPost**: club news items (title, body, date, author)
- **StaticPage**: custom pages (title, slug, body, last updated)

---

## Implementation Notes

- **Templates:** `templates/cms/` (homepage, news, page detail/edit)
- **Models:** `cms/models.py` (`HomepageContent`, `NewsPost`, `StaticPage`)
- **Admin:** all content types are editable via Django admin
- **Permissions:** only staff can edit; all can view

---

## Styling

- Uses Bootstrap 5 for layout and forms
- Custom styles in `static/css/baseline.css`
- News and homepage images use responsive classes

---

## Troubleshooting

- **Page not found:** check the slug in the URL and that the page exists
- **Permission denied:** only staff can edit content
- **Images not showing:** ensure media files are uploaded and MEDIA_URL is correct

---

## Development Tips

- To add a new static page: create via admin or `/cms/page/<slug>/edit/`
- To update homepage: edit `HomepageContent` in admin or `/cms/`
- To add news: create a `NewsPost` in admin or `/cms/news/<pk>/edit/`

---

## Changelog

- **2025-10** Initial CMS documentation.
