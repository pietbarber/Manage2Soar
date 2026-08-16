"""
E2E test for the written test creation page's live question count.

Regression test: the "N questions" counter uses a JS selector that only
matched <input> elements, but the weight fields render as <select>
dropdowns, so the counter always showed "0 questions" even when weights
were selected.
"""

from knowledgetest.models import Question, QuestionCategory

from .conftest import DjangoPlaywrightTestCase


class TestKnowledgeTestQuestionCount(DjangoPlaywrightTestCase):
    def _create_category_with_questions(self, code, description, count):
        category = QuestionCategory.objects.create(code=code, description=description)
        for i in range(count):
            Question.objects.create(
                qnum=1000 + i if code == "AAA" else 2000 + i,
                category=category,
                question_text=f"Question {i}",
                option_a="A",
                option_b="B",
                option_c="C",
                option_d="D",
                correct_answer="A",
            )
        return category

    def test_question_count_updates_when_selecting_weight(self):
        self._create_category_with_questions("AAA", "Category AAA", 10)

        self.create_test_member(
            username="instructor1", is_superuser=True, instructor=True
        )
        self.login(username="instructor1")

        self.page.goto(f"{self.live_server_url}/instructors/tests/create/")
        self.page.wait_for_load_state("networkidle")

        count_el = self.page.locator("#question-count")
        assert count_el.text_content().strip() == "0 questions"

        self.page.select_option('select[name="weight_AAA"]', "5")

        self.page.wait_for_function(
            "document.getElementById('question-count').textContent.trim() === '5 questions'"
        )
        assert count_el.text_content().strip() == "5 questions"

        warning_el = self.page.locator("#question-warning")
        assert "d-none" in (warning_el.get_attribute("class") or "")
