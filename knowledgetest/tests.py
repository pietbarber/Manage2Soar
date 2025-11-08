import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from instructors.models import InstructionReport
from knowledgetest.models import (
    Question,
    QuestionCategory,
    TestPreset,
    WrittenTestAnswer,
    WrittenTestAssignment,
    WrittenTestAttempt,
    WrittenTestTemplate,
)

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

    def test_invalid_payload_returns_error(self):
        submit_url = reverse("knowledgetest:quiz-submit", args=[self.tmpl.pk])
        # malformed JSON
        resp = self.client.post(submit_url, {"answers": "{bad json"})
        # should render the start template with form errors
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid answer payload")


class WrittenTestDeleteTests(TestCase):
    """Test cases for written test deletion functionality"""

    def setUp(self):
        # Create test users
        self.student = User.objects.create_user(username="student", password="pass")
        self.student.membership_status = "Student Member"
        self.student.save()

        self.instructor = User.objects.create_user(
            username="instructor", password="pass"
        )
        self.instructor.membership_status = "Full Member"
        self.instructor.is_staff = True
        self.instructor.save()

        self.other_user = User.objects.create_user(username="other", password="pass")
        self.other_user.membership_status = "Full Member"
        self.other_user.save()

        # Create test data
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

        self.tmpl = WrittenTestTemplate.objects.create(
            name="Test Template", pass_percentage=70
        )
        self.tmpl.questions.add(self.q1, through_defaults={"order": 1})

        # Create attempt
        self.attempt = WrittenTestAttempt.objects.create(
            student=self.student,
            template=self.tmpl,
            instructor=self.instructor,
            score_percentage=80.0,
            passed=True,
        )

        self.assignment = WrittenTestAssignment.objects.create(
            template=self.tmpl,
            student=self.student,
            instructor=self.instructor,
            completed=True,
            attempt=self.attempt,
        )

        # Create instruction report
        self.instruction_report = InstructionReport.objects.create(
            student=self.student,
            instructor=self.instructor,
            report_date="2024-01-01",
            report_text="Test instruction",
        )

    def test_anonymous_user_cannot_delete(self):
        """Anonymous users should be redirected to login"""
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_student_can_delete_own_attempt(self):
        """Students should be able to delete their own attempts"""
        self.client.login(username="student", password="pass")
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_instructor_can_delete_student_attempt(self):
        """Instructors should be able to delete their students' attempts"""
        self.client.login(username="instructor", password="pass")
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_other_student_cannot_delete(self):
        """Other students should not be able to delete attempts"""
        self.client.login(username="other", password="pass")
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_staff_can_delete_any_attempt(self):
        """Staff users should be able to delete any attempt"""
        staff_user = User.objects.create_user(
            username="staff", password="pass", membership_status="Full Member"
        )
        staff_user.is_staff = True
        staff_user.is_superuser = True  # This ensures active_member_required passes
        staff_user.save()

        self.client.login(username="staff", password="pass")
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_delete_cascades_to_answers(self):
        """Deleting an attempt should cascade to delete related answers"""
        # Create an answer for the attempt
        WrittenTestAnswer.objects.create(
            attempt=self.attempt, question=self.q1, selected_answer="A", is_correct=True
        )

        self.client.login(username="student", password="pass")
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())
        self.assertFalse(
            WrittenTestAnswer.objects.filter(attempt=self.attempt).exists()
        )

    def test_instruction_report_persists_after_attempt_deletion(self):
        """InstructionReport should remain valid after attempt deletion (independent entities)"""
        self.client.login(username="student", password="pass")
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=self.attempt.pk).exists())

        # Instruction report should still exist (they are independent)
        self.instruction_report.refresh_from_db()
        self.assertIsNotNone(self.instruction_report)

    def test_get_request_shows_confirmation_page(self):
        """GET request should show confirmation page"""
        self.client.login(username="student", password="pass")
        url = reverse("knowledgetest:quiz-attempt-delete", args=[self.attempt.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Are you sure")
        self.assertContains(response, self.attempt.template.name)

    def test_completion_creates_test_attempt(self):
        """Test that completing a test creates a WrittenTestAttempt correctly"""
        # Create a fresh student and assignment for this test
        new_student = User.objects.create_user(username="newstudent", password="pass")
        new_student.membership_status = "Student Member"
        new_student.save()

        assignment = WrittenTestAssignment.objects.create(
            template=self.tmpl,
            student=new_student,
            instructor=self.instructor,
            completed=False,
        )

        # Login as the new student
        self.client.login(username="newstudent", password="pass")

        # Submit the test
        submit_url = reverse("knowledgetest:quiz-submit", args=[self.tmpl.pk])
        payload = {"answers": json.dumps({"1": "A"})}
        response = self.client.post(submit_url, payload)

        # Check that attempt was created
        attempt = WrittenTestAttempt.objects.get(student=new_student)
        self.assertIsNotNone(attempt)
        self.assertTrue(attempt.passed)  # Should pass with 100% correct

        # Now delete the attempt and verify it's gone
        delete_url = reverse("knowledgetest:quiz-attempt-delete", args=[attempt.pk])
        delete_response = self.client.post(delete_url)
        self.assertEqual(delete_response.status_code, 302)

        # Attempt should be deleted
        self.assertFalse(WrittenTestAttempt.objects.filter(pk=attempt.pk).exists())


class TestPresetTests(TestCase):
    """Test cases for TestPreset model and functionality"""

    def setUp(self):
        # Clear existing presets from migration data for clean testing
        TestPreset.objects.all().delete()

        # Create test categories
        self.cat_gf = QuestionCategory.objects.create(
            code="GF", description="Ground Fundamentals"
        )
        self.cat_st = QuestionCategory.objects.create(
            code="ST", description="Soaring Technique"
        )
        self.cat_wx = QuestionCategory.objects.create(code="WX", description="Weather")

    def test_create_test_preset(self):
        """Test creating a basic test preset"""
        preset = TestPreset.objects.create(
            name="Test Preset",
            description="A test preset for unit testing",
            category_weights={"GF": 5, "ST": 3, "WX": 2},
            is_active=True,
            sort_order=50,
        )

        self.assertEqual(preset.name, "Test Preset")
        self.assertEqual(preset.description, "A test preset for unit testing")
        self.assertEqual(preset.category_weights, {"GF": 5, "ST": 3, "WX": 2})
        self.assertTrue(preset.is_active)
        self.assertEqual(preset.sort_order, 50)

    def test_preset_unique_name(self):
        """Test that preset names must be unique"""
        TestPreset.objects.create(name="Unique Test", is_active=True)

        with self.assertRaises(Exception):  # Should raise IntegrityError
            TestPreset.objects.create(name="Unique Test", is_active=False)

    def test_preset_str_method(self):
        """Test the string representation of TestPreset"""
        preset = TestPreset.objects.create(name="String Test", is_active=True)
        self.assertEqual(str(preset), "String Test")

    def test_preset_defaults(self):
        """Test default values for TestPreset fields"""
        preset = TestPreset.objects.create(name="Default Test")

        self.assertTrue(preset.is_active)  # Default should be True
        self.assertEqual(preset.sort_order, 100)  # Default should be 100
        self.assertEqual(preset.description, "")  # Default should be empty string
        self.assertEqual(preset.category_weights, {})  # Default should be empty dict
        self.assertIsNotNone(preset.created_at)
        self.assertIsNotNone(preset.updated_at)

    def test_preset_ordering(self):
        """Test that presets are ordered by sort_order then name"""
        preset_c = TestPreset.objects.create(name="C Preset", sort_order=30)
        preset_a = TestPreset.objects.create(name="A Preset", sort_order=10)
        preset_b = TestPreset.objects.create(name="B Preset", sort_order=20)

        presets = list(TestPreset.objects.all())
        self.assertEqual(presets[0], preset_a)
        self.assertEqual(presets[1], preset_b)
        self.assertEqual(presets[2], preset_c)

    def test_preset_ordering_by_name(self):
        """Test that presets with same sort_order are ordered by name"""
        preset_z = TestPreset.objects.create(name="Z Preset", sort_order=10)
        preset_a = TestPreset.objects.create(name="A Preset", sort_order=10)
        preset_m = TestPreset.objects.create(name="M Preset", sort_order=10)

        presets = list(TestPreset.objects.all())
        self.assertEqual(presets[0], preset_a)
        self.assertEqual(presets[1], preset_m)
        self.assertEqual(presets[2], preset_z)

    def test_get_active_presets(self):
        """Test the get_active_presets class method"""
        TestPreset.objects.create(name="Active 1", is_active=True, sort_order=10)
        TestPreset.objects.create(name="Active 2", is_active=True, sort_order=20)
        TestPreset.objects.create(name="Inactive 1", is_active=False, sort_order=15)
        TestPreset.objects.create(name="Inactive 2", is_active=False, sort_order=25)

        active_presets = list(TestPreset.get_active_presets())
        self.assertEqual(len(active_presets), 2)
        self.assertEqual(active_presets[0].name, "Active 1")
        self.assertEqual(active_presets[1].name, "Active 2")

    def test_get_presets_as_dict(self):
        """Test the get_presets_as_dict class method"""
        TestPreset.objects.create(
            name="Dict Test 1",
            is_active=True,
            sort_order=10,
            category_weights={"GF": 5, "ST": 3},
        )
        TestPreset.objects.create(
            name="Dict Test 2",
            is_active=True,
            sort_order=20,
            category_weights={"WX": 2},
        )
        TestPreset.objects.create(
            name="Inactive Dict", is_active=False, category_weights={"GF": 10}
        )

        presets_dict = TestPreset.get_presets_as_dict()

        self.assertEqual(len(presets_dict), 2)
        self.assertIn("Dict Test 1", presets_dict)
        self.assertIn("Dict Test 2", presets_dict)
        self.assertNotIn("Inactive Dict", presets_dict)
        self.assertEqual(presets_dict["Dict Test 1"], {"GF": 5, "ST": 3})
        self.assertEqual(presets_dict["Dict Test 2"], {"WX": 2})

    def test_get_total_questions(self):
        """Test the get_total_questions method"""
        preset_with_questions = TestPreset.objects.create(
            name="Questions Test", category_weights={"GF": 10, "ST": 5, "WX": 3}
        )
        preset_empty = TestPreset.objects.create(name="Empty Test", category_weights={})

        self.assertEqual(preset_with_questions.get_total_questions(), 18)
        self.assertEqual(preset_empty.get_total_questions(), 0)

    def test_preset_deletion_no_protection(self):
        """Test that presets can be deleted (no automatic protection)"""
        # Create a preset and a template that might reference it
        preset = TestPreset.objects.create(name="Deletable Preset", is_active=True)
        WrittenTestTemplate.objects.create(
            name="Test using Deletable Preset data", pass_percentage=70
        )

        # Deletion should succeed - no automatic protection
        preset.delete()

        # Preset should be gone
        self.assertFalse(TestPreset.objects.filter(name="Deletable Preset").exists())

    def test_preset_deletion_success(self):
        """Test that unused presets can be deleted successfully"""
        preset = TestPreset.objects.create(
            name="Another Deletable Preset", is_active=True
        )

        # Should be able to delete without error
        preset.delete()

        # Preset should be gone
        self.assertFalse(
            TestPreset.objects.filter(name="Another Deletable Preset").exists()
        )

    def test_bulk_delete_optimization(self):
        """Test that bulk delete uses values_list for efficiency"""
        # Create multiple test presets
        for i in range(3):
            TestPreset.objects.create(
                name=f"Bulk Delete Test {i}",
                description=f"Test preset {i} for bulk deletion",
                is_active=True,
            )

        # Verify they exist
        self.assertEqual(
            TestPreset.objects.filter(name__startswith="Bulk Delete Test").count(), 3
        )

        # Test that we can efficiently get names and delete
        queryset = TestPreset.objects.filter(name__startswith="Bulk Delete Test")

        # This is the optimized approach used in delete_queryset
        deleted_names = list(queryset.values_list("name", flat=True))
        self.assertEqual(len(deleted_names), 3)
        self.assertIn("Bulk Delete Test 0", deleted_names)
        self.assertIn("Bulk Delete Test 1", deleted_names)
        self.assertIn("Bulk Delete Test 2", deleted_names)

        # Test the delete operation
        count_deleted, _ = queryset.delete()
        self.assertEqual(count_deleted, 3)

        # Verify all were deleted
        self.assertEqual(
            TestPreset.objects.filter(name__startswith="Bulk Delete Test").count(), 0
        )


class TestPresetViewIntegrationTests(TestCase):
    """Test integration between TestPreset and views"""

    def setUp(self):
        # Clear existing presets from migration data for clean testing
        TestPreset.objects.all().delete()

        self.user = User.objects.create_user(username="testuser", password="pass")
        self.user.membership_status = "Full Member"
        self.user.is_staff = True
        self.user.save()

        # Create test categories
        self.cat_gf = QuestionCategory.objects.create(
            code="GF", description="Ground Fundamentals"
        )
        self.cat_st = QuestionCategory.objects.create(
            code="ST", description="Soaring Technique"
        )

        # Create test presets
        self.preset_active = TestPreset.objects.create(
            name="Active Test",
            description="Active preset for testing",
            category_weights={"GF": 5, "ST": 3},
            is_active=True,
            sort_order=10,
        )
        self.preset_inactive = TestPreset.objects.create(
            name="Inactive Test",
            description="Inactive preset for testing",
            category_weights={"GF": 2},
            is_active=False,
            sort_order=20,
        )

    def test_get_presets_function(self):
        """Test that get_presets() returns active presets from database"""
        from knowledgetest.views import get_presets

        presets = get_presets()

        # Should include active preset but not inactive
        self.assertIn("Active Test", presets)
        self.assertNotIn("Inactive Test", presets)
        self.assertEqual(presets["Active Test"], {"GF": 5, "ST": 3})

    def test_create_test_view_context(self):
        """Test that CreateWrittenTestView loads presets correctly"""
        self.client.login(username="testuser", password="pass")

        url = reverse("knowledgetest:create")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("presets", response.context)
        self.assertIn("preset_objects", response.context)

        # Should have active presets
        preset_names = response.context["presets"]
        self.assertIn("Active Test", preset_names)
        self.assertNotIn("Inactive Test", preset_names)

    def test_create_test_with_preset_parameter(self):
        """Test that preset parameter correctly loads preset data"""
        self.client.login(username="testuser", password="pass")

        # Use the "Active Test" preset we created in setUp
        url = reverse("knowledgetest:create") + "?preset=Active%20Test"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]

        # Check that preset weights are loaded into form fields
        # Active Test preset has GF=5, ST=3 according to setUp
        weight_gf_field = form.fields.get("weight_GF")
        weight_st_field = form.fields.get("weight_ST")

        # The form should have the initial values from our preset
        self.assertIsNotNone(weight_gf_field)
        self.assertIsNotNone(weight_st_field)
        self.assertEqual(weight_gf_field.initial, 5)
        self.assertEqual(weight_st_field.initial, 3)
