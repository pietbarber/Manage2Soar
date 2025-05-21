# knowledgetest/management/commands/import_legacy_tests.py
import psycopg2
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from knowledgetest.models import QuestionCategory, Question
from members.models import Member

class Command(BaseCommand):
    help = "Import legacy written-test questions and categories from the legacy DB"

    def handle(self, *args, **options):
        self.stdout.write("Connecting to legacy database via settings.DATABASES['legacy']...")
        legacy_conf = settings.DATABASES['legacy']
        conn = psycopg2.connect(
            dbname=legacy_conf['NAME'],
            user=legacy_conf['USER'],
            password=legacy_conf['PASSWORD'],
            host=legacy_conf.get('HOST', ''),
            port=legacy_conf.get('PORT', ''),
        )
        # Ensure correct decoding of Windows-1252 content
        conn.set_client_encoding('WIN1252')

        try:
            with conn.cursor() as cursor:
                # Import categories from qcodes
                cursor.execute("SELECT qcode, description FROM qcodes;")
                for qcode, desc in cursor.fetchall():
                    cat, created = QuestionCategory.objects.get_or_create(
                        code=qcode,
                        defaults={'description': desc}
                    )
                    status = "created" if created else "exists"
                    self.stdout.write(f"Category {qcode}: {status}")

                # Import questions from test_contents
                cursor.execute(
                    """
                    SELECT qnum, code, question, a, b, c, d, answer,
                           explanation, lastupdated, updatedby
                    FROM test_contents
                    ORDER BY qnum;
                    """
                )
                rows = cursor.fetchall()

                with transaction.atomic():
                    for row in rows:
                        qnum, code, question_text, a, b, c, d, answer, explanation, lastupdated, updatedby = row

                        # Lookup category
                        try:
                            cat = QuestionCategory.objects.get(code=code)
                        except QuestionCategory.DoesNotExist:
                            self.stdout.write(self.style.ERROR(
                                f"Skipping Q{qnum}: unknown category '{code}'"
                            ))
                            continue

                        # Map legacy_username to Member
                        member = None
                        if updatedby:
                            try:
                                member = Member.objects.get(legacy_username=updatedby)
                            except Member.DoesNotExist:
                                self.stdout.write(self.style.WARNING(
                                    f"Member with legacy_username '{updatedby}' not found; leaving updated_by NULL for Q{qnum}"
                                ))

                        # Create or get question
                        q, created = Question.objects.get_or_create(
                            qnum=qnum,
                            defaults={
                                'category': cat,
                                'question_text': question_text,
                                'option_a': a,
                                'option_b': b,
                                'option_c': c,
                                'option_d': d,
                                'correct_answer': answer.strip()[0] if answer else '',
                                'explanation': explanation or '',
                                'last_updated': lastupdated,
                                # set FK via member instance
                                'updated_by': member,
                            }
                        )
                        action = "imported" if created else "exists"

                        # Always update the updated_by field on reimport
                        if not created:
                            q.updated_by = member
                            q.save(update_fields=['updated_by'])
                            action = "updated"

                        self.stdout.write(f"Question {qnum}: {action}")
        finally:
            conn.close()
            self.stdout.write(self.style.SUCCESS("Legacy import complete."))
