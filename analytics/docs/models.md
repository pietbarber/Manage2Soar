# Models

The **Analytics** app defines **no database models**.

It reads from:
- `logsheet.models.Logsheet`
- `logsheet.models.Flight`
- `logsheet.models.Glider`
- user data via `django.contrib.auth.get_user_model`

No migrations are required for this app.
