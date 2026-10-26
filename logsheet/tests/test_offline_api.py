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

    # ------------------------------------------------------------------
    # Thread fef: the update path must validate the passenger role too.
    # ------------------------------------------------------------------

    @pytest.fixture
    def deceased_passenger(self, site_config, db):
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
            username="deceased-pax",
            first_name="Deceased",
            last_name="Pax",
            membership_status=deceased.name,
        )

    def test_update_rejects_change_to_deceased_passenger(
        self,
        authenticated_client,
        logsheet,
        glider,
        active_member,
        deceased_passenger,
    ):
        """Changing a flight's passenger to a Deceased member must be rejected."""
        url = reverse("logsheet:api_offline_flights_sync")
        create_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-upd-pax-setup",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "flight_type": "passenger",
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(create_payload), content_type="application/json"
        )
        flight_id = resp.json()["results"][0]["serverId"]

        update_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-upd-pax-deceased",
                    "action": "update",
                    "data": {"id": flight_id, "passenger_id": deceased_passenger.id},
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(update_payload), content_type="application/json"
        )
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "deceased" in data["results"][0]["error"].lower()
        flight = Flight.objects.get(id=flight_id)
        assert flight.passenger_id is None

    def test_update_rejects_change_to_ineligible_passenger(
        self,
        authenticated_client,
        logsheet,
        glider,
        active_member,
        ineligible_pilot,
    ):
        """Changing a flight's passenger to a can_be_passenger=False member
        must be rejected (mirrors the create path)."""
        url = reverse("logsheet:api_offline_flights_sync")
        create_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-upd-pax2-setup",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "glider_id": glider.id,
                        "flight_type": "passenger",
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(create_payload), content_type="application/json"
        )
        flight_id = resp.json()["results"][0]["serverId"]

        update_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-upd-pax2-ineligible",
                    "action": "update",
                    "data": {"id": flight_id, "passenger_id": ineligible_pilot.id},
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(update_payload), content_type="application/json"
        )
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "not eligible to be a passenger" in data["results"][0]["error"]

    def test_update_preserves_unchanged_passenger_exception(
        self, authenticated_client, logsheet, glider, active_member
    ):
        """An unchanged non-deceased passenger keeps the exception, so an
        unrelated edit still succeeds.  The passenger is a *distinct* member
        from the pilot (pilot == passenger is now rejected by the
        participant-combination rule)."""
        from django.contrib.auth import get_user_model

        passenger = get_user_model().objects.create_user(
            username="upd-pax-exception",
            first_name="Upd",
            last_name="Pax",
            membership_status="Full Member",
        )
        url = reverse("logsheet:api_offline_flights_sync")
        create_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-upd-pax3-setup",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "passenger_id": passenger.id,
                        "glider_id": glider.id,
                        "flight_type": "passenger",
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(create_payload), content_type="application/json"
        )
        flight_id = resp.json()["results"][0]["serverId"]

        # Touch only the notes; the (unchanged) passenger must be retained.
        update_payload = {
            "flights": [
                {
                    "idempotencyKey": "elig-upd-pax3-unchanged",
                    "action": "update",
                    "data": {"id": flight_id, "notes": "still here"},
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(update_payload), content_type="application/json"
        )
        data = resp.json()
        assert data["results"][0]["status"] == "success", data
        flight = Flight.objects.get(id=flight_id)
        assert flight.passenger_id == passenger.id
        assert flight.notes == "still here"


# ============================================================
# Regression tests for PR #1118 thread feT (reference-data flags)
# ============================================================


class TestReferenceDataVisitingAndStatusFlags:
    """The role-eligibility flags must mirror the sync validator's
    visiting-pilot and allowed-status restrictions so offline clients are not
    offered assignments that cannot synchronize."""

    def test_visiting_disabled_excludes_instructor_and_towpilot_flags(
        self, db, authenticated_client
    ):
        from django.contrib.auth import get_user_model

        from siteconfig.models import MembershipStatus, SiteConfiguration

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
        visiting, _ = MembershipStatus.objects.get_or_create(
            name="Affiliate Member",
            defaults={
                "is_active": True,
                "can_be_pilot": True,
                "can_be_passenger": True,
                "sort_order": 5,
            },
        )
        visiting.can_be_pilot = True
        visiting.can_be_passenger = True
        visiting.save(update_fields=["can_be_pilot", "can_be_passenger"])
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            visiting_pilot_enabled=False,
            visiting_pilot_status="Affiliate Member",
        )
        visiting_instr = User.objects.create_user(
            username="v-instr",
            first_name="V",
            last_name="Instr",
            membership_status="Affiliate Member",
            instructor=True,
        )
        visiting_tp = User.objects.create_user(
            username="v-tp",
            first_name="V",
            last_name="Tp",
            membership_status="Affiliate Member",
            towpilot=True,
        )
        url = reverse("logsheet:api_offline_reference_data")
        data = authenticated_client.get(url).json()
        instr = next(m for m in data["members"] if m["id"] == visiting_instr.id)
        tp = next(m for m in data["members"] if m["id"] == visiting_tp.id)
        assert instr["isInstructor"] is False
        assert tp["isTowpilot"] is False
        assert tp["isPilotEligible"] is False
        assert tp["isPassengerEligible"] is False

    def test_inactive_status_excluded_from_instructor_and_towpilot_flags(
        self, db, authenticated_client
    ):
        from django.contrib.auth import get_user_model

        from siteconfig.models import MembershipStatus, SiteConfiguration

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
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
        )
        # A status with the role flag set but a status that is neither active,
        # visiting, nor "Inactive" — i.e. outside the validator's allowed set.
        former, _ = MembershipStatus.objects.get_or_create(
            name="Former Member",
            defaults={"is_active": False, "sort_order": 20},
        )
        former_instr = User.objects.create_user(
            username="former-instr",
            first_name="Former",
            last_name="Instr",
            membership_status=former.name,
            instructor=True,
        )
        url = reverse("logsheet:api_offline_reference_data")
        data = authenticated_client.get(url).json()
        m = next(mm for mm in data["members"] if mm["id"] == former_instr.id)
        assert m["isInstructor"] is False

    def test_active_instructor_and_towpilot_flags_true(
        self, db, authenticated_client, active_member
    ):
        """A Full Member with the role flags should be advertised as
        instructor / tow pilot eligible."""
        from django.contrib.auth import get_user_model

        from siteconfig.models import SiteConfiguration

        User = get_user_model()
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
        )
        instr = User.objects.create_user(
            username="act-instr",
            first_name="Act",
            last_name="Instr",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
        )
        url = reverse("logsheet:api_offline_reference_data")
        data = authenticated_client.get(url).json()
        m = next(mm for mm in data["members"] if mm["id"] == instr.id)
        assert m["isInstructor"] is True
        assert m["isTowpilot"] is True
        assert m["isPilotEligible"] is True
        assert m["isPassengerEligible"] is True

    def test_instructor_status_not_offered_as_towpilot(self, db, authenticated_client):
        """The special 'Instructor' status allowance applies only to the
        instructor flag. A member with an inactive 'Instructor' status and
        towpilot=True must NOT be advertised as tow-pilot eligible (the sync
        validator rejects it), even though the same status grants the
        instructor flag."""
        from django.contrib.auth import get_user_model

        from siteconfig.models import MembershipStatus, SiteConfiguration

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
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
        )
        # An INACTIVE status named exactly "Instructor" (the special allowance
        # status) that is not otherwise active/visiting/"Inactive".
        instr_status, _ = MembershipStatus.objects.get_or_create(
            name="Instructor", defaults={"is_active": False, "sort_order": 30}
        )
        instr_status.is_active = False
        instr_status.save(update_fields=["is_active"])
        instr_tp = User.objects.create_user(
            username="instr-status-tp",
            first_name="InstrStatus",
            last_name="Tp",
            membership_status="Instructor",
            towpilot=True,
        )
        instr_only = User.objects.create_user(
            username="instr-status-only",
            first_name="InstrStatus",
            last_name="Only",
            membership_status="Instructor",
            instructor=True,
        )
        url = reverse("logsheet:api_offline_reference_data")
        data = authenticated_client.get(url).json()
        m = next(mm for mm in data["members"] if mm["id"] == instr_tp.id)
        # Tow-pilot flag must be False: the "Instructor" allowance is not part
        # of the tow-pilot allowed set.
        assert m["isTowpilot"] is False
        # The same status still grants the instructor flag (the special
        # allowance), proving the two allowed sets are distinct.
        m2 = next(mm for mm in data["members"] if mm["id"] == instr_only.id)
        assert m2["isInstructor"] is True


# ============================================================
# Participant combination validation (passenger == pilot/instructor)
# ============================================================


class TestParticipantCombination:
    """The offline sync endpoint must reject a member holding two mutually
    exclusive roles on the same flight, mirroring FlightForm.clean()."""

    @pytest.fixture
    def site_config(self, db):
        from siteconfig.models import SiteConfiguration

        return SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
        )

    @pytest.fixture
    def second_member(self, site_config, db):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(
            username="second-pilot",
            first_name="Second",
            last_name="Pilot",
            membership_status="Full Member",
            instructor=True,
            towpilot=True,
        )

    def test_create_rejects_pilot_equal_passenger(
        self, authenticated_client, logsheet, glider, active_member, site_config
    ):
        """A member cannot be both pilot and passenger on the same flight."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "combo-create-pilot-pax",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "passenger_id": active_member.id,
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
        assert "both pilot and passenger" in data["results"][0]["error"]
        assert Flight.objects.filter(logsheet=logsheet).count() == 0

    def test_create_rejects_pilot_equal_instructor(
        self, authenticated_client, logsheet, glider, second_member, site_config
    ):
        """A member cannot be both pilot and instructor on the same flight.

        ``second_member`` has ``instructor=True`` so it passes the instructor
        eligibility check; the rejection must then come from the combination
        rule (not from instructor qualification)."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "combo-create-pilot-instr",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": second_member.id,
                        "instructor_id": second_member.id,
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
        assert "both pilot and instructor" in data["results"][0]["error"]
        assert Flight.objects.filter(logsheet=logsheet).count() == 0

    def test_update_rejects_passenger_equal_pilot(
        self, authenticated_client, logsheet, glider, active_member, second_member
    ):
        """Updating a valid flight so passenger_id == pilot_id must be
        rejected (the comment's exact scenario)."""
        url = reverse("logsheet:api_offline_flights_sync")
        # Create a valid two-seat flight: pilot=active, passenger=second.
        create_payload = {
            "flights": [
                {
                    "idempotencyKey": "combo-update-setup",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "passenger_id": second_member.id,
                        "glider_id": glider.id,
                        "flight_type": "towed",
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(create_payload), content_type="application/json"
        )
        flight_id = resp.json()["results"][0]["serverId"]

        # Now set the passenger to be the same member as the pilot.
        update_payload = {
            "flights": [
                {
                    "idempotencyKey": "combo-update-pax-eq-pilot",
                    "action": "update",
                    "data": {
                        "id": flight_id,
                        "passenger_id": active_member.id,
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(update_payload), content_type="application/json"
        )
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "both pilot and passenger" in data["results"][0]["error"]
        # The flight's passenger must still be the original distinct member.
        flight = Flight.objects.get(id=flight_id)
        assert flight.passenger_id == second_member.id
        assert flight.pilot_id == active_member.id

    def test_update_rejects_passenger_equal_instructor(
        self, authenticated_client, logsheet, glider, active_member, second_member
    ):
        """Updating a flight so passenger_id == instructor_id must be
        rejected."""
        url = reverse("logsheet:api_offline_flights_sync")
        # Create a valid flight: pilot=active, instructor=second.
        create_payload = {
            "flights": [
                {
                    "idempotencyKey": "combo-update-instr-setup",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "instructor_id": second_member.id,
                        "glider_id": glider.id,
                        "flight_type": "towed",
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(create_payload), content_type="application/json"
        )
        flight_id = resp.json()["results"][0]["serverId"]

        # Now set the passenger to be the same member as the instructor.
        update_payload = {
            "flights": [
                {
                    "idempotencyKey": "combo-update-pax-eq-instr",
                    "action": "update",
                    "data": {
                        "id": flight_id,
                        "passenger_id": second_member.id,
                    },
                }
            ]
        }
        resp = authenticated_client.post(
            url, data=json.dumps(update_payload), content_type="application/json"
        )
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "both instructor and passenger" in data["results"][0]["error"]
        flight = Flight.objects.get(id=flight_id)
        assert flight.passenger_id is None

    def test_create_allows_distinct_pilot_and_passenger(
        self, authenticated_client, logsheet, glider, active_member, second_member
    ):
        """A flight with distinct pilot and passenger must still be accepted."""
        url = reverse("logsheet:api_offline_flights_sync")
        payload = {
            "flights": [
                {
                    "idempotencyKey": "combo-create-valid",
                    "action": "create",
                    "data": {
                        "logsheet_id": logsheet.id,
                        "pilot_id": active_member.id,
                        "passenger_id": second_member.id,
                        "glider_id": glider.id,
                        "flight_type": "towed",
                    },
                }
            ]
        }
        response = authenticated_client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        data = response.json()
        assert data["results"][0]["status"] == "success", data
        assert Flight.objects.filter(logsheet=logsheet).count() == 1
        flight = Flight.objects.get(logsheet=logsheet)
        assert flight.pilot_id == active_member.id
        assert flight.passenger_id == second_member.id


# ============================================================
# Name-ordering preference propagation for offline selectors
# ============================================================


class TestReferenceDataNameOrdering:
    """The reference-data endpoint must propagate the club's member name
    ordering preference and both name fields so the offline cache can sort
    participant selectors the same way the online dropdowns do."""

    def _get_member(self, data, member):
        return next((m for m in data["members"] if m["id"] == member.id), None)

    def test_response_includes_name_ordering_preference(
        self, db, authenticated_client, active_member
    ):
        """The response carries the configured member_name_ordering so the
        offline cache can honor it (default is last_name)."""
        from siteconfig.models import SiteConfiguration

        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            member_name_ordering="last_name",
        )
        url = reverse("logsheet:api_offline_reference_data")
        data = authenticated_client.get(url).json()
        assert data["member_name_ordering"] == "last_name"

    def test_first_name_preference_is_propagated(
        self, db, authenticated_client, active_member
    ):
        """A club selecting first-name ordering gets 'first_name' back."""
        from siteconfig.models import SiteConfiguration

        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            member_name_ordering="first_name",
        )
        url = reverse("logsheet:api_offline_reference_data")
        data = authenticated_client.get(url).json()
        assert data["member_name_ordering"] == "first_name"

    def test_members_include_first_and_last_name(
        self, db, authenticated_client, active_member
    ):
        """Each cached member carries firstName and lastName fields so the
        offline selectors can apply the ordering and a secondary tie-breaker."""
        from siteconfig.models import SiteConfiguration

        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.example.com",
            club_abbreviation="TC",
            member_name_ordering="first_name",
        )
        url = reverse("logsheet:api_offline_reference_data")
        data = authenticated_client.get(url).json()
        member = self._get_member(data, active_member)
        assert member is not None
        assert member["first_name"] == active_member.first_name
        assert member["last_name"] == active_member.last_name
