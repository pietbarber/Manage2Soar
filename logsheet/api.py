"""
Offline Sync API Endpoints for Manage2Soar PWA

Provides API endpoints for:
- GET /api/offline/reference-data/ - Fetch members, gliders, towplanes, airfields for pre-caching
- POST /api/offline/flights/sync/ - Batch upload flights with idempotency keys
- GET /api/offline/sync-status/ - Check sync status

Part of Issue #315: PWA Fully-offline Logsheet data entry
"""

import json
import logging
import uuid
from datetime import date

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from members.decorators import active_member_required
from members.models import Member

from .models import Airfield, Flight, Glider, Logsheet, Towplane

logger = logging.getLogger(__name__)


# Cache for tracking idempotency keys to prevent duplicate flight creation
# In production, this should be stored in Redis or database
_idempotency_cache = {}


@require_GET
@active_member_required
def reference_data(request):
    """
    Return all reference data needed for offline flight entry.

    Returns minimal data needed for form dropdowns and validation:
    - members: id, name, can be pilot/instructor/tow_pilot
    - gliders: id, display name, seats, is_active
    - towplanes: id, name, is_active
    - airfields: id, identifier, name, is_active
    - flight_types: list of valid flight type choices
    - release_altitudes: list of valid release altitude choices
    """
    try:
        # Get active members who can appear on flights
        # Include pilots, instructors, tow pilots
        members = Member.objects.filter(is_active=True).values(
            "id",
            "first_name",
            "last_name",
            "nickname",
            "is_staff",
        )

        # Determine member capabilities from related permissions
        member_list = []
        for m in members:
            member_list.append(
                {
                    "id": m["id"],
                    "name": f"{m['first_name']} {m['last_name']}".strip(),
                    "nickname": m["nickname"] or "",
                    "display_name": (
                        m["nickname"]
                        if m["nickname"]
                        else f"{m['first_name']} {m['last_name']}".strip()
                    ),
                }
            )

        # Get active gliders
        gliders = Glider.objects.filter(is_active=True).values(
            "id",
            "make",
            "model",
            "n_number",
            "competition_number",
            "seats",
            "rental_rate",
            "club_owned",
        )
        glider_list = []
        for g in gliders:
            display_parts = []
            if g["competition_number"]:
                display_parts.append(g["competition_number"].upper())
            if g["n_number"]:
                display_parts.append(g["n_number"].upper())
            if g["model"]:
                display_parts.append(g["model"])

            glider_list.append(
                {
                    "id": g["id"],
                    "display_name": " / ".join(display_parts),
                    "n_number": g["n_number"],
                    "competition_number": g["competition_number"] or "",
                    "model": g["model"],
                    "seats": g["seats"],
                    "rental_rate": str(g["rental_rate"]) if g["rental_rate"] else None,
                    "club_owned": g["club_owned"],
                }
            )

        # Get active towplanes
        towplanes = Towplane.objects.filter(is_active=True).values(
            "id",
            "name",
            "n_number",
            "make",
            "model",
        )
        towplane_list = [
            {
                "id": t["id"],
                "name": t["name"],
                "n_number": t["n_number"],
                "display_name": f"{t['name']} ({t['n_number']})",
            }
            for t in towplanes
        ]

        # Get active airfields
        airfields = Airfield.objects.filter(is_active=True).values(
            "id",
            "identifier",
            "name",
        )
        airfield_list = [
            {
                "id": a["id"],
                "identifier": a["identifier"],
                "name": a["name"],
                "display_name": f"{a['identifier']} – {a['name']}",
            }
            for a in airfields
        ]

        # Flight types - these match the choices used in forms
        flight_types = [
            {"value": "solo", "label": "Solo"},
            {"value": "dual", "label": "Dual Instruction"},
            {"value": "intro", "label": "Intro Ride"},
            {"value": "demo", "label": "Demo Flight"},
            {"value": "checkout", "label": "Checkout"},
            {"value": "proficiency", "label": "Proficiency"},
            {"value": "passenger", "label": "Passenger Flight"},
            {"value": "other", "label": "Other"},
        ]

        # Release altitude choices (from Flight model)
        release_altitudes = [
            {"value": i, "label": f"{i} ft"} for i in range(0, 7100, 100)
        ]

        # Launch methods
        launch_methods = [
            {"value": "tow", "label": "Towplane"},
            {"value": "winch", "label": "Winch"},
            {"value": "self", "label": "Self-Launch"},
            {"value": "other", "label": "Other"},
        ]

        # Version for cache invalidation
        # Use a combination of data modification timestamps
        version = int(timezone.now().timestamp())

        return JsonResponse(
            {
                "success": True,
                "version": version,
                "members": member_list,
                "gliders": glider_list,
                "towplanes": towplane_list,
                "airfields": airfield_list,
                "flight_types": flight_types,
                "release_altitudes": release_altitudes,
                "launch_methods": launch_methods,
            }
        )

    except Exception as e:
        logger.exception("Error fetching reference data")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=500,
        )


@require_POST
@active_member_required
def flights_sync(request):
    """
    Batch sync flights from offline storage.

    Expects JSON body:
    {
        "flights": [
            {
                "idempotencyKey": "unique-key-for-deduplication",
                "action": "create" | "update",
                "data": {
                    "logsheet_id": int,
                    "pilot_id": int,
                    "glider_id": int,
                    ...
                }
            }
        ]
    }

    Returns:
    {
        "success": true,
        "results": [
            {
                "idempotencyKey": "...",
                "status": "success" | "duplicate" | "conflict" | "error",
                "serverId": int (if success),
                "error": "message" (if error),
                "serverData": {...} (if conflict)
            }
        ]
    }
    """
    try:
        data = json.loads(request.body.decode())
        flights = data.get("flights", [])

        if not flights:
            return JsonResponse(
                {"success": False, "error": "No flights provided"},
                status=400,
            )

        results = []

        for flight_item in flights:
            idempotency_key = flight_item.get("idempotencyKey")
            action = flight_item.get("action", "create")
            flight_data = flight_item.get("data", {})

            result = {"idempotencyKey": idempotency_key}

            try:
                # Check for duplicate using idempotency key
                if idempotency_key in _idempotency_cache:
                    cached = _idempotency_cache[idempotency_key]
                    result["status"] = "duplicate"
                    result["serverId"] = cached.get("flight_id")
                    results.append(result)
                    continue

                if action == "create":
                    # Validate and create flight
                    flight_result = _create_flight_from_offline(
                        flight_data, request.user
                    )

                    if flight_result["success"]:
                        result["status"] = "success"
                        result["serverId"] = flight_result["flight_id"]

                        # Cache idempotency key
                        _idempotency_cache[idempotency_key] = {
                            "flight_id": flight_result["flight_id"],
                            "created_at": timezone.now().isoformat(),
                        }
                    else:
                        result["status"] = "error"
                        result["error"] = flight_result.get("error", "Unknown error")

                elif action == "update":
                    # Handle update with conflict detection
                    flight_result = _update_flight_from_offline(
                        flight_data, request.user
                    )

                    if flight_result["success"]:
                        result["status"] = "success"
                        result["serverId"] = flight_result["flight_id"]
                    elif flight_result.get("conflict"):
                        result["status"] = "conflict"
                        result["reason"] = flight_result.get("reason")
                        result["serverData"] = flight_result.get("serverData")
                    else:
                        result["status"] = "error"
                        result["error"] = flight_result.get("error", "Unknown error")

                else:
                    result["status"] = "error"
                    result["error"] = f"Unknown action: {action}"

            except Exception as e:
                logger.exception(f"Error processing flight sync: {idempotency_key}")
                result["status"] = "error"
                result["error"] = str(e)

            results.append(result)

        return JsonResponse(
            {
                "success": True,
                "results": results,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON"},
            status=400,
        )
    except Exception as e:
        logger.exception("Error in flights sync")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=500,
        )


def _create_flight_from_offline(flight_data, user):
    """
    Create a new flight from offline data.

    Args:
        flight_data: Dictionary with flight fields
        user: The user making the request

    Returns:
        dict with success status and flight_id or error
    """
    try:
        with transaction.atomic():
            # Validate required fields
            logsheet_id = flight_data.get("logsheet_id")
            if not logsheet_id:
                return {"success": False, "error": "logsheet_id is required"}

            # Get logsheet and verify it's not finalized
            try:
                logsheet = Logsheet.objects.get(id=logsheet_id)
            except Logsheet.DoesNotExist:
                return {"success": False, "error": "Logsheet not found"}

            if logsheet.finalized:
                return {"success": False, "error": "Logsheet is finalized"}

            # Validate and get related objects
            pilot = None
            if flight_data.get("pilot_id"):
                try:
                    pilot = Member.objects.get(id=flight_data["pilot_id"])
                except Member.DoesNotExist:
                    return {"success": False, "error": "Pilot not found"}

            instructor = None
            if flight_data.get("instructor_id"):
                try:
                    instructor = Member.objects.get(id=flight_data["instructor_id"])
                except Member.DoesNotExist:
                    return {"success": False, "error": "Instructor not found"}

            glider = None
            if flight_data.get("glider_id"):
                try:
                    glider = Glider.objects.get(id=flight_data["glider_id"])
                except Glider.DoesNotExist:
                    return {"success": False, "error": "Glider not found"}

            towplane = None
            if flight_data.get("towplane_id"):
                try:
                    towplane = Towplane.objects.get(id=flight_data["towplane_id"])
                except Towplane.DoesNotExist:
                    return {"success": False, "error": "Towplane not found"}

            tow_pilot = None
            if flight_data.get("tow_pilot_id"):
                try:
                    tow_pilot = Member.objects.get(id=flight_data["tow_pilot_id"])
                except Member.DoesNotExist:
                    return {"success": False, "error": "Tow pilot not found"}

            passenger = None
            if flight_data.get("passenger_id"):
                try:
                    passenger = Member.objects.get(id=flight_data["passenger_id"])
                except Member.DoesNotExist:
                    return {"success": False, "error": "Passenger not found"}

            airfield = None
            if flight_data.get("airfield_id"):
                try:
                    airfield = Airfield.objects.get(id=flight_data["airfield_id"])
                except Airfield.DoesNotExist:
                    return {"success": False, "error": "Airfield not found"}

            # Create the flight
            flight = Flight.objects.create(
                logsheet=logsheet,
                pilot=pilot,
                instructor=instructor,
                glider=glider,
                towplane=towplane,
                tow_pilot=tow_pilot,
                passenger=passenger,
                airfield=airfield,
                launch_time=flight_data.get("launch_time"),
                landing_time=flight_data.get("landing_time"),
                release_altitude=flight_data.get("release_altitude"),
                flight_type=flight_data.get("flight_type", "solo"),
                launch_method=flight_data.get("launch_method", "tow"),
                notes=flight_data.get("notes", ""),
                passenger_name=flight_data.get("passenger_name", ""),
            )

            return {"success": True, "flight_id": flight.id}

    except Exception as e:
        logger.exception("Error creating flight from offline data")
        return {"success": False, "error": str(e)}


def _update_flight_from_offline(flight_data, user):
    """
    Update an existing flight from offline data with conflict detection.

    Args:
        flight_data: Dictionary with flight fields (must include 'id')
        user: The user making the request

    Returns:
        dict with success status, conflict info, or error
    """
    try:
        flight_id = flight_data.get("id")
        if not flight_id:
            return {"success": False, "error": "Flight id is required for updates"}

        with transaction.atomic():
            try:
                flight = Flight.objects.select_for_update().get(id=flight_id)
            except Flight.DoesNotExist:
                return {"success": False, "error": "Flight not found"}

            if flight.logsheet.finalized:
                return {"success": False, "error": "Logsheet is finalized"}

            # Check for conflict: compare last modified timestamp
            # If client has stale data, return conflict
            client_version = flight_data.get("version")
            if client_version:
                server_version = flight.created_at.isoformat()
                if client_version != server_version:
                    # Conflict detected - return current server data
                    return {
                        "success": False,
                        "conflict": True,
                        "reason": "Flight was modified on server",
                        "serverData": _flight_to_dict(flight),
                    }

            # Apply updates
            if "pilot_id" in flight_data:
                if flight_data["pilot_id"]:
                    flight.pilot = Member.objects.get(id=flight_data["pilot_id"])
                else:
                    flight.pilot = None

            if "instructor_id" in flight_data:
                if flight_data["instructor_id"]:
                    flight.instructor = Member.objects.get(
                        id=flight_data["instructor_id"]
                    )
                else:
                    flight.instructor = None

            if "glider_id" in flight_data:
                if flight_data["glider_id"]:
                    flight.glider = Glider.objects.get(id=flight_data["glider_id"])
                else:
                    flight.glider = None

            if "towplane_id" in flight_data:
                if flight_data["towplane_id"]:
                    flight.towplane = Towplane.objects.get(
                        id=flight_data["towplane_id"]
                    )
                else:
                    flight.towplane = None

            if "tow_pilot_id" in flight_data:
                if flight_data["tow_pilot_id"]:
                    flight.tow_pilot = Member.objects.get(
                        id=flight_data["tow_pilot_id"]
                    )
                else:
                    flight.tow_pilot = None

            if "launch_time" in flight_data:
                flight.launch_time = flight_data["launch_time"]

            if "landing_time" in flight_data:
                flight.landing_time = flight_data["landing_time"]

            if "release_altitude" in flight_data:
                flight.release_altitude = flight_data["release_altitude"]

            if "flight_type" in flight_data:
                flight.flight_type = flight_data["flight_type"]

            if "launch_method" in flight_data:
                flight.launch_method = flight_data["launch_method"]

            if "notes" in flight_data:
                flight.notes = flight_data["notes"]

            flight.save()

            return {"success": True, "flight_id": flight.id}

    except Member.DoesNotExist:
        return {"success": False, "error": "Member not found"}
    except Glider.DoesNotExist:
        return {"success": False, "error": "Glider not found"}
    except Towplane.DoesNotExist:
        return {"success": False, "error": "Towplane not found"}
    except Exception as e:
        logger.exception("Error updating flight from offline data")
        return {"success": False, "error": str(e)}


def _flight_to_dict(flight):
    """Convert a Flight model to a dictionary for API responses."""
    return {
        "id": flight.id,
        "logsheet_id": flight.logsheet_id,
        "pilot_id": flight.pilot_id,
        "instructor_id": flight.instructor_id,
        "glider_id": flight.glider_id,
        "towplane_id": flight.towplane_id,
        "tow_pilot_id": flight.tow_pilot_id,
        "passenger_id": flight.passenger_id,
        "airfield_id": flight.airfield_id,
        "launch_time": (flight.launch_time.isoformat() if flight.launch_time else None),
        "landing_time": (
            flight.landing_time.isoformat() if flight.landing_time else None
        ),
        "release_altitude": flight.release_altitude,
        "flight_type": flight.flight_type,
        "launch_method": flight.launch_method,
        "notes": flight.notes,
        "version": flight.created_at.isoformat(),
    }


@require_GET
@active_member_required
def sync_status(request):
    """
    Return sync status for the current user.

    This can be used to check if there are pending syncs on the server side
    or to verify connectivity.
    """
    return JsonResponse(
        {
            "success": True,
            "online": True,
            "serverTime": timezone.now().isoformat(),
            "user": {
                "id": request.user.id,
                "name": request.user.get_full_name(),
            },
        }
    )
