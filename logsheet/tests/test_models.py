import pytest
from datetime import date
from logsheet.models import Logsheet, MaintenanceIssue, Airfield, Glider

@pytest.mark.django_db
def test_logsheet_str_representation(logsheet):
    assert str(logsheet) == f"{logsheet.log_date} @ {logsheet.airfield}"

@pytest.mark.django_db
def test_logsheet_default_finalized_false(logsheet):
    assert logsheet.finalized is False

@pytest.mark.django_db
def test_maintenance_issue_str_representation(glider):
    issue = MaintenanceIssue.objects.create(
        description="Flat tire",
        glider=glider,
        resolved=False
    )
    expected = f"{glider} - Open - Flat tire"
    assert str(issue) == expected

@pytest.mark.django_db
def test_maintenance_issue_default_resolved_false(glider):
    issue = MaintenanceIssue.objects.create(
        description="Battery issue",
        glider=glider
    )
    assert issue.resolved is False

@pytest.mark.django_db
def test_airfield_str_representation():
    airfield = Airfield.objects.create(identifier="W99", name="Winchester Airport")
    assert str(airfield) == "W99 – Winchester Airport"
