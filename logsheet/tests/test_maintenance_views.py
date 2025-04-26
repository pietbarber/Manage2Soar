import pytest
from django.urls import reverse
from logsheet.models import MaintenanceIssue

@pytest.mark.django_db
def test_manage_logsheet_finances_view_accessible(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(reverse('logsheet:manage_logsheet_finances', args=[logsheet.pk]))
    assert response.status_code == 200
    assert "flight_data" in response.context

@pytest.mark.django_db
def test_edit_logsheet_closeout_view(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(reverse('logsheet:edit_logsheet_closeout', args=[logsheet.pk]))
    assert response.status_code == 200
    assert "form" in response.context

@pytest.mark.django_db
def test_view_logsheet_closeout_view(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(reverse('logsheet:view_logsheet_closeout', args=[logsheet.pk]))
    assert response.status_code == 200
    assert "maintenance_issues" in response.context

@pytest.mark.django_db
def test_add_maintenance_issue_success(client, active_member, glider, logsheet):
    client.force_login(active_member)
    response = client.post(reverse('logsheet:add_maintenance_issue', args=[logsheet.pk]), {
        "description": "Flat tire",
        "glider": glider.pk,
    })
    assert response.status_code == 302
    assert MaintenanceIssue.objects.filter(description="Flat tire").exists()

@pytest.mark.django_db
def test_equipment_list_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse('logsheet:equipment_list'))
    assert response.status_code == 200
    assert "gliders" in response.context

@pytest.mark.django_db
def test_maintenance_issues_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse('logsheet:maintenance_issues'))
    assert response.status_code == 200
    assert "open_issues" in response.context

@pytest.mark.django_db
def test_mark_issue_resolved_authorized(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse('logsheet:maintenance_mark_resolved', args=[maintenance_issue.pk]),
        {"resolution_notes": "Fixed brake inspection issue."}
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True

@pytest.mark.django_db
def test_resolve_maintenance_issue_post(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse('logsheet:maintenance_mark_resolved', args=[maintenance_issue.pk]),
        {"resolution_notes": "Fixed valve."}
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True


@pytest.mark.django_db
def test_maintenance_mark_resolved_requires_notes(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(reverse('logsheet:maintenance_mark_resolved', args=[maintenance_issue.pk]), {
        "resolution_notes": ""
    })
    assert response.status_code == 400

@pytest.mark.django_db
def test_maintenance_mark_resolved_success(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(reverse('logsheet:maintenance_mark_resolved', args=[maintenance_issue.pk]), {
        "resolution_notes": "Patched leak."
    })
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True

@pytest.mark.django_db
def test_maintenance_deadlines_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse('logsheet:maintenance_deadlines'))
    assert response.status_code == 200
    assert "deadlines" in response.context
