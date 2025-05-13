# instructors/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import StudentProgressSnapshot, GroundInstruction, InstructionReport
from .utils import update_student_progress_snapshot

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
    update_student_progress_snapshot(instance.student)

@receiver(post_save, sender=GroundInstruction)
def ground_instruction_saved(sender, instance, **kwargs):
    """
    Handler for GroundInstruction saves.

    Whenever a GroundInstruction session is created or updated,
    this signal fires and calls update_student_progress_snapshot()
    for the session's student to update the snapshot accordingly.
    """
    update_student_progress_snapshot(instance.student)
