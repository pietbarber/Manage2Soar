# instructors/signals.py


import sys

from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import GroundInstruction, InstructionReport
from .utils import update_student_progress_snapshot

# Utility to check if it's safe to run signal DB code


def is_safe_to_run_signals():
    return apps.ready and not any(
        cmd in sys.argv
        for cmd in ["makemigrations", "migrate", "collectstatic", "loaddata", "test"]
    )


####################################################
# Signal handlers for updating StudentProgressSnapshot
#
# These receivers listen for post-save events on InstructionReport
# and GroundInstruction models, and trigger a refresh of the
# StudentProgressSnapshot for the affected student.
####################################################


@receiver(post_save, sender=InstructionReport)
def instruction_report_saved(sender, instance, **kwargs):
    """
    Handler for InstructionReport saves.

    Whenever an InstructionReport is created or updated, this
    signal fires and calls update_student_progress_snapshot()
    for the report's student to keep the snapshot in sync.
    """
    if not is_safe_to_run_signals():
        return
    update_student_progress_snapshot(instance.student)


@receiver(post_save, sender=GroundInstruction)
def ground_instruction_saved(sender, instance, **kwargs):
    """
    Handler for GroundInstruction saves.

    Whenever a GroundInstruction session is created or updated,
    this signal fires and calls update_student_progress_snapshot()
    for the session's student to update the snapshot accordingly.
    """
    if not is_safe_to_run_signals():
        return
    update_student_progress_snapshot(instance.student)
