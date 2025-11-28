"""
Tests for Offline Sync API endpoints.

Part of Issue #315: PWA Fully-offline Logsheet data entry
"""

import json
from datetime import date

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
