# Instructors App Documentation

Welcome to the documentation for the **instructors** Django app. This directory contains high‑level guides to help new contributors understand the architecture, key components, and maintenance tasks.

---

## Contents

* [Models](models.md) — Overview of core database models and their roles
* [Signals](signals.md) — How and when signals fire to keep data in sync
* [Utilities](utils.md) — Description of helper functions and their usage
* [Management Commands](management.md) — Instructions for running maintenance scripts

---

## Getting Started

1. Read **models.md** to familiarize yourself with the data structures.
2. Consult **signals.md** to understand automated snapshot updates.
3. Review **utils.md** for the main business‑logic helpers.
4. Run **backfill\_student\_progress\_snapshots** as per **management.md** to seed or refresh snapshots.

---

## How to Contribute

* Add or update documentation files in this directory alongside code changes.
* Keep examples in sync with actual code (e.g., method names, file paths).
* Submit pull requests with both code and doc changes for review.

---
