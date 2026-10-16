"""Seed instruction reports + lesson scores for the seeded dual training flights.

Companion to ``seed_sample_data``: it finds every dual (training) flight in the
local dev database — identified by ``instructor IS NOT NULL`` — and creates,
for each unique (student, instructor, date) combination:

- one ``InstructionReport`` with a short pilot-themed instructor essay, and
- ``LessonScore`` rows that simulate realistic training progression, tied to
  the student's first solo flight:
  * **Before the first solo** the student works through the syllabus in
    order — new lessons start at "1" (Introduced) and are bumped to
    "2" (Practiced) then "3" (Solo Standard) as they accumulate repeats.
    The last pre-solo report is finalized so that **every solo-required
    (``far_requirement``) lesson is at least "3"**, i.e. the student reaches
    **100% solo_progress** by the time they fly their first solo.
  * **After the first solo** the student's dual-flight reports score 2–4
    lessons at **"4" (Checkride Standard)**, reflecting the post-solo /
    checkride phase of training.

Safety (defense in depth, mirrors ``seed_sample_data``):
- **Dry-run by default**: without ``--run`` the command only prints what it
  would do and exits — it writes nothing.
- **Localhost guard**: even with ``--run`` it refuses to proceed unless the
  default DB host is localhost/127.0.0.1 (or ``--i-meant-it`` is passed).
- Idempotent by default: it clears previously-seeded reports (reports whose
  student is a seeded ``@email.invalid`` member) and then regenerates.
  ``--skip-wipe`` appends instead.
- Runs inside a single transaction.
- The ``notify_student_on_instruction_report`` and ``instruction_report_saved``
  signals are disconnected during seeding (no notification spam; the
  ``StudentProgressSnapshot`` is refreshed once per student at the end).

Usage:
    python manage.py seed_instruction_reports              # DRY RUN (prints only)
    python manage.py seed_instruction_reports --run        # wipe + regenerate
    python manage.py seed_instruction_reports --run --seed 42    # reproducible
"""

import random

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.signals import post_save

# --- Seeding configuration -------------------------------------------------

EMAIL_DOMAIN = "email.invalid"  # seeded members all use this domain

# Pilot-themed sentence pool for instructor report essays. 3–4 are picked
# per report and wrapped in <p> tags.
SENTENCE_POOL = [
    "The student demonstrated solid aileron control during the downwind leg.",
    "Approach stability improved noticeably from the previous session.",
    "The student needs to focus on making timely, clear callouts.",
    "Tow release was smooth and the transition to glide was well managed.",
    "Energy management on the first circuit was better than last time.",
    "The student is beginning to anticipate stall parameters rather than react.",
    "Crosswind correction is coming along but still needs refinement.",
    "The student flew a crisp pattern with good altitude discipline.",
    "Trim usage improved; fewer micro-corrections were needed on the thermal legs.",
    "The student should keep practicing flare timing before the next solo.",
    "Good judgment on thermalling decisions — climbed where the air was good.",
    "Spotted another ship and maintained safe separation throughout the flight.",
    "The student handled the landing rollout with better rudder discipline.",
    "Communication with the tow pilot was clear and professional.",
]

# Progression tuning: how many new (intro) lessons per flight at each stage.
EARLY_STAGE_END = 3  # flights 1..3
MID_STAGE_END = 12  # flights 4..12; flights 13+ are "late"


def _score_for_seen_count(seen_count: int) -> str:
    """Map prior-exposure count to the score for this exposure.

    0 times before -> "1" (Introduced)
    1 time before  -> "2" (Practiced)
    2+ times before -> "3" (Solo Standard) — the cap for sample data.
    """
    if seen_count == 0:
        return "1"
    if seen_count == 1:
        return "2"
    return "3"


def _plan_lesson_scores(
    rnd: random.Random,
    lessons: list,
    student_flight_index: int,
    seen_counts: dict,
    syllabus_cursor: int,
) -> tuple[list, int]:
    """Decide which (lesson, score) pairs a given dual flight should record.

    ``lessons`` must be the full syllabus in ``sort_key`` order.
    Mutates ``seen_counts`` (lesson_id -> exposures) in place.
    Returns ``(pairs, new_cursor)`` where ``pairs`` is a list of
    ``(TrainingLesson, score)`` tuples (2–4 long) and ``new_cursor`` is the
    syllabus position the caller should pass on the next flight.
    """
    n = len(lessons)

    # Decide the (new, seen) split based on where we are in the student's
    # training history. student_flight_index is 0-based.
    if student_flight_index < EARLY_STAGE_END:
        # Early: introduce new lessons, no bumps yet.
        new_wanted = min(3, max(2, n - syllabus_cursor))
        seen_wanted = 0
    elif student_flight_index < MID_STAGE_END:
        # Mid: mix of new and bump.
        new_wanted = 1 + (1 if rnd.random() < 0.5 else 0)
        seen_wanted = 2 + (1 if rnd.random() < 0.5 else 0) - new_wanted
        seen_wanted = max(1, seen_wanted)
    else:
        # Late: mostly bumps, occasionally a new lesson.
        seen_wanted = 2 + (1 if rnd.random() < 0.5 else 0)
        new_wanted = 1 if rnd.random() < 0.4 else 0

    # New lessons: taken in syllabus order from the cursor.
    new_lessons = []
    while len(new_lessons) < new_wanted and syllabus_cursor < n:
        new_lessons.append(lessons[syllabus_cursor])
        syllabus_cursor += 1

    # Bumps: prefer lessons with the FEWEST exposures (they're closest to
    # advancing). Tiers are randomised within, so a student doesn't always
    # re-fly the exact same lesson next.
    bump_lessons = []
    if seen_wanted:
        by_count: dict = {}
        for l in lessons:
            c = seen_counts.get(l.id, 0)
            if c > 0:
                by_count.setdefault(c, []).append(l)
        still_needed = seen_wanted
        for count in sorted(by_count):  # fewest exposures first
            if still_needed <= 0:
                break
            tier = by_count[count]
            take = min(len(tier), still_needed)
            bump_lessons.extend(rnd.sample(tier, take))
            still_needed -= take

    # Assemble: bumps first (they carry the progression), then new lessons.
    pairs = [(l, _score_for_seen_count(seen_counts[l.id])) for l in bump_lessons]
    pairs += [(l, "1") for l in new_lessons]

    # Guarantee at least 2 pairs: top up with new lessons from the cursor.
    while len(pairs) < 2 and syllabus_cursor < n:
        pairs.append((lessons[syllabus_cursor], "1"))
        syllabus_cursor += 1

    pairs = pairs[:4]

    # Record the exposures for next time.
    for l, _ in pairs:
        seen_counts[l.id] = seen_counts.get(l.id, 0) + 1
    return pairs, syllabus_cursor


def _make_report_text(rnd: random.Random) -> str:
    sentences = rnd.sample(SENTENCE_POOL, k=min(3, len(SENTENCE_POOL)))
    if rnd.random() < 0.5:
        extra = rnd.choice(SENTENCE_POOL)
        if extra not in sentences:
            sentences.append(extra)
    return "".join(f"<p>{s}</p>" for s in sentences)


def _pick_post_solo_lessons(
    rnd: random.Random, lessons: list, seen_counts: dict
) -> list:
    """Pick the 2–4 lessons to score at "4" on a post-first-solo dual flight.

    Prefers lessons the student has already been exposed to (the ones being
    brought up to checkride standard); falls back to any syllabus lesson if
    the student has no prior exposures yet.
    """
    wanted = 2 + rnd.randint(0, 2)  # 2..4
    pool = [l for l in lessons if seen_counts.get(l.id, 0) > 0] or list(lessons)
    take = min(wanted, len(pool))
    return rnd.sample(pool, take) if take else []


class Command(BaseCommand):
    help = (
        "Seed instruction reports + lesson scores for dual training flights "
        "in the LOCAL dev database (localhost/127.0.0.1 only)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--run",
            action="store_true",
            help=(
                "REQUIRED to actually write data. Without this flag the command "
                "only prints what it would do and exits (dry-run)."
            ),
        )
        parser.add_argument(
            "--skip-wipe",
            action="store_true",
            help="Append instead of clearing previously-seeded instruction reports.",
        )
        parser.add_argument(
            "--i-meant-it",
            action="store_true",
            help="Override the localhost-only safety guard (use with extreme care).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional RNG seed for reproducible essay/score data.",
        )

    def handle(self, *args, **options):
        from instructors.models import InstructionReport, StudentProgressSnapshot
        from instructors.signals import (
            instruction_report_saved,
            notify_student_on_instruction_report,
        )
        from logsheet.models import Flight
        from members.models import Member

        # -- Localhost guard (runs FIRST, before any DB access). -------------
        # Pure settings inspection; safe to run in dry-run mode too.
        host = (settings.DATABASES.get("default", {}).get("HOST") or "").strip()
        if (
            host
            and host not in {"localhost", "127.0.0.1"}
            and not options["i_meant_it"]
        ):
            self.stderr.write(
                self.style.ERROR(
                    f"\nABORT: refusing to seed against DB host '{host}'.\n"
                    "This command is intended for the LOCAL dev database only "
                    "(localhost/127.0.0.1).\n"
                    "If you truly intend to seed this database, re-run with "
                    "--i-meant-it.\n"
                )
            )
            raise SystemExit(1)
        if host:
            self.stdout.write(
                self.style.WARNING(f"Target DB host: {host or '(default)'}")
            )

        # -- Prerequisite checks (read-only, safe in dry-run too). -----------
        dual_count = (
            Flight.objects.filter(instructor__isnull=False)
            .select_related("pilot", "instructor", "logsheet")
            .count()
        )
        if dual_count == 0:
            self.stderr.write(
                self.style.ERROR(
                    "\nNo dual (training) flights found in the database.\n"
                    "Run `python manage.py seed_sample_data --run` first, or "
                    "load real flight data.\n"
                )
            )
            return

        from instructors.models import TrainingLesson

        lesson_count = TrainingLesson.objects.count()
        if lesson_count == 0:
            self.stderr.write(
                self.style.ERROR(
                    "\nNo TrainingLesson rows found in the database.\n"
                    "The syllabus must be loaded first (e.g. via "
                    "`import_legacy_syllabus` or `loaddata`).\n"
                )
            )
            return

        # -- Group dual flights into sessions -------------------------------
        # A "session" is one (student, instructor, date) combination — the
        # unique key of InstructionReport. A student may have several dual
        # flights with the same instructor on the same day; those merge into
        # ONE report.
        flights = list(
            Flight.objects.filter(instructor__isnull=False)
            .select_related("pilot", "instructor", "logsheet")
            .order_by("logsheet__log_date", "launch_time", "id")
        )
        per_student: dict = {}  # student_id -> list of session dicts
        for f in flights:
            if f.pilot_id is None or f.instructor_id is None:
                continue
            session_key = (f.instructor_id, f.logsheet.log_date)
            sessions = per_student.setdefault(f.pilot_id, {})
            if session_key not in sessions:
                sessions[session_key] = {
                    "instructor_id": f.instructor_id,
                    "report_date": f.logsheet.log_date,
                    "n_flights": 0,
                }
            sessions[session_key]["n_flights"] += 1

        # Convert to a per-student chronological list of sessions.
        session_lists = {}
        for student_id, sessions in per_student.items():
            ordered = sorted(sessions.values(), key=lambda s: s["report_date"])
            session_lists[student_id] = ordered
        per_student = session_lists

        n_sessions = sum(len(v) for v in per_student.values())

        # -- Dry-run guard: without --run, print what we'd do and exit. ------
        if not options["run"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis command would create instruction reports + lesson "
                    "scores for:\n"
                )
            )
            self.stdout.write(
                f"  • {len(per_student)} student(s) with "
                f"{dual_count} dual training flight(s)\n"
            )
            self.stdout.write(
                f"  • {n_sessions} instruction report(s) "
                "(one per student/instructor/date)\n"
            )
            self.stdout.write(
                "  • Pre-solo reports: 1 → 2 → 3, solo-ready (100% of "
                "solo-required lessons at ≥3) before the first solo\n"
            )
            self.stdout.write(
                "  • Post-solo reports: 2–4 lessons scored at 4 "
                "(Checkride Standard)\n"
            )
            self.stdout.write(
                f"  • Pilot-themed instructor essays (3–4 sentences each)\n"
            )
            if not options["skip_wipe"]:
                existing_reports = self._count_existing_reports()
                if existing_reports:
                    self.stdout.write(
                        f"  • Would first WIPE {existing_reports} existing "
                        f"seeded report(s) and their lesson scores\n"
                    )
            self.stdout.write(
                self.style.WARNING(
                    "\nThis is a DRY RUN. No data was written.\n"
                    "To actually create the reports, re-run with --run:\n"
                    f"  python manage.py seed_instruction_reports --run\n"
                    f"  python manage.py seed_instruction_reports --run --seed 42   # reproducible\n"
                )
            )
            return

        rnd = random.Random(options["seed"])

        # -- Disconnect InstructionReport signals during seeding. -------------
        # The receivers were registered with sender=InstructionReport, so we
        # must disconnect with the same sender to match.
        post_save.disconnect(instruction_report_saved, sender=InstructionReport)
        post_save.disconnect(
            notify_student_on_instruction_report, sender=InstructionReport
        )

        # -- Do the work in one transaction. ---------------------------------
        # student_stats is initialised before the with-block so the summary
        # section (outside the block) can read it even if the transaction
        # fails and we bail early.
        student_stats: dict = {}

        with transaction.atomic():
            from instructors.models import LessonScore, TrainingLesson
            from instructors.utils import update_student_progress_snapshot

            if not options["skip_wipe"]:
                self._wipe(InstructionReport, LessonScore)

            lessons = list(
                TrainingLesson.objects.order_by("sort_key").only(
                    "id", "code", "title", "sort_key", "far_requirement"
                )
            )

            total_reports = 0
            total_scores = 0

            for student_id, student_sessions in per_student.items():
                # Find the student's first solo flight (if any) so we can tie
                # the scoring to their training timeline.
                first_solo_date = (
                    Flight.objects.filter(pilot_id=student_id, flight_type="solo")
                    .order_by("logsheet__log_date")
                    .values_list("logsheet__log_date", flat=True)
                    .first()
                )
                # Index of the last dual session on-or-before the first solo.
                # A dual on the solo day is still part of pre-solo training
                # (it's the training that leads up to the solo), so it is
                # capped at "3" and carries the solo-readiness pass; only
                # sessions strictly AFTER the first solo score "4". If the
                # student never solos, every session is pre-solo and the final
                # one carries the solo-readiness pass.
                if first_solo_date is None:
                    last_pre_solo_index = len(student_sessions) - 1
                else:
                    pre = [
                        i
                        for i, s in enumerate(student_sessions)
                        if s["report_date"] <= first_solo_date
                    ]
                    last_pre_solo_index = max(pre) if pre else -1

                seen_counts = {}
                syllabus_cursor = 0
                student_reports = 0
                student_scores = 0
                highest_score_seen = "0"

                def _record(score):
                    nonlocal total_scores, student_scores, highest_score_seen
                    student_scores += 1
                    total_scores += 1
                    if score > highest_score_seen:
                        highest_score_seen = score

                for session_index, session in enumerate(student_sessions):
                    is_solo_ready = session_index == last_pre_solo_index
                    is_post_solo = session_index > last_pre_solo_index

                    # Create the report (get_or_create for idempotency).
                    report, created = InstructionReport.objects.get_or_create(
                        student_id=student_id,
                        instructor_id=session["instructor_id"],
                        report_date=session["report_date"],
                        defaults={"report_text": _make_report_text(rnd)},
                    )
                    student_reports += 1
                    total_reports += 1

                    if is_post_solo:
                        # Post-solo: the student is now in the checkride phase,
                        # so re-work previously-flown lessons up to "4".
                        for lesson in _pick_post_solo_lessons(
                            rnd, lessons, seen_counts
                        ):
                            LessonScore.objects.update_or_create(
                                report=report,
                                lesson_id=lesson.id,
                                defaults={"score": "4"},
                            )
                            seen_counts[lesson.id] = seen_counts.get(lesson.id, 0) + 1
                            _record("4")
                    else:
                        # Pre-solo (and the solo-ready session): normal
                        # 1 -> 2 -> 3 progression.
                        pairs, syllabus_cursor = _plan_lesson_scores(
                            rnd,
                            lessons,
                            student_flight_index=session_index,
                            seen_counts=seen_counts,
                            syllabus_cursor=syllabus_cursor,
                        )
                        for lesson, score in pairs:
                            LessonScore.objects.update_or_create(
                                report=report,
                                lesson_id=lesson.id,
                                defaults={"score": score},
                            )
                            _record(score)

                        # Solo-readiness pass on the last pre-solo report:
                        # bump every solo-required lesson to "3" so the student
                        # is 100% solo-ready by their first solo flight.
                        if is_solo_ready:
                            for lesson in lessons:
                                if lesson.far_requirement:
                                    LessonScore.objects.update_or_create(
                                        report=report,
                                        lesson_id=lesson.id,
                                        defaults={"score": "3"},
                                    )
                                    if "3" > highest_score_seen:
                                        highest_score_seen = "3"

                student_stats[student_id] = {
                    "reports": student_reports,
                    "scores": student_scores,
                    "highest_score": highest_score_seen,
                }

            # -- Refresh the StudentProgressSnapshot once per student. --------
            for student_id in per_student:
                try:
                    update_student_progress_snapshot(Member.objects.get(pk=student_id))
                except Member.DoesNotExist:
                    pass

        # -- Summary. -----------------------------------------------------------
        self.stdout.write(
            self.style.SUCCESS("\n--- Instruction report seed summary ---")
        )
        for student_id, stats in student_stats.items():
            try:
                student = Member.objects.get(pk=student_id)
                name = student.full_display_name
            except Member.DoesNotExist:
                name = f"<student #{student_id}>"
            highest = stats["highest_score"]
            highest_label = {
                "1": "Introduced",
                "2": "Practiced",
                "3": "Solo Standard",
                "4": "Checkride Standard",
                "!": "Needs Attention",
            }.get(highest, "n/a")
            # Look up the snapshot for solo_progress.
            try:
                snap = StudentProgressSnapshot.objects.get(student_id=student_id)
                solo_pct = f"{snap.solo_progress * 100:.0f}%"
            except Exception:
                solo_pct = "n/a"
            self.stdout.write(
                f"  {name}: {stats['reports']} report(s), "
                f"{stats['scores']} lesson score(s), "
                f"highest={highest_label}, solo_progress={solo_pct}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {total_reports} report(s), {total_scores} lesson score(s) created."
            )
        )

    # ------------------------------------------------------------------
    # Wipe (idempotency)
    # ------------------------------------------------------------------
    def _wipe(self, InstructionReport, LessonScore):
        from members.models import Member

        seeded_ids = list(
            Member.objects.filter(email__endswith=EMAIL_DOMAIN).values_list(
                "id", flat=True
            )
        )
        if not seeded_ids:
            self.stdout.write(
                self.style.WARNING("  No seeded students found — nothing to wipe.")
            )
            return

        # Delete lesson scores first (FK), then the reports.
        scores_deleted, _ = LessonScore.objects.filter(
            report__student_id__in=seeded_ids
        ).delete()
        reports_deleted, _ = InstructionReport.objects.filter(
            student_id__in=seeded_ids
        ).delete()

        self.stdout.write(
            self.style.WARNING(
                f"  Wiped {reports_deleted} instruction report(s) and "
                f"{scores_deleted} lesson score(s) for seeded students."
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _count_existing_reports(self):
        from instructors.models import InstructionReport

        return InstructionReport.objects.filter(
            student__email__endswith=EMAIL_DOMAIN
        ).count()
