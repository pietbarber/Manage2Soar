"""
Tests for Offline Sync API endpoints.

Part of Issue #315: PWA Fully-offline Logsheet data entry
"""

import json
from datetime import date
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from logsheet.models import Airfield, Flight, Glider, Logsheet, Towplane
from members.models import Member


@pytest.fixture
def active_member(db):
    """Create an active member for testing."""
    member = Member.objects.create_user(
        username="testpilot",
        email="pilot@test.com",
        password="testpass123",
        first_name="Test",
        last_name="Pilot",
        is_active=True,
        membership_status="Full Member",
    )
    return member


@pytest.fixture
def instructor_member(db):
    """Create an instructor member for testing."""
    member = Member.objects.create_user(
        username="testinstructor",
        email="instructor@test.com",
        password="testpass123",
        first_name="Test",
        last_name="Instructor",
        is_active=True,
        membership_status="Full Member",
    )
    return member


@pytest.fixture
def airfield(db):
    """Create a test airfield."""
    return Airfield.objects.create(
        identifier="KFRR",
        name="Front Royal Warren County Airport",
        is_active=True,
    )


@pytest.fixture
def glider(db):
    """Create a test glider."""
    return Glider.objects.create(
        make="Schempp-Hirth",
        model="Discus",
        n_number="N123AB",
        competition_number="AB",
        seats=1,
        is_active=True,
        club_owned=True,
    )


@pytest.fixture
def towplane(db):
    """Create a test towplane."""
    return Towplane.objects.create(
        name="Husky",
        make="Aviat",
        model="A-1B",
        n_number="N456TP",
        is_active=True,
    )


@pytest.fixture
def logsheet(db, active_member, airfield):
    """Create a test logsheet."""
    return Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )


@pytest.fixture
def authenticated_client(db, active_member):
    """Return an authenticated client."""
    client = Client()
    client.login(username="testpilot", password="testpass123")
    return client


class TestReferenceDataEndpoint:
    """Tests for the GET /api/offline/reference-data/ endpoint."""

    def test_requires_authentication(self, db, client):
        """Unauthenticated requests should be redirected."""
        url = reverse("logsheet:api_offline_reference_data")
        response = client.get(url)
        assert response.status_code == 302  # Redirect to login

    def test_returns_json(self, db, authenticated_client):
        """Should return JSON content type."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"

    def test_includes_members(self, db, authenticated_client, active_member):
        """Response should include active members."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert data["success"] is True
        assert "members" in data
        assert len(data["members"]) >= 1
        # Check member has required fields
        member_data = next(
            (m for m in data["members"] if m["id"] == active_member.id), None
        )
        assert member_data is not None
        assert "name" in member_data
        assert "display_name" in member_data

    def test_includes_gliders(self, db, authenticated_client, glider):
        """Response should include active gliders."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert "gliders" in data
        assert len(data["gliders"]) >= 1
        glider_data = next((g for g in data["gliders"] if g["id"] == glider.id), None)
        assert glider_data is not None
        assert "display_name" in glider_data
        assert "n_number" in glider_data
        assert "seats" in glider_data

    def test_includes_towplanes(self, db, authenticated_client, towplane):
        """Response should include active towplanes."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert "towplanes" in data
        assert len(data["towplanes"]) >= 1
        towplane_data = next(
            (t for t in data["towplanes"] if t["id"] == towplane.id), None
        )
        assert towplane_data is not None
        assert "name" in towplane_data
        assert "n_number" in towplane_data

    def test_includes_airfields(self, db, authenticated_client, airfield):
        """Response should include active airfields."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert "airfields" in data
        assert len(data["airfields"]) >= 1
        airfield_data = next(
            (a for a in data["airfields"] if a["id"] == airfield.id), None
        )
        assert airfield_data is not None
        assert "identifier" in airfield_data
        assert "name" in airfield_data

    def test_includes_flight_types(self, db, authenticated_client):
        """Response should include flight type choices."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert "flight_types" in data
        assert len(data["flight_types"]) > 0
        # Check structure
        assert "value" in data["flight_types"][0]
        assert "label" in data["flight_types"][0]

    def test_includes_release_altitudes(self, db, authenticated_client):
        """Response should include release altitude choices."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert "release_altitudes" in data
        assert len(data["release_altitudes"]) > 0

    def test_includes_launch_methods(self, db, authenticated_client):
        """Response should include launch method choices."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert "launch_methods" in data
        assert len(data["launch_methods"]) > 0

    def test_includes_version(self, db, authenticated_client):
        """Response should include a version for cache invalidation."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        assert "version" in data
        assert isinstance(data["version"], int)

    def test_excludes_inactive_gliders(self, db, authenticated_client, glider):
        """Inactive gliders should not be included."""
        # Create an inactive glider
        inactive = Glider.objects.create(
            make="Old",
            model="Glider",
            n_number="N999ZZ",
            is_active=False,
        )

        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()

        glider_ids = [g["id"] for g in data["gliders"]]
        assert glider.id in glider_ids
        assert inactive.id not in glider_ids


class TestFlightsSyncEndpoint:
    """Tests for the POST /api/offline/flights/sync/ endpoint."""

    def test_requires_authentication(self, db, client):
        """Unauthenticated requests should be redirected."""
        url = reverse("logsheet:api_offline_flights_sync")
        response = client.post(
            url, data=json.dumps({"flights": []}), content_type="application/json"
        )
        assert response.status_code == 302  # Redirect to login

    def test_requires_post(self, db, authenticated_client):
        """Only POST method should be allowed."""
        url = reverse("logsheet:api_offline_flights_sync")
        response = authenticated_client.get(url)
        assert response.status_code == 405  # Method not allowed

    def test_requires_flights_array(self, db, authenticated_client):
        """Request must include flights array."""
        url = reverse("logsheet:api_offline_flights_sync")
        response = authenticated_client.post(
            url, data=json.dumps({}), content_type="application/json"
        )
        data = response.json()
        assert data["success"] is False
        assert "No flights provided" in data["error"]

    def test_create_flight_success(
        self, db, authenticated_client, logsheet, active_member, glider, airfield
    ):
        """Should successfully create a new flight."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "test-key-001",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "airfield_id": airfield.id,
                        "flight_type": "solo",
                        "launch_method": "tow",
                    },
                }
            ]
        }

        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()

        assert data["success"] is True
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "success"
        assert "serverId" in data["results"][0]

        # Verify flight was created
        flight = Flight.objects.get(id=data["results"][0]["serverId"])
        assert flight.pilot == active_member
        assert flight.glider == glider

    def test_idempotency_key_prevents_duplicates(
        self, db, authenticated_client, logsheet, active_member, glider, airfield
    ):
        """Same idempotency key should not create duplicate flights."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "test-key-duplicate",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "airfield_id": airfield.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }

        # First request
        response1 = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data1 = response1.json()
        assert data1["results"][0]["status"] == "success"
        flight_id = data1["results"][0]["serverId"]

        # Second request with same key
        response2 = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data2 = response2.json()
        assert data2["results"][0]["status"] == "duplicate"
        assert data2["results"][0]["serverId"] == flight_id

        # Only one flight should exist
        assert Flight.objects.filter(logsheet=logsheet).count() == 1

    def test_finalized_logsheet_rejected(
        self, db, authenticated_client, logsheet, active_member, glider, airfield
    ):
        """Cannot add flights to finalized logsheet."""
        logsheet.finalized = True
        logsheet.save()

        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "test-key-finalized",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "airfield_id": airfield.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }

        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()

        assert data["results"][0]["status"] == "error"
        assert "finalized" in data["results"][0]["error"].lower()

    def test_invalid_pilot_rejected(
        self, db, authenticated_client, logsheet, glider, airfield
    ):
        """Invalid pilot ID should be rejected."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "test-key-invalid-pilot",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": 99999,  # Non-existent
                        "glider_id": glider.id,
                        "airfield_id": airfield.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }

        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()

        assert data["results"][0]["status"] == "error"
        assert "not found" in data["results"][0]["error"].lower()

    def test_batch_sync_multiple_flights(
        self, db, authenticated_client, logsheet, active_member, glider, airfield
    ):
        """Should handle multiple flights in a single request."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "batch-key-001",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "airfield_id": airfield.id,
                        "flight_type": "solo",
                    },
                },
                {
                    "idempotencyKey": "batch-key-002",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "airfield_id": airfield.id,
                        "flight_type": "dual",
                    },
                },
            ]
        }

        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()

        assert data["success"] is True
        assert len(data["results"]) == 2
        assert all(r["status"] == "success" for r in data["results"])

        # Verify both flights created
        assert Flight.objects.filter(logsheet=logsheet).count() == 2

    def test_unexpected_sync_exception_does_not_leak_internal_details(
        self, db, authenticated_client, logsheet, active_member, glider, airfield
    ):
        """Unexpected sync exceptions should return a generic per-flight error message."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "test-key-exception-no-leak",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "airfield_id": airfield.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }

        with patch(
            "logsheet.api._create_flight_from_offline",
            side_effect=RuntimeError("SECRET_STACK_TRACE_DETAIL"),
        ):
            response = authenticated_client.post(
                url, data=json.dumps(payload), content_type="application/json"
            )

        data = response.json()
        assert data["success"] is True
        assert data["results"][0]["status"] == "error"
        assert (
            data["results"][0]["error"]
            == "An internal error occurred while processing this flight."
        )
        assert "SECRET_STACK_TRACE_DETAIL" not in response.content.decode("utf-8")


class TestSyncStatusEndpoint:
    """Tests for the GET /api/offline/sync-status/ endpoint."""

    def test_requires_authentication(self, db, client):
        """Unauthenticated requests should be redirected."""
        url = reverse("logsheet:api_offline_sync_status")
        response = client.get(url)
        assert response.status_code == 302

    def test_returns_status(self, db, authenticated_client, active_member):
        """Should return sync status information."""
        url = reverse("logsheet:api_offline_sync_status")
        response = authenticated_client.get(url)
        data = response.json()

        assert data["success"] is True
        assert data["online"] is True
        assert "serverTime" in data
        assert "user" in data
        assert data["user"]["id"] == active_member.id


# ============================================================
# Regression tests for PR #1118 threads 2 & 3
# ============================================================


class TestReferenceDataRoleEligibility:
    """Thread 3: offline reference data must include role-eligibility flags."""

    def test_member_flags_present(self, db, authenticated_client, active_member):
        """Each member dict should expose isPilotEligible / isPassengerEligible."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()
        member = next(m for m in data["members"] if m["id"] == active_member.id)
        assert "isPilotEligible" in member
        assert "isPassengerEligible" in member
        assert "isInstructor" in member
        assert "isTowpilot" in member

    def test_full_member_is_pilot_and_passenger_eligible(
        self, db, authenticated_client, active_member
    ):
        """'Full Member' (can_be_pilot=True) should be eligible for both roles."""
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()
        member = next(m for m in data["members"] if m["id"] == active_member.id)
        assert member["isPilotEligible"] is True
        assert member["isPassengerEligible"] is True

    def test_ineligible_pilot_status_flagged_false(self, db, authenticated_client):
        """A status with can_be_pilot=False must be flagged isPilotEligible=False."""
        from django.contrib.auth import get_user_model

        from siteconfig.models import MembershipStatus

        User = get_user_model()
        MembershipStatus.objects.get_or_create(
            name="Full Member",
            defaults={
                "is_active": True,
                "can_be_pilot": True,
                "can_be_passenger": True,
                "sort_order": 1,
            },
        )
        family, _ = MembershipStatus.objects.get_or_create(
            name="Family Member",
            defaults={
                "is_active": True,
                "can_be_pilot": False,
                "can_be_passenger": True,
                "sort_order": 50,
            },
        )
        family.can_be_pilot = False
        family.can_be_passenger = True
        family.save(update_fields=["can_be_pilot", "can_be_passenger"])
        family_member = User.objects.create_user(
            username="family-x",
            first_name="Family",
            last_name="Member",
            membership_status=family.name,
        )
        url = reverse("logsheet:api_offline_reference_data")
        response = authenticated_client.get(url)
        data = response.json()
        m = next(m for m in data["members"] if m["id"] == family_member.id)
        assert m["isPilotEligible"] is False
        assert m["isPassengerEligible"] is True


class TestFlightsSyncEligibility:
    """Thread 2: the offline sync endpoint must enforce eligibility."""

    @pytest.fixture
    def site_config(self, db):
        from siteconfig.models import SiteConfiguration

        return SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            visiting_pilot_enabled=False,
            visiting_pilot_status="Affiliate Member",
        )

    @pytest.fixture
    def ineligible_pilot(self, site_config, db):
        """A member whose status has can_be_pilot=False."""
        from django.contrib.auth import get_user_model

        from siteconfig.models import MembershipStatus

        User = get_user_model()
        MembershipStatus.objects.get_or_create(
            name="Full Member",
            defaults={
                "is_active": True,
                "can_be_pilot": True,
                "can_be_passenger": True,
                "sort_order": 1,
            },
        )
        ground, _ = MembershipStatus.objects.get_or_create(
            name="Grounded",
            defaults={
                "is_active": True,
                "can_be_pilot": False,
                "can_be_passenger": False,
                "sort_order": 90,
            },
        )
        ground.can_be_pilot = False
        ground.can_be_passenger = False
        ground.save(update_fields=["can_be_pilot", "can_be_passenger"])
        return User.objects.create_user(
            username="grounded-pilot",
            first_name="Grounded",
            last_name="Pilot",
            membership_status=ground.name,
        )

    @pytest.fixture
    def deceased_member(self, site_config, db):
        """A Deceased member (always blocked)."""
        from django.contrib.auth import get_user_model

        from siteconfig.models import MembershipStatus

        User = get_user_model()
        deceased, _ = MembershipStatus.objects.get_or_create(
            name="Deceased",
            defaults={
                "is_active": False,
                "can_be_pilot": False,
                "can_be_passenger": False,
                "sort_order": 99,
            },
        )
        deceased.can_be_pilot = False
        deceased.can_be_passenger = False
        deceased.save(update_fields=["can_be_pilot", "can_be_passenger"])
        return User.objects.create_user(
            username="deceased-pilot",
            first_name="Deceased",
            last_name="Pilot",
            membership_status=deceased.name,
        )

    @pytest.fixture
    def unqualified_towpilot(self, site_config, db):
        """A 'Full Member' without the towpilot=True flag."""
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(
            username="not-a-towpilot",
            first_name="NotTow",
            last_name="Pilot",
            membership_status="Full Member",
            towpilot=False,
        )

    def test_create_rejects_ineligible_pilot(
        self, authenticated_client, logsheet, glider, ineligible_pilot
    ):
        """Assigning a can_be_pilot=False member as pilot must be rejected."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-create-inelig-pilot",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": ineligible_pilot.id,
                        "glider_id": glider.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }
        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()
        assert data["results"][0]["status"] == "error"
        assert "not eligible to be a pilot" in data["results"][0]["error"]
        # No flight should be created.
        assert Flight.objects.filter(logsheet=logsheet).count() == 0

    def test_create_rejects_deceased_pilot(
        self, authenticated_client, logsheet, glider, deceased_member
    ):
        """Deceased members are always blocked as pilot."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-create-deceased",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": deceased_member.id,
                        "glider_id": glider.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }
        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()
        assert data["results"][0]["status"] == "error"
        assert "deceased" in data["results"][0]["error"].lower()

    def test_create_rejects_unqualified_tow_pilot(
        self,
        authenticated_client,
        logsheet,
        glider,
        active_member,
        unqualified_towpilot,
    ):
        """A member without towpilot=True must not be assignable as tow_pilot."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-create-towpilot",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "tow_pilot_id": unqualified_towpilot.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }
        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()
        assert data["results"][0]["status"] == "error"
        assert "not qualified as a tow pilot" in data["results"][0]["error"]

    def test_update_rejects_change_to_ineligible_pilot(
        self,
        authenticated_client,
        logsheet,
        glider,
        active_member,
        ineligible_pilot,
    ):
        """Updating a flight to assign an ineligible pilot must be rejected."""
        url = reverse("logsheet:api_offline_flights_sync")
        # Create a valid flight first.
        create_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-update-setup",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "flight_type": "solo",
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(create_payload), content_type="application/json"
        )
        flight_id = resp.json()["results"][0]["serverId"]

        # Now attempt to change the pilot to an ineligible member.
        update_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-update-inelig",
                    "action": "update",
                    "data": {
                        "id": flight_id,
                        "pilot_id": ineligible_pilot.id,
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(update_payload), content_type="application/json"
        )
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "not eligible to be a pilot" in data["results"][0]["error"]
        # Flight's pilot must still be the original eligible member.
        flight = Flight.objects.get(id=flight_id)
        assert flight.pilot_id == active_member.id

    def test_update_preserves_unchanged_ineligible_assignment_exception(
        self,
        authenticated_client,
        logsheet,
        glider,
        inactive_pilot,
    ):
        """An unchanged non-deceased assignment is allowed even if currently
        ineligible, per the existing-assignment exception."""

        # First create the flight with the inactive member as pilot by bypassing
        # eligibility (e.g. legacy import path). This simulates a flight that
        # already exists in the database with an inactive pilot.
        from logsheet.models import Flight

        flight = Flight.objects.create(
            logsheet=logsheet,
            pilot=inactive_pilot,
            glider=glider,
            flight_type="solo",
        )

        # Now update the flight but keep the same pilot (unchanged).
        url = reverse("logsheet:api_offline_flights_sync")
        update_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-update-unchanged",
                    "action": "update",
                    "data": {
                        "id": flight.id,
                        "pilot_id": inactive_pilot.id,
                        "notes": "touched",
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(update_payload), content_type="application/json"
        )
        data = resp.json()
        assert data["results"][0]["status"] == "success", data
        flight.refresh_from_db()
        assert flight.pilot_id == inactive_pilot.id
        assert flight.notes == "touched"

    @pytest.fixture
    def inactive_pilot(self, site_config, db):
        """A member whose status is not in the active list (inactive)."""
        from django.contrib.auth import get_user_model

        from siteconfig.models import MembershipStatus

        User = get_user_model()
        inactive, _ = MembershipStatus.objects.get_or_create(
            name="Inactive",
            defaults={
                "is_active": False,
                "can_be_pilot": False,
                "can_be_passenger": False,
                "sort_order": 10,
            },
        )
        inactive.can_be_pilot = False
        inactive.can_be_passenger = False
        inactive.save(update_fields=["can_be_pilot", "can_be_passenger"])
        return User.objects.create_user(
            username="inactive-pilot",
            first_name="Inactive",
            last_name="Pilot",
            membership_status=inactive.name,
        )
