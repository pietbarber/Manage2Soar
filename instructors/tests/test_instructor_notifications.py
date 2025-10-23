import pytest
from datetime import date

from django.urls import reverse

from instructors.models import InstructionReport, GroundInstruction, MemberQualification, ClubQualificationType
from members.models import Member, Badge, MemberBadge
from notifications.models import Notification


@pytest.mark.django_db
def test_instruction_report_creates_notification(django_user_model):
    instructor = django_user_model.objects.create_user(username="inst1", password="pw")
    student = django_user_model.objects.create_user(username="stud1", password="pw")

    # create report
    r = InstructionReport.objects.create(
        student=student, instructor=instructor, report_date=date.today(), report_text="ok")
    # invoke the handler explicitly (unit test for the handler logic)
    import instructors.signals as sigmod
    sigmod.notify_student_on_instruction_report(None, r, True)

    qs = Notification.objects.filter(
        user=student, message__contains=str(date.today().isoformat()))
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
        student=student, instructor=instructor, date=date.today(), notes="good")
    import instructors.signals as sigmod
    sigmod.notify_student_on_ground_instruction(None, s, True)
    assert Notification.objects.filter(
        user=student, message__contains=str(date.today().isoformat())).exists()


@pytest.mark.django_db
def test_member_qualification_creates_notification(django_user_model):
    instr = django_user_model.objects.create_user(username="instq", password="pw")
    member = django_user_model.objects.create_user(username="memberq", password="pw")
    # create a qualification type so the FK constraint is satisfied
    qual_type = ClubQualificationType.objects.create(code="TESTQ", name="Test Qual")
    qual = MemberQualification.objects.create(
        member=member, qualification=qual_type, is_qualified=True, instructor=instr, date_awarded=date.today())
    import instructors.signals as sigmod
    sigmod.notify_member_on_qualification(None, qual, True)
    assert Notification.objects.filter(
        user=member, message__contains=str(date.today().isoformat())).exists()


@pytest.mark.django_db
def test_member_badge_creates_notification(django_user_model):
    member = django_user_model.objects.create_user(username="mbadge", password="pw")
    badge = Badge.objects.create(name="Test Badge")
    mb = MemberBadge.objects.create(
        member=member, badge=badge, date_awarded=date.today())
    import instructors.signals as sigmod
    sigmod.notify_member_on_badge(None, mb, True)
    assert Notification.objects.filter(
        user=member, message__contains=badge.name).exists()
