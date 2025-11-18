# Members App Documentation

Welcome to the documentation for the `members` app. This app manages all aspects of club membership, including member profiles, biographies, badges, authentication, and integration with external systems.

## Overview
- **Purpose:** Central hub for all member-related data and logic.
- **Key Features:**
  - Member profiles and authentication (Google OAuth2, fallback to Django login)
  - **Membership application processing (Issue #245)** - Complete system for non-logged-in users including:
    - International address support with country-specific validation
    - Foreign pilot support with conditional field requirements
    - User-initiated withdrawal functionality with notifications
    - Administrative review interface with Django admin integration
    - Automated cleanup system with 365-day retention
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
