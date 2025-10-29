# Knowledge Test App Documentation

Welcome to the documentation for the **knowledgetest** Django app. This directory contains guides for contributors and maintainers.

---

## Key Features

### Configurable Test Presets (Issue #135)
The knowledgetest app now supports **configurable test presets** that can be managed through the Django admin interface:

- **Database-driven presets**: Test presets are now stored in the database instead of being hardcoded
- **Django admin interface**: Staff users can create, edit, and manage test presets through `/admin/`
- **Category weight management**: Each preset defines question counts per category using JSONField storage
- **Backward compatibility**: Existing functionality preserved with automatic migration of hardcoded presets
- **Deletion protection**: Presets referenced by test templates cannot be deleted accidentally
- **Active/inactive status**: Presets can be temporarily disabled without deletion

#### Available Presets (migrated from legacy code):
- **ASK21**: ASK-21 aircraft-specific test (73 questions total)
- **PW5**: PW-5 aircraft-specific test (78 questions total)  
- **DISCUS**: Discus aircraft-specific test (47 questions total)
- **ACRO**: Aerobatics-focused test (30 questions total)
- **EMPTY**: Blank preset for custom test creation

#### Usage:
1. **Admin Interface**: Navigate to `/admin/knowledgetest/testpreset/` to manage presets
2. **Test Creation**: Use preset parameter in URLs: `/knowledgetest/create/?preset=ASK21`
3. **Dynamic Loading**: Test creation forms automatically load preset weights as initial values

---

## Contents

- [Models](models.md)
- [Forms](forms.md)
- [Views](views.md)
- [Management Commands](management.md)
- [Tests](tests.md)

---

## Getting Started

- Review [models.md](models.md) for the data model and database schema, including the new TestPreset model
- See [forms.md](forms.md) for form logic and validation, including preset parameter handling
- Check [views.md](views.md) for all view classes and functions, including dynamic preset loading
- Use [management.md](management.md) for import and admin scripts
- Read [tests.md](tests.md) for comprehensive test coverage documentation

---

## Also See
- [Models](models.md)
- [Forms](forms.md)
- [Views](views.md)
- [Management Commands](management.md)
- [Tests](tests.md)
