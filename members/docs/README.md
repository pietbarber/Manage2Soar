# Members App Documentation

Welcome to the documentation for the `members` app. This app manages all aspects of club membership, including member profiles, biographies, badges, authentication, and integration with external systems.

## Overview
- **Purpose:** Central hub for all member-related data and logic.
- **Key Features:**
  - Member profiles and authentication (Google OAuth2, fallback to Django login)
  - Biographies and profile images
  - Badge tracking and display
  - Role/group management
  - Data import from legacy systems
  - Decorators for access control
  - Custom pipelines for authentication

## Documentation Index
- [models.md](models.md): Member, Biography, Badge, and related models (with ERD)
- [decorators.md](decorators.md): Decorators for access control and member status
- [pipeline.md](pipeline.md): Custom authentication and profile pipelines
- [views.md](views.md): Member-facing and admin views
- [management.md](management.md): Management commands and legacy data import
- [tests.md](tests.md): Unit tests and coverage

## Also See
- [models.md](models.md)
- [decorators.md](decorators.md)
- [pipeline.md](pipeline.md)
- [views.md](views.md)
- [management.md](management.md)
- [tests.md](tests.md)
- [forms.md](forms.md)
