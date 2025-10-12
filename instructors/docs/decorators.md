## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Models](models.md)
- [Signals](signals.md)
- [Utilities](utils.md)
- [Views](views.md)
# Decorators in instructors/decorators.py

This document describes the key decorators in `instructors/decorators.py`.

---

## instructor_required
Restricts view access to authenticated instructors (or superusers). Checks:
- User is authenticated
- User is a superuser, or
- User has a valid membership status and `user.instructor` is True
- Otherwise, redirects to login or renders 403

**Usage:**
```python
@instructor_required
def my_view(request, ...):
    ...
```

---

## member_or_instructor_required
Restricts view access to either:
- The member matching the `member_id` URL argument, or
- Any instructor (or superuser)

Checks authentication, valid membership, and that the user is either the member or an instructor. Otherwise, redirects to login or renders 403.

**Usage:**
```python
@member_or_instructor_required
def my_view(request, member_id, ...):
    ...
```

---

## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Models](models.md)
- [Signals](signals.md)
- [Utilities](utils.md)
- [Views](views.md)
