from datetime import date, timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from instructors.models import (
    ClubQualificationType,
    GroundInstruction,
    InstructionReport,
    MemberQualification,
)
from instructors.utils import OVERDUE_SPR_NOTIFICATION_FRAGMENT
from logsheet.models import Airfield, Flight, Glider, Logsheet
from members.models import Badge, MemberBadge
from notifications.context_processors import notifications as notifications_context
from notifications.models import Notification


def _create_finalized_instructional_flight(
    *, instructor, student, flight_date, suffix="001"
):
    airfield = Airfield.objects.create(identifier=f"T{suffix}", name=f"Test {suffix}")
    glider = Glider.objects.create(
        make="Schweizer", model="2-33", n_number=f"N{suffix}"
    )
    logsheet = Logsheet.objects.create(
        log_date=flight_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    return Flight.objects.create(
        logsheet=logsheet,
        pilot=student,
        instructor=instructor,
        glider=glider,
        flight_type="dual",
    )


@pytest.mark.django_db
def test_instruction_report_creates_notification(django_user_model):
    instructor = django_user_model.objects.create_user(username="inst1", password="pw")
    student = django_user_model.objects.create_user(username="stud1", password="pw")

    # create report
    r = InstructionReport.objects.create(
        student=student,
        instructor=instructor,
        report_date=date.today(),
        report_text="ok",
    )
    # invoke the handler explicitly (unit test for the handler logic)
    import instructors.signals as sigmod

    sigmod.notify_student_on_instruction_report(None, r, True)

    qs = Notification.objects.filter(
        user=student, message__contains=str(date.today().isoformat())
    )
    assert qs.exists()

    # updating the report should also create (or be deduped if exact same message exists)
    prev_count = Notification.objects.filter(user=student).count()
    r.report_text = "updated"
    r.save()
    sigmod.notify_student_on_instruction_report(None, r, False)
    assert Notification.objects.filter(user=student).count() >= prev_count


@pytest.mark.django_db
def test_ground_instruction_creates_notification(django_user_model):
    instructor = django_user_model.objects.create_user(username="inst2", password="pw")
    student = django_user_model.objects.create_user(username="stud2", password="pw")

    s = GroundInstruction.objects.create(
        student=student, instructor=instructor, date=date.today(), notes="good"
    )
    import instructors.signals as sigmod

    sigmod.notify_student_on_ground_instruction(None, s, True)
    assert Notification.objects.filter(
        user=student, message__contains=str(date.today().isoformat())
    ).exists()


@pytest.mark.django_db
def test_member_qualification_creates_notification(django_user_model):
    instr = django_user_model.objects.create_user(username="instq", password="pw")
    member = django_user_model.objects.create_user(username="memberq", password="pw")
    # create a qualification type so the FK constraint is satisfied
    qual_type = ClubQualificationType.objects.create(code="TESTQ", name="Test Qual")
    qual = MemberQualification.objects.create(
        member=member,
        qualification=qual_type,
        is_qualified=True,
        instructor=instr,
        date_awarded=date.today(),
    )
    import instructors.signals as sigmod

    sigmod.notify_member_on_qualification(None, qual, True)
    assert Notification.objects.filter(
        user=member, message__contains=str(date.today().isoformat())
    ).exists()


@pytest.mark.django_db
def test_member_badge_creates_notification(django_user_model):
    member = django_user_model.objects.create_user(username="mbadge", password="pw")
    badge = Badge.objects.create(name="Test Badge")
    mb = MemberBadge.objects.create(
        member=member, badge=badge, date_awarded=date.today()
    )
    import instructors.signals as sigmod

    sigmod.notify_member_on_badge(None, mb, True)
    assert Notification.objects.filter(
        user=member, message__contains=badge.name
    ).exists()


@pytest.mark.django_db
def test_overdue_reminder_dismissed_when_final_spr_completed(django_user_model):
    instructor = django_user_model.objects.create_user(
        username="inst_cleanup1", password="pw"
    )
    student = django_user_model.objects.create_user(
        username="stud_cleanup1", password="pw"
    )
    flight_date = timezone.localdate() - timedelta(days=8)

    _create_finalized_instructional_flight(
        instructor=instructor,
        student=student,
        flight_date=flight_date,
        suffix="101",
    )

    reminder = Notification.objects.create(
        user=instructor,
        message="📝 You have 1 overdue Student Progress Report(s)",
    )

    InstructionReport.objects.create(
        student=student,
        instructor=instructor,
        report_date=flight_date,
        report_text="completed",
    )

    reminder.refresh_from_db()
    assert reminder.dismissed is True


@pytest.mark.django_db
def test_overdue_reminder_not_dismissed_when_other_overdue_remains(django_user_model):
    instructor = django_user_model.objects.create_user(
        username="inst_cleanup2", password="pw"
    )
    student_one = django_user_model.objects.create_user(
        username="stud_cleanup2a", password="pw"
    )
    student_two = django_user_model.objects.create_user(
        username="stud_cleanup2b", password="pw"
    )

    first_date = timezone.localdate() - timedelta(days=8)
    second_date = timezone.localdate() - timedelta(days=9)

    _create_finalized_instructional_flight(
        instructor=instructor,
        student=student_one,
        flight_date=first_date,
        suffix="102",
    )
    _create_finalized_instructional_flight(
        instructor=instructor,
        student=student_two,
        flight_date=second_date,
        suffix="103",
    )

    reminder = Notification.objects.create(
        user=instructor,
        message="📝 You have 2 overdue Student Progress Report(s)",
    )

    InstructionReport.objects.create(
        student=student_one,
        instructor=instructor,
        report_date=first_date,
        report_text="completed one",
    )

    reminder.refresh_from_db()
    assert reminder.dismissed is False


@pytest.mark.django_db
def test_overdue_cleanup_is_instructor_scoped(django_user_model):
    instructor_one = django_user_model.objects.create_user(
        username="inst_cleanup3a", password="pw"
    )
    instructor_two = django_user_model.objects.create_user(
        username="inst_cleanup3b", password="pw"
    )
    student_one = django_user_model.objects.create_user(
        username="stud_cleanup3a", password="pw"
    )
    student_two = django_user_model.objects.create_user(
        username="stud_cleanup3b", password="pw"
    )

    first_date = timezone.localdate() - timedelta(days=8)
    second_date = timezone.localdate() - timedelta(days=9)

    _create_finalized_instructional_flight(
        instructor=instructor_one,
        student=student_one,
        flight_date=first_date,
        suffix="104",
    )
    _create_finalized_instructional_flight(
        instructor=instructor_two,
        student=student_two,
        flight_date=second_date,
        suffix="105",
    )

    reminder_one = Notification.objects.create(
        user=instructor_one,
        message="📝 You have 1 overdue Student Progress Report(s)",
    )
    reminder_two = Notification.objects.create(
        user=instructor_two,
        message="📝 You have 1 overdue Student Progress Report(s)",
    )

    InstructionReport.objects.create(
        student=student_one,
        instructor=instructor_one,
        report_date=first_date,
        report_text="completed",
    )

    reminder_one.refresh_from_db()
    reminder_two.refresh_from_db()

    assert reminder_one.dismissed is True
    assert reminder_two.dismissed is False


@pytest.mark.django_db
def test_context_processor_hides_stale_overdue_notification(django_user_model):
    instructor = django_user_model.objects.create_user(
        username="inst_cleanup4", password="pw"
    )

    stale = Notification.objects.create(
        user=instructor,
        message=f"📌 You have 1 {OVERDUE_SPR_NOTIFICATION_FRAGMENT}(s)",
        dismissed=False,
    )
    keep = Notification.objects.create(
        user=instructor,
        message="General notification",
        dismissed=False,
    )

    request = RequestFactory().get("/")
    request.user = instructor

    context = notifications_context(request)
    rendered_notifications = context["notifications"]

    assert stale not in rendered_notifications
    assert keep in rendered_notifications
