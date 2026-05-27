import json
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from instructors.models import (
    ClubQualificationType,
    SyllabusDocument,
    TrainingLesson,
    TrainingPhase,
)
from knowledgetest.models import (
    Question,
    QuestionCategory,
    WrittenTestTemplate,
    WrittenTestTemplateQuestion,
)
from members.models import Badge


class Command(BaseCommand):
    help = "Bootstrap starter data for a new tenant using create-missing-only semantics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            default="skyline-default",
            help="Starter data profile name under loaddata/starter_profiles",
        )
        parser.add_argument(
            "--manifest",
            default=None,
            help="Optional path to a profile manifest JSON file",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing any data",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail fast on malformed fixtures or missing dependencies",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.strict = options["strict"]
        self.base_dir = Path(settings.BASE_DIR)
        self.user_model = get_user_model()

        self.summary = defaultdict(lambda: {"created": 0, "existing": 0, "skipped": 0})
        self.phase_pk_map = {}
        self.category_code_set = set()
        self.question_pk_set = set()
        self.template_pk_map = {}

        manifest_path = self._resolve_manifest_path(
            options["manifest"], options["profile"]
        )
        manifest = self._load_json(manifest_path)

        fixtures = manifest.get("fixtures") if isinstance(manifest, dict) else None
        if not isinstance(fixtures, list) or not fixtures:
            raise CommandError("Manifest must contain a non-empty 'fixtures' list")

        self.stdout.write(
            self.style.NOTICE(
                f"Bootstrapping starter data from profile '{manifest.get('name', options['profile'])}'"
            )
        )
        self.stdout.write(f"Manifest: {manifest_path}")
        self.stdout.write(f"Mode: {'DRY RUN' if self.dry_run else 'APPLY'}")

        if self.dry_run:
            for fixture_ref in fixtures:
                self._process_fixture_reference(fixture_ref)
        else:
            with transaction.atomic():
                for fixture_ref in fixtures:
                    self._process_fixture_reference(fixture_ref)

        self._print_summary()

    def _resolve_manifest_path(self, explicit_manifest, profile):
        if explicit_manifest:
            manifest_path = Path(explicit_manifest)
            if not manifest_path.is_absolute():
                manifest_path = self.base_dir / manifest_path
        else:
            manifest_path = (
                self.base_dir / "loaddata" / "starter_profiles" / f"{profile}.json"
            )

        if not manifest_path.exists():
            raise CommandError(f"Manifest not found: {manifest_path}")
        return manifest_path

    def _resolve_fixture_path(self, fixture_ref):
        fixture_path = Path(fixture_ref)
        if not fixture_path.is_absolute():
            fixture_path = self.base_dir / fixture_path
        if not fixture_path.exists():
            raise CommandError(f"Fixture file not found: {fixture_path}")
        return fixture_path

    def _load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {path}: {exc}") from exc

    def _process_fixture_reference(self, fixture_ref):
        fixture_path = self._resolve_fixture_path(fixture_ref)
        self.stdout.write(f"Processing fixture: {fixture_path}")

        entries = self._load_json(fixture_path)
        if not isinstance(entries, list):
            self._handle_error(f"Fixture must contain a JSON list: {fixture_path}")
            return

        for index, entry in enumerate(entries, start=1):
            self._process_entry(entry, fixture_path, index)

    def _process_entry(self, entry, fixture_path, index):
        if not isinstance(entry, dict):
            self._handle_error(
                f"Entry {index} in {fixture_path} is not a JSON object; skipping"
            )
            return

        model_label = entry.get("model")
        fields = entry.get("fields", {})
        pk = entry.get("pk")

        if not model_label or not isinstance(fields, dict):
            self._handle_error(
                f"Entry {index} in {fixture_path} missing 'model' or 'fields'; skipping"
            )
            return

        handlers = {
            "members.badge": self._load_badge,
            "instructors.clubqualificationtype": self._load_qualification_type,
            "instructors.trainingphase": self._load_training_phase,
            "instructors.traininglesson": self._load_training_lesson,
            "instructors.syllabusdocument": self._load_syllabus_document,
            "knowledgetest.questioncategory": self._load_question_category,
            "knowledgetest.question": self._load_question,
            "knowledgetest.writtentesttemplate": self._load_written_test_template,
            "knowledgetest.writtentesttemplatequestion": self._load_written_test_template_question,
        }

        handler = handlers.get(model_label)
        if not handler:
            self.summary[model_label]["skipped"] += 1
            return

        handler(pk, fields)

    def _load_badge(self, _pk, fields):
        model_name = "members.badge"
        name = fields.get("name")
        if not name:
            self._handle_error("Badge fixture entry missing name")
            self.summary[model_name]["skipped"] += 1
            return

        defaults = {
            "image": fields.get("image", ""),
            "description": fields.get("description", ""),
            "order": fields.get("order", 0),
        }

        self._create_missing(Badge, {"name": name}, defaults, model_name)

    def _load_qualification_type(self, _pk, fields):
        model_name = "instructors.clubqualificationtype"
        code = fields.get("code")
        if not code:
            self._handle_error("ClubQualificationType fixture entry missing code")
            self.summary[model_name]["skipped"] += 1
            return

        defaults = {
            "name": fields.get("name", ""),
            "icon": fields.get("icon", ""),
            "applies_to": fields.get("applies_to", "both"),
            "is_obsolete": fields.get("is_obsolete", False),
            "tooltip": fields.get("tooltip", ""),
        }

        self._create_missing(
            ClubQualificationType, {"code": code}, defaults, model_name
        )

    def _load_training_phase(self, _pk, fields):
        model_name = "instructors.trainingphase"
        number = fields.get("number")
        name = fields.get("name")
        if number is None or not name:
            self._handle_error("TrainingPhase fixture entry missing number or name")
            self.summary[model_name]["skipped"] += 1
            return

        phase_obj = self._create_missing(
            TrainingPhase,
            {"number": number},
            {"name": name},
            model_name,
            return_instance=True,
        )

        if _pk is not None:
            # Keep fixture PK mapping so related fixture rows can resolve dependencies.
            self.phase_pk_map[_pk] = phase_obj or "planned"

    def _load_training_lesson(self, _pk, fields):
        model_name = "instructors.traininglesson"
        code = fields.get("code")
        if not code:
            self._handle_error("TrainingLesson fixture entry missing code")
            self.summary[model_name]["skipped"] += 1
            return

        phase_obj = None
        phase_pk = fields.get("phase")
        phase_exists = False
        if phase_pk is not None:
            phase_obj = self.phase_pk_map.get(phase_pk)
            phase_exists = phase_obj is not None
            if phase_obj == "planned":
                phase_obj = None
            if phase_obj is None:
                phase_obj = TrainingPhase.objects.filter(pk=phase_pk).first()
                phase_exists = phase_exists or phase_obj is not None
            if not phase_exists:
                self._handle_error(
                    f"TrainingLesson '{code}' references missing TrainingPhase pk={phase_pk}"
                )
                self.summary[model_name]["skipped"] += 1
                return

            if self.dry_run and phase_obj is None:
                self.summary[model_name]["created"] += 1
                return

        defaults = {
            "title": fields.get("title", ""),
            "description": fields.get("description", ""),
            "far_requirement": fields.get("far_requirement", ""),
            "pts_reference": fields.get("pts_reference", ""),
            "phase": phase_obj,
        }

        self._create_missing(TrainingLesson, {"code": code}, defaults, model_name)

    def _load_syllabus_document(self, _pk, fields):
        model_name = "instructors.syllabusdocument"
        slug = fields.get("slug")
        if not slug:
            self._handle_error("SyllabusDocument fixture entry missing slug")
            self.summary[model_name]["skipped"] += 1
            return

        defaults = {
            "title": fields.get("title", ""),
            "content": fields.get("content", ""),
        }

        self._create_missing(SyllabusDocument, {"slug": slug}, defaults, model_name)

    def _load_question_category(self, pk, fields):
        model_name = "knowledgetest.questioncategory"
        code = pk or fields.get("code")
        if not code:
            self._handle_error("QuestionCategory fixture entry missing code")
            self.summary[model_name]["skipped"] += 1
            return

        self._create_missing(
            QuestionCategory,
            {"code": code},
            {"description": fields.get("description", "")},
            model_name,
        )
        self.category_code_set.add(code)

    def _load_question(self, pk, fields):
        model_name = "knowledgetest.question"
        qnum = pk if pk is not None else fields.get("qnum")
        if qnum is None:
            self._handle_error("Question fixture entry missing qnum")
            self.summary[model_name]["skipped"] += 1
            return

        category_code = fields.get("category")
        category = QuestionCategory.objects.filter(pk=category_code).first()
        category_exists = (
            category is not None or category_code in self.category_code_set
        )
        if not category_exists:
            self._handle_error(
                f"Question {qnum} references missing QuestionCategory '{category_code}'"
            )
            self.summary[model_name]["skipped"] += 1
            return

        if self.dry_run and category is None:
            # Category is planned in this run, but not in DB yet.
            self.summary[model_name]["created"] += 1
            self.question_pk_set.add(qnum)
            return

        updated_by = None
        updated_by_id = fields.get("updated_by")
        if updated_by_id:
            updated_by = self.user_model.objects.filter(pk=updated_by_id).first()

        defaults = {
            "category": category,
            "question_text": fields.get("question_text", ""),
            "option_a": fields.get("option_a", ""),
            "option_b": fields.get("option_b", ""),
            "option_c": fields.get("option_c", ""),
            "option_d": fields.get("option_d", ""),
            "correct_answer": fields.get("correct_answer", "A"),
            "explanation": fields.get("explanation", ""),
            "last_updated": fields.get("last_updated"),
            "updated_by": updated_by,
            "media": fields.get("media") or None,
        }

        self._create_missing(Question, {"qnum": qnum}, defaults, model_name)
        self.question_pk_set.add(qnum)

    def _load_written_test_template(self, pk, fields):
        model_name = "knowledgetest.writtentesttemplate"
        name = fields.get("name")
        if not name:
            self._handle_error("WrittenTestTemplate fixture entry missing name")
            self.summary[model_name]["skipped"] += 1
            return

        created_by = None
        created_by_id = fields.get("created_by")
        if created_by_id:
            created_by = self.user_model.objects.filter(pk=created_by_id).first()

        defaults = {
            "description": fields.get("description", ""),
            "pass_percentage": fields.get("pass_percentage", "100.00"),
            "time_limit": fields.get("time_limit"),
            "created_by": created_by,
        }

        template_obj = self._create_missing(
            WrittenTestTemplate,
            {"name": name},
            defaults,
            model_name,
            return_instance=True,
        )

        if pk is not None:
            self.template_pk_map[pk] = template_obj or "planned"

    def _load_written_test_template_question(self, _pk, fields):
        model_name = "knowledgetest.writtentesttemplatequestion"
        template_ref = fields.get("template")
        question_ref = fields.get("question")

        template_obj = self.template_pk_map.get(template_ref)
        template_exists = template_obj is not None
        if template_obj == "planned":
            template_obj = None
        if template_obj is None and template_ref is not None:
            template_obj = WrittenTestTemplate.objects.filter(pk=template_ref).first()
            template_exists = template_exists or template_obj is not None

        question_obj = Question.objects.filter(pk=question_ref).first()
        question_exists = (
            question_obj is not None or question_ref in self.question_pk_set
        )

        if not template_exists or not question_exists:
            self._handle_error(
                "WrittenTestTemplateQuestion references missing template or question"
            )
            self.summary[model_name]["skipped"] += 1
            return

        if self.dry_run and (template_obj is None or question_obj is None):
            # Relationship is valid within the run plan, but one or both rows are not
            # in the database yet, so we cannot query existence for this through row.
            self.summary[model_name]["created"] += 1
            return

        defaults = {"order": fields.get("order", 0)}
        self._create_missing(
            WrittenTestTemplateQuestion,
            {"template": template_obj, "question": question_obj},
            defaults,
            model_name,
        )

    def _create_missing(
        self,
        model_cls,
        lookup,
        defaults,
        model_name,
        return_instance=False,
    ):
        existing = model_cls.objects.filter(**lookup).first()
        if existing:
            self.summary[model_name]["existing"] += 1
            return existing if return_instance else None

        if self.dry_run:
            self.summary[model_name]["created"] += 1
            return None

        obj = model_cls.objects.create(**lookup, **defaults)
        self.summary[model_name]["created"] += 1
        return obj if return_instance else None

    def _handle_error(self, message):
        if self.strict:
            raise CommandError(message)
        self.stderr.write(self.style.WARNING(message))

    def _print_summary(self):
        self.stdout.write(self.style.SUCCESS("Bootstrap summary:"))
        for model_name in sorted(self.summary.keys()):
            counts = self.summary[model_name]
            self.stdout.write(
                f"  {model_name}: created={counts['created']} existing={counts['existing']} skipped={counts['skipped']}"
            )
