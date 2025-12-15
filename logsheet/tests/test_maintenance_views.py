import pytest
from django.urls import reverse

from logsheet.models import MaintenanceIssue


@pytest.mark.django_db
def test_manage_logsheet_finances_view_accessible(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:manage_logsheet_finances", args=[logsheet.pk])
    )
    assert response.status_code == 200
    assert "flight_data" in response.context


@pytest.mark.django_db
def test_edit_logsheet_closeout_view(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:edit_logsheet_closeout", args=[logsheet.pk])
    )
    assert response.status_code == 200
    assert "form" in response.context
    # Issue #411: Verify tow_pilots_data is in context
    assert "tow_pilots_data" in response.context


@pytest.mark.django_db
def test_view_logsheet_closeout_view(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:view_logsheet_closeout", args=[logsheet.pk])
    )
    assert response.status_code == 200
    assert "maintenance_issues" in response.context


@pytest.mark.django_db
def test_add_maintenance_issue_success(client, active_member, glider, logsheet):
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {
            "description": "Flat tire",
            "glider": glider.pk,
        },
    )
    assert response.status_code == 302
    assert MaintenanceIssue.objects.filter(description="Flat tire").exists()


@pytest.mark.django_db
def test_add_maintenance_issue_ajax_success(client, active_member, glider, logsheet):
    """Test AJAX submission of maintenance issue returns JSON response"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {"description": "Flat tire on main gear", "glider": glider.pk},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "issue" in data
    assert data["issue"]["description"] == "Flat tire on main gear"
    assert data["issue"]["glider"] == str(glider)
    assert MaintenanceIssue.objects.filter(
        description="Flat tire on main gear"
    ).exists()


@pytest.mark.django_db
def test_add_maintenance_issue_ajax_validation_error(client, active_member, logsheet):
    """Test AJAX submission with missing aircraft returns error"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {"description": "Issue without aircraft"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "error" in data
    assert "errors" in data  # Should include detailed form errors


@pytest.mark.django_db
def test_add_maintenance_issue_ajax_grounded_flag(
    client, active_member, towplane, logsheet
):
    """Test AJAX submission with grounded flag"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {
            "description": "Engine failure",
            "towplane": towplane.pk,
            "grounded": True,
        },
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["issue"]["grounded"] is True
    issue = MaintenanceIssue.objects.get(description="Engine failure")
    assert issue.grounded is True


@pytest.mark.django_db
def test_equipment_list_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse("logsheet:equipment_list"))
    assert response.status_code == 200
    assert "gliders" in response.context


@pytest.mark.django_db
def test_maintenance_issues_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse("logsheet:maintenance_issues"))
    assert response.status_code == 200
    assert "open_issues" in response.context


@pytest.mark.django_db
def test_mark_issue_resolved_authorized(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": "Fixed brake inspection issue."},
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True


@pytest.mark.django_db
def test_resolve_maintenance_issue_post(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": "Fixed valve."},
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True


@pytest.mark.django_db
def test_maintenance_mark_resolved_requires_notes(
    client, meister_member, maintenance_issue
):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": ""},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_maintenance_mark_resolved_success(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": "Patched leak."},
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True


@pytest.mark.django_db
def test_maintenance_deadlines_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse("logsheet:maintenance_deadlines"))
    assert response.status_code == 200
    assert "deadlines" in response.context
