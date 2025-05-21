import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from knowledgetest.models import (
    QuestionCategory, Question,
    WrittenTestTemplate, WrittenTestAttempt,
    WrittenTestAnswer
)

User = get_user_model()

class QuizFlowTests(TestCase):
    def setUp(self):
        # create a student user
        self.student = User.objects.create_user(
            username='student', password='pass'
        )
        # create category & questions
        self.cat = QuestionCategory.objects.create(
            code='PRE', description='Pre-solo'
        )
        self.q1 = Question.objects.create(
            qnum=1,
            category=self.cat,
            question_text='Q1?',
            option_a='A1', option_b='B1',
            option_c='C1', option_d='D1',
            correct_answer='A'
        )
        self.q2 = Question.objects.create(
            qnum=2,
            category=self.cat,
            question_text='Q2?',
            option_a='A2', option_b='B2',
            option_c='C2', option_d='D2',
            correct_answer='B'
        )
        # make a template and add questions in order
        self.tmpl = WrittenTestTemplate.objects.create(
            name='Pre-solo Test',
            pass_percentage=50
        )
        # through_defaults requires Django ≥3.2; otherwise set order manually
        self.tmpl.questions.add(self.q1, through_defaults={'order': 1})
        self.tmpl.questions.add(self.q2, through_defaults={'order': 2})

        self.client = Client()
        self.client.login(username='student', password='pass')

    def test_start_view_renders_questions(self):
        url = reverse('knowledgetest:quiz-start', args=[self.tmpl.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # ensure JSON context is present and valid
        data = resp.context['questions_json']
        questions = json.loads(data)
        self.assertEqual(len(questions), 2)
        self.assertIn('qnum', questions[0])
        self.assertIn('option_a', questions[0])

    def test_submit_creates_attempt_and_answers(self):
        submit_url = reverse('knowledgetest:quiz-submit', args=[self.tmpl.pk])
        # 1 correct (A), 1 wrong (C)
        payload = {'answers': json.dumps({'1': 'A', '2': 'C'})}
        resp = self.client.post(submit_url, payload)
        # should redirect to result page
        self.assertEqual(resp.status_code, 302)
        attempt = WrittenTestAttempt.objects.get(student=self.student)
        # score = 1/2 * 100 = 50 → passes (threshold=50)
        self.assertAlmostEqual(attempt.score_percentage, 50.0)
        self.assertTrue(attempt.passed)
        # two answer records
        answers = WrittenTestAnswer.objects.filter(attempt=attempt)
        self.assertEqual(answers.count(), 2)
        a1 = answers.get(question=self.q1)
        self.assertTrue(a1.is_correct)
        a2 = answers.get(question=self.q2)
        self.assertFalse(a2.is_correct)

    def test_invalid_payload_returns_error(self):
        submit_url = reverse('knowledgetest:quiz-submit', args=[self.tmpl.pk])
        # malformed JSON
        resp = self.client.post(submit_url, {'answers': '{bad json'})
        # should render the start template with form errors
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid answer payload")
