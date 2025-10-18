import os

from django.core.management.base import BaseCommand

from instructors.models import TrainingLesson

SYLLABUS_PATH = "legacy_syllabus_html"  # Change this path to your directory


class Command(BaseCommand):
    help = "Import legacy .shtml lesson plans into TrainingLesson models"

    def handle(self, *args, **kwargs):
        imported = 0
        for filename in os.listdir(SYLLABUS_PATH):
            if not filename.endswith(".shtml"):
                continue

            code = filename.replace(".shtml", "")
            full_path = os.path.join(SYLLABUS_PATH, filename)

            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()

            # Placeholder title; you can improve this later
            title = f"Lesson {code.upper()}"

            lesson, created = TrainingLesson.objects.get_or_create(code=code)
            lesson.description = html
            if created:
                lesson.title = title
            lesson.save()

            status = "Created" if created else "Updated"
            self.stdout.write(f"{status} lesson {code}")

            imported += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {imported} lesson files"))
