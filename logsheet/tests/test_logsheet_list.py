import pytest
from django.urls import reverse

from logsheet.models import Airfield, Logsheet, Towplane, TowplaneCloseout


@pytest.mark.django_db
def test_delete_button_not_shown_for_finalized_logsheet(client, active_member):
    airfield = Airfield.objects.create(name="Test Field")
    logsheet = Logsheet.objects.create(
        log_date="2024-01-01",
        airfield=airfield,
        created_by=active_member,
        finalized=True,
    )
    url = reverse("logsheet:index")
    client.force_login(active_member)
    response = client.get(url)
    assert response.status_code == 200
    # The delete button should not be present for finalized logsheets
    assert (
        f"action=\"{reverse('logsheet:delete', args=[logsheet.pk])}\""
        not in response.content.decode()
    )


@pytest.mark.django_db
def test_delete_button_not_shown_for_logsheet_with_towplane_closeout(
    client, active_member
):
    airfield = Airfield.objects.create(name="Test Field")
    towplane = Towplane.objects.create(n_number="N12345")
    logsheet = Logsheet.objects.create(
        log_date="2024-01-02",
        airfield=airfield,
        created_by=active_member,
        finalized=False,
    )
    TowplaneCloseout.objects.create(
        logsheet=logsheet,
        towplane=towplane,
        start_tach=100,
        end_tach=110,
        tach_time=10,
        fuel_added=20,
    )
    url = reverse("logsheet:index")
    client.force_login(active_member)
    response = client.get(url)
    assert response.status_code == 200
    # The delete button should not be present for logsheets with towplane closeouts
    assert (
        f"action=\"{reverse('logsheet:delete', args=[logsheet.pk])}\""
        not in response.content.decode()
    )


@pytest.mark.django_db
def test_year_selector_includes_current_year_when_no_current_year_logsheets(
    client, active_member
):
    """
    Test that the year selector always includes the current year, even when
    no logsheets exist for the current year. This ensures users can navigate
    to historical logsheets. (Fixes issue #466)
    """
    from datetime import datetime

    airfield = Airfield.objects.create(name="Test Field")
    # Create a logsheet from a previous year only
    Logsheet.objects.create(
        log_date="2024-06-15",
        airfield=airfield,
        created_by=active_member,
    )

    url = reverse("logsheet:index")
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200
    # The available_years context should include the current year
    available_years = list(response.context["available_years"])
    current_year = datetime.now().year
    assert current_year in available_years
    # Should also include the year of the existing logsheet
    assert 2024 in available_years
    # Current year should be first (sorted descending)
    assert available_years[0] == current_year


@pytest.mark.django_db
def test_year_selector_works_with_no_logsheets_at_all(client, active_member):
    """
    Test that the year selector shows the current year even when there are
    no logsheets in the database at all.
    """
    from datetime import datetime

    # Ensure no logsheets exist
    Logsheet.objects.all().delete()

    url = reverse("logsheet:index")
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200
    available_years = list(response.context["available_years"])
    current_year = datetime.now().year
    # Current year should be in available_years
    assert current_year in available_years
    assert len(available_years) == 1
