## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Models](models.md)
- [Utilities](utils.md)
- [Views](views.md)
- [Decorators](decorators.md)
# Signals Reference

This document describes the Django signal handlers defined in **instructors/signals.py** that keep the `StudentProgressSnapshot` model in sync with instructional data.

---

## Overview

Two `post_save` signal receivers listen for changes in `InstructionReport` and `GroundInstruction` models. Whenever a new report or ground session is created or updated, the corresponding student’s progress snapshot is recomputed via the `update_student_progress_snapshot()` utility.

---

## Signal Handlers

```python
# instructors/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from instructors.models import InstructionReport, GroundInstruction
from instructors.utils import update_student_progress_snapshot

@receiver(post_save, sender=InstructionReport)
def instruction_report_saved(sender, instance, **kwargs):
    """
    Fires when an InstructionReport is saved.

    Triggers a rebuild of the StudentProgressSnapshot for:
      - instance.student
    """
    update_student_progress_snapshot(instance.student)

@receiver(post_save, sender=GroundInstruction)
def ground_instruction_saved(sender, instance, **kwargs):
    """
    Fires when a GroundInstruction session is saved.

    Recalculates the StudentProgressSnapshot for:
      - instance.student
    """
    update_student_progress_snapshot(instance.student)
```

**Key points:**

* **When it fires:** Immediately after any `save()` call on `InstructionReport` or `GroundInstruction`.
* **What it does:** Calls `update_student_progress_snapshot()` which:

  1. Counts total sessions (flight reports + ground sessions)
  2. Aggregates lesson scores to compute solo and checkride progress
  3. Updates or creates a `StudentProgressSnapshot` record
* **Why:** Avoids expensive dashboard queries by precomputing progress in a single table.

---

## Registration

Ensure that **instructors/signals.py** is imported in the app’s `ready()` method, e.g., in **instructors/apps.py**:

```python
# instructors/apps.py
from django.apps import AppConfig

class InstructorsConfig(AppConfig):
    name = 'instructors'

    def ready(self):
        import instructors.signals  # noqa
```

This guarantees the signal handlers are connected when Django starts.
