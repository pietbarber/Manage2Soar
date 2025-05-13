# instructors/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import StudentProgressSnapshot
from .utils import update_student_progress_snapshot
from logsheet.models import Flight
from .models import GroundInstruction, InstructionReport

@receiver(post_save, sender=InstructionReport)
def instruction_report_saved(sender, instance, **kwargs):
    update_student_progress_snapshot(instance.student)

@receiver(post_save, sender=GroundInstruction)
def ground_instruction_saved(sender, instance, **kwargs):
    update_student_progress_snapshot(instance.student)
