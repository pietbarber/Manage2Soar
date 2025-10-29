import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from knowledgetest.models import (
    Question,
    QuestionCategory,
    WrittenTestAnswer,
    WrittenTestAttempt,
    WrittenTestTemplate,
)
from instructors.models import InstructionReport
from notifications.models import Notification
from typing import cast

User = get_user_model()


class QuizFlowTests(TestCase):

    def test_student_submission_records_attempt_and_scores(self):
        """
        Simulate a student submitting answers to a written test and verify:
        - Attempt is recorded
        - Score is 50% and marked as passed
        - Two answer records exist, one correct and one incorrect
        """
        # Log in as the student
        login_success = self.client.login(username="student", password="pass")
        self.assertTrue(login_success, "Login failed for test user")

        # Ensure the assignment exists and is incomplete
        from knowledgetest.models import WrittenTestAssignment

        assignment = WrittenTestAssignment.objects.filter(
            template=self.tmpl, student=self.student, completed=False
        ).first()
        self.assertIsNotNone(
            assignment, "Assignment does not exist or is already completed"
        )

        # POST answers (1 correct, 1 incorrect)
        submit_url = reverse("knowledgetest:quiz-submit", args=[self.tmpl.pk])
        payload = {"answers": json.dumps({"1": "A", "2": "C"})}
        resp = self.client.post(submit_url, payload)
        self.assertEqual(
            resp.status_code, 302, f"Expected redirect, got {resp.status_code}"
        )

        # Check WrittenTestAttempt
        from knowledgetest.models import WrittenTestAnswer, WrittenTestAttempt

        attempt = WrittenTestAttempt.objects.get(student=self.student)
        self.assertIsNotNone(attempt.score_percentage)
        score = (
            float(attempt.score_percentage)
            if attempt.score_percentage is not None
            else 0.0
        )
        self.assertAlmostEqual(score, 50.0)
        self.assertTrue(attempt.passed)

        # Check answer records
        answers = WrittenTestAnswer.objects.filter(attempt=attempt)
        self.assertEqual(answers.count(), 2)
        a1 = answers.get(question=self.q1)
        self.assertTrue(a1.is_correct)
        a2 = answers.get(question=self.q2)
        self.assertFalse(a2.is_correct)

    def setUp(self):
        # create a student user
        self.student = User.objects.create_user(username="student", password="pass")
        # Set membership_status to an allowed value for active_member_required
        self.student.membership_status = "Student Member"
        self.student.save()
        # create category & questions
        self.cat = QuestionCategory.objects.create(code="PRE", description="Pre-solo")
        self.q1 = Question.objects.create(
            qnum=1,
            category=self.cat,
            question_text="Q1?",
            option_a="A1",
            option_b="B1",
            option_c="C1",
            option_d="D1",
            correct_answer="A",
        )
        self.q2 = Question.objects.create(
            qnum=2,
            category=self.cat,
            question_text="Q2?",
            option_a="A2",
            option_b="B2",
            option_c="C2",
            option_d="D2",
            correct_answer="B",
        )
        # make a template and add questions in order
        self.tmpl = WrittenTestTemplate.objects.create(
            name="Pre-solo Test", pass_percentage=50
        )
        # through_defaults requires Django ≥3.2; otherwise set order manually
        self.tmpl.questions.add(self.q1, through_defaults={"order": 1})
        self.tmpl.questions.add(self.q2, through_defaults={"order": 2})

        self.client = Client(enforce_csrf_checks=False)
        self.client.login(username="student", password="pass")

        # Assign the test to the student so they can submit answers
        from knowledgetest.models import WrittenTestAssignment

        WrittenTestAssignment.objects.create(
            template=self.tmpl, student=self.student, instructor=None, completed=False
        )

    def test_start_view_renders_questions(self):
        # Ensure assignment exists
        from knowledgetest.models import WrittenTestAssignment

        self.assertTrue(
            WrittenTestAssignment.objects.filter(
                template=self.tmpl, student=self.student
            ).exists()
        )
        url = reverse("knowledgetest:quiz-start", args=[self.tmpl.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # ensure questions context is present and valid
        questions = resp.context["questions"]
        self.assertEqual(len(questions), 2)
        self.assertIn("qnum", questions[0])
        self.assertIn("option_a", questions[0])

    def test_submit_creates_attempt_and_answers(self):
        submit_url = reverse("knowledgetest:quiz-submit", args=[self.tmpl.pk])
        # 1 correct (A), 1 wrong (C)
        payload = {"answers": json.dumps({"1": "A", "2": "C"})}
        resp = self.client.post(submit_url, payload)
        # should redirect to result page
        self.assertEqual(resp.status_code, 302)
        attempt = WrittenTestAttempt.objects.get(student=self.student)
        # score = 1/2 * 100 = 50 → passes (threshold=50)
        score = (
            float(attempt.score_percentage)
            if attempt.score_percentage is not None
            else 0.0
        )
        self.assertAlmostEqual(score, 50.0)
        self.assertTrue(attempt.passed)
        # two answer records
        answers = WrittenTestAnswer.objects.filter(attempt=attempt)
        self.assertEqual(answers.count(), 2)
        a1 = answers.get(question=self.q1)
        self.assertTrue(a1.is_correct)
        a2 = answers.get(question=self.q2)
        self.assertFalse(a2.is_correct)

    def test_completion_creates_notifications_for_instructor(self):
        # Create an instructor and assign the test
        instructor = User.objects.create_user(username="instr", password="pw")
        self.tmpl.created_by = instructor
        self.tmpl.save()

        # Assign with an instructor — update the existing assignment created in setUp
        from knowledgetest.models import WrittenTestAssignment

        asn = WrittenTestAssignment.objects.get(
            template=self.tmpl, student=self.student)
        asn.instructor = instructor
        asn.save(update_fields=["instructor"])

        # Submit answers
        submit_url = reverse("knowledgetest:quiz-submit", args=[self.tmpl.pk])
        payload = {"answers": json.dumps({"1": "A", "2": "C"})}
        resp = self.client.post(submit_url, payload)
        self.assertEqual(resp.status_code, 302)

        # Instructor should have received a Notification
        notes = Notification.objects.filter(user=instructor)
        self.assertTrue(notes.exists())
        n = notes.first()
        self.assertIsNotNone(n)
        n = cast(Notification, n)
        self.assertIn("has completed the written test", n.message)

    def test_invalid_payload_returns_error(self):
        submit_url = reverse("knowledgetest:quiz-submit", args=[self.tmpl.pk])
        # malformed JSON
        resp = self.client.post(submit_url, {"answers": "{bad json"})
        # should render the start template with form errors
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid answer payload")

    def test_completion_creates_instruction_report_with_persistent_link(self):
        """Test that completing a written test creates an InstructionReport with a link to the result."""
        # Create an instructor and assign the test
        instructor = User.objects.create_user(username="instructor", password="pw")
        instructor.membership_status = "Full Member"
        instructor.save()

        self.tmpl.created_by = instructor
        self.tmpl.save()

        # Submit answers
        submit_url = reverse("knowledgetest:quiz-submit", args=[self.tmpl.pk])
        payload = {"answers": json.dumps({"1": "A", "2": "C"})}
        resp = self.client.post(submit_url, payload)
        self.assertEqual(resp.status_code, 302)

        # Check that an InstructionReport was created
        reports = InstructionReport.objects.filter(
            student=self.student, instructor=instructor)
        self.assertTrue(reports.exists())

        report = reports.first()
        self.assertIsNotNone(report)
        report = cast(InstructionReport, report)

        # Verify the report text contains test completion info and a link
        self.assertIn('Written test "Pre-solo Test" completed', report.report_text)
        self.assertIn("50%", report.report_text)
        self.assertIn("Passed", report.report_text)
        self.assertIn("View written test result", report.report_text)

        # Verify the link points to the correct attempt
        attempt = WrittenTestAttempt.objects.get(student=self.student)
        expected_url = reverse("knowledgetest:quiz-result", args=[attempt.pk])
        self.assertIn(expected_url, report.report_text)


class WrittenTestDeleteTests(TestCase):
    """Tests for the written test attempt deletion functionality."""

    def setUp(self):
        # Create users
        self.student = User.objects.create_user(username="student", password="pass")
        self.student.membership_status = "Student Member"
        self.student.save()

        self.instructor = User.objects.create_user(
            username="instructor", password="pass")
        self.instructor.membership_status = "Full Member"
        self.instructor.save()

        self.staff_user = User.objects.create_user(
            username="staff", password="pass", is_staff=True)
        self.staff_user.membership_status = "Full Member"
        self.staff_user.save()

        self.other_user = User.objects.create_user(username="other", password="pass")
        self.other_user.membership_status = "Full Member"
        self.other_user.save()

        # Create test content
        self.cat = QuestionCategory.objects.create(
            code="TEST", description="Test Category")
        self.q1 = Question.objects.create(
            qnum=1,
            category=self.cat,
            question_text="Test question?",
            option_a="Option A",
            option_b="Option B",
            option_c="Option C",
            option_d="Option D",
            correct_answer="A",
        )

        self.tmpl = WrittenTestTemplate.objects.create(
            name="Test Template",
            pass_percentage=70,
            created_by=self.instructor
        )
        self.tmpl.questions.add(self.q1, through_defaults={"order": 1})

        # Create attempt
        self.attempt = WrittenTestAttempt.objects.create(
            template=self.tmpl,
            student=self.student,
            instructor=self.instructor,
            score_percentage=85.0,
            passed=True
        )

        # Create answer
        WrittenTestAnswer.objects.create(
            attempt=self.attempt,
            question=self.q1,
            selected_answer="A",
            is_correct=True
        )

    def test_staff_can_delete_attempt(self):
        """Staff users should be able to delete any attempt."""
        self.client.login(username="staff", password="pass")

        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        resp = self.client.post(delete_url)

        # Should redirect to the student's instruction record
        expected_redirect = reverse(
            "instructors:member_instruction_record", args=[self.student.pk])
        self.assertRedirects(resp, expected_redirect)

        # Attempt should be deleted
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_instructor_can_delete_own_attempt(self):
        """The grading instructor should be able to delete attempts they graded."""
        self.client.login(username="instructor", password="pass")

        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        resp = self.client.post(delete_url)

        expected_redirect = reverse(
            "instructors:member_instruction_record", args=[self.student.pk])
        self.assertRedirects(resp, expected_redirect)

        # Attempt should be deleted
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_template_creator_can_delete_attempt(self):
        """The creator/proctor of the test template should be able to delete attempts."""
        # Create a different instructor to be the grading instructor
        grading_instructor = User.objects.create_user(
            username="grader", password="pass")
        grading_instructor.membership_status = "Full Member"
        grading_instructor.save()

        self.attempt.instructor = grading_instructor
        self.attempt.save()

        # Template creator (self.instructor) should still be able to delete
        self.client.login(username="instructor", password="pass")

        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        resp = self.client.post(delete_url)

        expected_redirect = reverse(
            "instructors:member_instruction_record", args=[self.student.pk])
        self.assertRedirects(resp, expected_redirect)

        # Attempt should be deleted
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_unauthorized_user_cannot_delete_attempt(self):
        """Users who are not staff, grading instructor, or template creator should not be able to delete."""
        self.client.login(username="other", password="pass")

        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        resp = self.client.post(delete_url)

        # Should return 403 Forbidden
        self.assertEqual(resp.status_code, 403)

        # Attempt should still exist
        self.assertTrue(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_student_can_delete_own_attempt(self):
        """Students should be able to delete their own attempts."""
        self.client.login(username="student", password="pass")

        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        resp = self.client.post(delete_url)

        # Should redirect after successful deletion
        self.assertEqual(resp.status_code, 302)

        # Attempt should be deleted
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_get_request_not_allowed(self):
        """Only POST requests should be allowed for deletion."""
        self.client.login(username="staff", password="pass")

        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        resp = self.client.get(delete_url)

        # Should return 405 Method Not Allowed
        self.assertEqual(resp.status_code, 405)

        # Attempt should still exist
        self.assertTrue(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_delete_nonexistent_attempt_returns_404(self):
        """Attempting to delete a non-existent attempt should return 404."""
        self.client.login(username="staff", password="pass")

        delete_url = reverse("knowledgetest:quiz-attempt-delete", args=[99999])
        resp = self.client.post(delete_url)

        # Should return 404 Not Found
        self.assertEqual(resp.status_code, 404)

    def test_delete_removes_related_answers(self):
        """Deleting an attempt should cascade delete related answers."""
        self.client.login(username="staff", password="pass")

        # Verify answer exists before deletion
        self.assertTrue(WrittenTestAnswer.objects.filter(attempt=self.attempt).exists())

        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        resp = self.client.post(delete_url)

        # Should redirect successfully
        self.assertEqual(resp.status_code, 302)

        # Both attempt and related answers should be deleted
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())
        self.assertFalse(WrittenTestAnswer.objects.filter(
            attempt=self.attempt).exists())

    def test_result_page_shows_delete_button_with_confirmation(self):
        """The result page should show delete button with confirmation dialog for authorized users."""
        self.client.login(username="staff", password="pass")

        result_url = reverse("knowledgetest:quiz-result", args=[self.attempt.pk])
        resp = self.client.get(result_url)

        self.assertEqual(resp.status_code, 200)

        # Check that the delete button is present
        self.assertContains(resp, "Remove Test Record")

        # Check that the confirmation dialog is in the onclick attribute
        self.assertContains(resp, "confirm('Remove this test record?")
        self.assertContains(resp, "This action cannot be undone")

        # Check that the form points to the correct delete URL
        delete_url = reverse("knowledgetest:quiz-attempt-delete",
                             args=[self.attempt.pk])
        self.assertContains(resp, f'action="{delete_url}"')

    def test_result_page_shows_pass_threshold(self):
        """The result page should show what percentage was required to pass."""
        self.client.login(username="student", password="pass")

        result_url = reverse("knowledgetest:quiz-result", args=[self.attempt.pk])
        resp = self.client.get(result_url)

        self.assertEqual(resp.status_code, 200)

        # Should show the score and the required pass percentage
        self.assertContains(resp, "85.0%")  # The attempt score
        self.assertContains(resp, "(Required: 70% to pass)")  # Template pass percentage
