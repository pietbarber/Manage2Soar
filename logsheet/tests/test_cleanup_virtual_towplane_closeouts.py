"""
Tests for the cleanup_virtual_towplane_closeouts management command.

Tests that the command properly handles:
1. Dry-run mode (no deletions)
2. Real run (deletes stale closeouts)
3. SELF closeouts with club-owned gliders (preserved)
4. WINCH/OTHER closeouts (always deleted)
"""

from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command

from logsheet.models import Flight, Glider, Logsheet, Towplane, TowplaneCloseout


@pytest.fixture
def create_test_data(db, airfield, active_member):
    """Create test data for cleanup command tests."""
    # Create logsheet
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=active_member
    )

    # Create virtual towplanes
    winch = Towplane.objects.create(n_number="WINCH", name="Winch", is_active=True)
    other = Towplane.objects.create(n_number="OTHER", name="Other", is_active=True)
    self_tp = Towplane.objects.create(n_number="SELF", name="Self", is_active=True)

    # Create club-owned and private gliders
    club_glider = Glider.objects.create(
        n_number="001",
        make="ASK21",
        model="Club Glider",
        club_owned=True,
        is_active=True,
    )
    private_glider = Glider.objects.create(
        n_number="002",
        make="ASW20",
        model="Private Glider",
        club_owned=False,
        is_active=True,
    )

    return {
        "logsheet": logsheet,
        "winch": winch,
        "other": other,
        "self_tp": self_tp,
        "club_glider": club_glider,
        "private_glider": private_glider,
        "active_member": active_member,
    }


@pytest.mark.django_db
def test_dry_run_does_not_delete(create_test_data):
    """Test that dry-run mode does not delete any closeouts."""
    data = create_test_data

    # Create closeouts for virtual towplanes (these would normally be deleted)
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"], towplane=data["winch"], start_tach=100, end_tach=110
    )
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"], towplane=data["other"], start_tach=200, end_tach=210
    )

    initial_count = TowplaneCloseout.objects.count()
    assert initial_count == 2

    # Run command in dry-run mode
    out = StringIO()
    call_command("cleanup_virtual_towplane_closeouts", "--dry-run", stdout=out)

    # Verify no closeouts were deleted
    final_count = TowplaneCloseout.objects.count()
    assert final_count == initial_count
    assert "DRY RUN MODE" in out.getvalue()
    assert "Found 2 stale closeouts" in out.getvalue()
    assert "No closeouts were deleted" in out.getvalue()


@pytest.mark.django_db
def test_real_run_deletes_stale_closeouts(create_test_data):
    """Test that real run deletes stale WINCH and OTHER closeouts."""
    data = create_test_data

    # Create stale closeouts (WINCH and OTHER should always be deleted)
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"], towplane=data["winch"], start_tach=100, end_tach=110
    )
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"], towplane=data["other"], start_tach=200, end_tach=210
    )

    initial_count = TowplaneCloseout.objects.count()
    assert initial_count == 2

    # Run command (real run, no --dry-run flag)
    out = StringIO()
    call_command("cleanup_virtual_towplane_closeouts", stdout=out)

    # Verify stale closeouts were deleted
    final_count = TowplaneCloseout.objects.count()
    assert final_count == 0
    assert "Successfully deleted 2 stale virtual towplane closeouts" in out.getvalue()


@pytest.mark.django_db
def test_self_closeout_preserved_with_club_glider(create_test_data):
    """Test that SELF closeouts are preserved when used with club-owned gliders."""
    from datetime import time

    data = create_test_data

    # Create a SELF flight with a club-owned glider
    Flight.objects.create(
        logsheet=data["logsheet"],
        glider=data["club_glider"],
        towplane=data["self_tp"],
        pilot=data["active_member"],
        landing_time=time(12, 0),
        launch_time=time(12, 0),
        release_altitude=0,
    )

    # Create SELF closeout (should be preserved because club glider is used)
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"],
        towplane=data["self_tp"],
        start_tach=300,
        end_tach=310,
    )

    initial_count = TowplaneCloseout.objects.count()
    assert initial_count == 1

    # Run command
    out = StringIO()
    call_command("cleanup_virtual_towplane_closeouts", stdout=out)

    # Verify SELF closeout was NOT deleted
    final_count = TowplaneCloseout.objects.count()
    assert final_count == 1
    assert "No stale virtual towplane closeouts found" in out.getvalue()


@pytest.mark.django_db
def test_self_closeout_deleted_with_private_glider(create_test_data):
    """Test that SELF closeouts are deleted when used with private gliders."""
    from datetime import time

    data = create_test_data

    # Create a SELF flight with a private glider
    Flight.objects.create(
        logsheet=data["logsheet"],
        glider=data["private_glider"],
        towplane=data["self_tp"],
        pilot=data["active_member"],
        landing_time=time(12, 0),
        launch_time=time(12, 0),
        release_altitude=0,
    )

    # Create SELF closeout (should be deleted because only private glider is used)
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"],
        towplane=data["self_tp"],
        start_tach=300,
        end_tach=310,
    )

    initial_count = TowplaneCloseout.objects.count()
    assert initial_count == 1

    # Run command
    out = StringIO()
    call_command("cleanup_virtual_towplane_closeouts", stdout=out)

    # Verify SELF closeout WAS deleted
    final_count = TowplaneCloseout.objects.count()
    assert final_count == 0
    assert "Successfully deleted 1 stale virtual towplane closeouts" in out.getvalue()


@pytest.mark.django_db
def test_winch_and_other_always_deleted(create_test_data):
    """Test that WINCH and OTHER closeouts are always deleted regardless of glider type."""
    from datetime import time

    data = create_test_data

    # Create flights with WINCH and OTHER (with club gliders, doesn't matter)
    Flight.objects.create(
        logsheet=data["logsheet"],
        glider=data["club_glider"],
        towplane=data["winch"],
        pilot=data["active_member"],
        landing_time=time(12, 0),
        launch_time=time(12, 0),
        release_altitude=0,
    )
    Flight.objects.create(
        logsheet=data["logsheet"],
        glider=data["club_glider"],
        towplane=data["other"],
        pilot=data["active_member"],
        landing_time=time(12, 0),
        launch_time=time(12, 0),
        release_altitude=0,
    )

    # Create closeouts for WINCH and OTHER (should always be deleted)
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"], towplane=data["winch"], start_tach=100, end_tach=110
    )
    TowplaneCloseout.objects.create(
        logsheet=data["logsheet"], towplane=data["other"], start_tach=200, end_tach=210
    )

    initial_count = TowplaneCloseout.objects.count()
    assert initial_count == 2

    # Run command
    out = StringIO()
    call_command("cleanup_virtual_towplane_closeouts", stdout=out)

    # Verify WINCH and OTHER closeouts were deleted
    final_count = TowplaneCloseout.objects.count()
    assert final_count == 0
    assert "Successfully deleted 2 stale virtual towplane closeouts" in out.getvalue()


@pytest.mark.django_db
def test_no_closeouts_to_delete(create_test_data):
    """Test command handles case with no stale closeouts."""
    # Don't create any closeouts

    out = StringIO()
    call_command("cleanup_virtual_towplane_closeouts", stdout=out)

    assert "No stale virtual towplane closeouts found" in out.getvalue()
