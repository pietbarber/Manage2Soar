# SiteConfiguration fields

This document lists the important `SiteConfiguration` fields used by the application 

## Overview

The `SiteConfiguration` model stores site-wide settings and customizable role titles. There should only be one instance of this model. The admin UI provides an editor for the single SiteConfiguration object.
This app is in place in order to configure some site-wide variables. This will allow a webmaster
to dictate whether or not the club in question uses a duty roster to assign instructors, or 
even to assign duty at all.  It also allows site-wide configuration for what the club is named, 
what the URL is for the club, and allows the webmaster to upload a logo for the club. 

## Notable fields

- `club_name` (CharField)
  - Human-friendly club name used in the navbar and title.
  - Example default: `"Manage2Soar"` (the template will fall back to this if empty).

- `domain_name` (CharField)
  - Primary domain name for the site (e.g. `example.org`).

- `club_logo` (ImageField)
  - Optional logo image used in the navbar and for generating a favicon.

- `club_abbreviation` (CharField)
  - Short abbreviation used in small UIs.

- `membership_manager_title` (CharField)
  - New: customizable label for the person who manages membership (e.g. "Membership Manager", "Member Meister").
  - Default: `"Membership Manager"`
  - Used in templates (for example, the members detail page) so UI text can refer to the club's preferred job title.

- `equipment_manager_title` (CharField)
  - Customizable label for equipment manager.

- `duty_officer_title`, `assistant_duty_officer_title`, `instructor_title`, etc.
  - Existing terminology fields for various roles; used by the roster and scheduling UIs.

## Redaction notification dedupe

- `redaction_notification_dedupe_minutes` (PositiveIntegerField)
  - Number of minutes to suppress duplicate redaction notifications for the same member URL.
  - Default: `60` (minutes).
  - Behavior: when a member toggles redaction on/off, the system notifies roster managers; this field controls a time-window to avoid spamming the same recipient with repeated notifications for the same member URL.

## Scheduling toggles

- `schedule_instructors`, `schedule_tow_pilots`, `schedule_duty_officers`, `schedule_assistant_duty_officers`
  - Boolean toggles to enable/disable scheduling UI elements for specific roles.

## Notes

- Only one `SiteConfiguration` instance should exist. The model enforces this in its `clean()` method.
- The admin UI exposes these fields; to change behavior or defaults, edit this model and run any required migrations.

## Using `SiteConfiguration` from `manage.py shell`

Here are common examples you may find useful when working from a Django shell (`python manage.py shell`):

1. Read the current configuration

```python
from siteconfig.models import SiteConfiguration
sc = SiteConfiguration.objects.first()
print(sc.club_name)
print(sc.membership_manager_title)

# Access the dedupe window
print(sc.redaction_notification_dedupe_minutes)
```

2. Update a field (safe for one-off/admin fixes)

```python
from siteconfig.models import SiteConfiguration
sc = SiteConfiguration.objects.first()
sc.membership_manager_title = 'Membership Meister'
sc.redaction_notification_dedupe_minutes = 120
sc.save()
```

3. Create a SiteConfiguration (only do this if none exists)

```python
from siteconfig.models import SiteConfiguration
if not SiteConfiguration.objects.exists():
  SiteConfiguration.objects.create(
    club_name='My Club',
    domain_name='example.org',
    club_abbreviation='MC',
  )

# Always prefer editing via the Django admin for safety
```

4. Use from templates

In templates you can load the siteconfig with the provided template tag:

```django
{% load siteconfig_tags %}
{% get_siteconfig as siteconfig %}
{{ siteconfig.membership_manager_title }}
```

If you want more examples (for scripts or tests), tell me which patterns you need and I will add them.
