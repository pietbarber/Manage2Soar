# instructors/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import StudentProgressSnapshot
from .utils import update_student_progress_snapshot
from logsheet.models import Flight
from .models import GroundInstruction

@receiver(post_save, sender=Flight)
def flight_instruction_saved(sender, instance, created, **kwargs):
    # whenever a Flight with an instructor is saved, update their snapshot
    if instance.instructor_id:
        update_student_progress_snapshot(instance.instructor)

@receiver(post_save, sender=GroundInstruction)
def ground_instruction_saved(sender, instance, created, **kwargs):
    # whenever a GroundInstruction is saved, update that student’s snapshot
    update_student_progress_snapshot(instance.student)
