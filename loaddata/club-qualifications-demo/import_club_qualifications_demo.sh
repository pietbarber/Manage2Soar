#!/usr/bin/env bash
#
# import_club_qualifications_demo.sh
#
# Imports the portable club-qualifications catalog captured from the
# tenant-ssc cluster (the "good-enough" set of 30 qualification types)
# into the CURRENT tenant (whichever DB this script's environment points at).
#
# The seed is NOT sanitized:
#   * No Member/User FKs to null.
#   * `icon` is a prefix-free GCS relative path (e.g.
#     `quals/icons/CFI-abc123.jpg`). This is a generic qualification graphic,
#     not PII. We preserve it in the DB.
#
# The one cross-tenant concern — the icon OBJECTS — is handled by an
# ICON-COPY phase that runs BEFORE loaddata. Because `MEDIA_URL` in prod is
# `https://storage.googleapis.com/{GS_BUCKET_NAME}/{CLUB_PREFIX}/media/`
# (where `CLUB_PREFIX` is the RENDERING tenant's prefix), a new tenant's own
# `{NEW_PREFIX}/media/quals/icons/` area is empty. If we only ran loaddata,
# the icons would 404. So this script copies the icon objects from the
# source tenant's area into the new tenant's area using the `google.cloud.storage`
# Python client (already a transitive dep of `django-storages` in the pod).
#
#   Default behavior: NO-CLOBBER. If a destination object already exists, it
#   is skipped (so a re-run is safe and never destroys a tenant's customized
#   icons). Use --overwrite-icons to force-copy over existing objects.
#
# Intended use (production / per-tenant):
#   The deployed image may not ship this repo's loaddata/ tree, so copy the
#   seed into the pod first, then run it from the copied location:
#     NS=<tenant-ns>
#     POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
#           | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 \
#           | sed -E 's#^pods?/##')
#     kubectl cp "loaddata/club-qualifications-demo" "$NS/$POD:/tmp/cseed" -c django
#     kubectl exec -n "$NS" -c django "$POD" -- bash /tmp/cseed/import_club_qualifications_demo.sh
#   (See docs/runbooks/club-qualifications-import.md for the full walkthrough.)
#
# Local / dev use (with your Django env already active):
#   bash loaddata/club-qualifications-demo/import_club_qualifications_demo.sh
#
# Options:
#   -f, --force              Allow overwriting an existing catalog (upsert, no delete).
#   -n, --no-icons           Skip the GCS icon-copy phase (icon DB values are
#                            preserved; the new tenant re-uploads icons to render).
#   -o, --overwrite-icons    Force-copy icons over existing objects in the
#                            target area (default is no-clobber).
#   -s, --source-prefix PFX  Source tenant prefix to copy icons from
#                            (default: ssc). Separate from the target's
#                            CLUB_PREFIX which comes from the pod env.
#   -h, --help               Show this help.
#
# Safety notes:
#   * --force does NOT delete existing rows. loaddata upserts by (model, pk);
#     rows with the same pk are replaced, other rows are left alone.
#   * Icon copy is NO-CLOBBER by default. Use --overwrite-icons to force.

set -euo pipefail

FORCE=0
NO_ICONS=0
OVERWRITE_ICONS=0
SOURCE_PREFIX="ssc"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force) FORCE=1; shift ;;
        -n|--no-icons) NO_ICONS=1; shift ;;
        -o|--overwrite-icons) OVERWRITE_ICONS=1; shift ;;
        -s|--source-prefix)
            if [[ -z "${2:-}" ]]; then
                echo "ERROR: --source-prefix requires a value" >&2
                exit 2
            fi
            SOURCE_PREFIX="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $1 (see --help)" >&2
            exit 2
            ;;
    esac
done

# Resolve the fixture directory relative to this script, so the script works
# both from the repo root and from inside the container image.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR"
export FIXTURE_DIR

FIXTURES=(
    "instructors.ClubQualificationType.json"
)

for f in "${FIXTURES[@]}"; do
    if [[ ! -f "$FIXTURE_DIR/$f" ]]; then
        echo "ERROR: fixture not found: $FIXTURE_DIR/$f" >&2
        exit 1
    fi
done

echo "==> Preflight: checking that the target tenant has no existing qualification catalog"

# Django's `manage.py shell -c` prints a line like
#     "95 objects imported automatically (use -v 2 for details)."
# to STDOUT before our own print() runs. Filter it out so we only see the
# count on a single line.
COUNT="$(
    python manage.py shell -c '
from instructors.models import ClubQualificationType
print(ClubQualificationType.objects.count())
' 2>/dev/null | grep -EoE '^[0-9]+$' | head -n1 || true
)"

if [[ -z "$COUNT" ]]; then
    echo "    ERROR: could not read row count from Django shell (unexpected output)." >&2
    echo "    Refusing to proceed without a reliable empty-check." >&2
    exit 4
fi

echo "    ClubQualificationType: $COUNT"

if [[ "$COUNT" -ne 0 ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
        echo "    !! Existing catalog detected, but --force was given. Proceeding (upsert, no delete)."
    else
        echo
        echo "ABORT: This tenant already has a qualification catalog ($COUNT rows)."
        echo "This script is meant for an EMPTY catalog."
        echo
        echo "If you are absolutely sure you want to overwrite it, re-run with --force."
        echo "NOTE: --force upserts by primary key and does NOT delete extra rows."
        exit 3
    fi
fi

# ---------------------------------------------------------------------------
# Icon copy phase (GCS) — copy icon objects from the source tenant's media
# area into the target tenant's media area, so the icons resolve for the new
# tenant (their MEDIA_URL points at their own {CLUB_PREFIX}/media/...).
# ---------------------------------------------------------------------------

if [[ "$NO_ICONS" -eq 1 ]]; then
    echo
    echo "==> Skipping icon copy (--no-icons). Icon DB values are preserved; the"
    echo "    new tenant will need to re-upload icons for them to render."
    ICON_COPY_STATUS="skipped"
else
    echo
    echo "==> Copying qualification icons from the source tenant's GCS media area"
    echo "    into the target tenant's GCS media area (no-clobber by default)"

    # Extract the set of non-empty icon relative paths from the fixture.
    ICON_PATHS="$(python3 -c '
import json, os
d = os.environ["FIXTURE_DIR"]
data = json.load(open(f"{d}/instructors.ClubQualificationType.json"))
paths = sorted({o["fields"]["icon"] for o in data if o["fields"].get("icon")})
print("\n".join(paths))
')"
    ICON_COUNT="$(echo "$ICON_PATHS" | grep -c . || true)"
    echo "    Found $ICON_COUNT distinct icon path(s) in the fixture."

    if [[ "$ICON_COUNT" -eq 0 ]]; then
        echo "    (No icons to copy — skipping GCS phase.)"
        ICON_COPY_STATUS="empty"
    else
        COPY_OUT="$(
            CQ_OVERWRITE_ICONS="$OVERWRITE_ICONS" CQ_ICON_PATHS="$ICON_PATHS" \
            CQ_SOURCE_PREFIX="$SOURCE_PREFIX" \
            python manage.py shell -c '
import os
from google.cloud import storage

overwrite = os.environ.get("CQ_OVERWRITE_ICONS") == "1"
paths = [p.strip() for p in os.environ["CQ_ICON_PATHS"].splitlines() if p.strip()]

bucket_name = os.environ.get("GS_BUCKET_NAME")
if not bucket_name:
    print("ERROR: GS_BUCKET_NAME is not set in the environment.")
    raise SystemExit(1)
src_prefix = os.environ.get("CQ_SOURCE_PREFIX", "ssc")
dst_prefix = os.environ.get("CLUB_PREFIX")
if not dst_prefix:
    print("ERROR: CLUB_PREFIX is not set in the environment.")
    raise SystemExit(1)

client = storage.Client()
bucket = client.bucket(bucket_name)
copied = skipped = 0
for p in paths:
    src = f"{src_prefix}/media/{p}"
    dst = f"{dst_prefix}/media/{p}"
    if bucket.get_blob(dst) is not None and not overwrite:
        skipped += 1
        continue
    # Same shared bucket for source and target; copy_blob expects a Bucket
    # object (not a string) as the destination bucket.
    bucket.copy_blob(bucket.blob(src), bucket, dst)
    copied += 1
print(f"icons: copied={copied} skipped_existing={skipped}")
' 2>&1
        )" || true

        echo "$COPY_OUT" | sed 's/^/    /'

        if echo "$COPY_OUT" | grep -qE 'GS_BUCKET_NAME is not set|CLUB_PREFIX is not set'; then
            echo "    ERROR: GCS environment is missing (GS_BUCKET_NAME / CLUB_PREFIX)." >&2
            echo "    Run inside the tenant pod, or pass --no-icons to skip the icon copy." >&2
            exit 7
        fi
        if ! echo "$COPY_OUT" | grep -qE '^icons: copied='; then
            echo "    ERROR: icon copy did not complete successfully." >&2
            echo "    Retry, or pass --no-icons to skip the icon copy." >&2
            exit 6
        fi
        ICON_COPY_STATUS="done"
    fi
fi

echo
echo "==> Loading qualification catalog fixtures"
for f in "${FIXTURES[@]}"; do
    echo "    loaddata $f"
    python manage.py loaddata "$FIXTURE_DIR/$f"
done

echo
echo "==> Verifying that every fixture primary key is now present in the target"

# `loaddata` upserts by primary key without deleting other rows. For an EMPTY
# tenant this means post_count == fixture_count; for a NON-EMPTY tenant with
# overlapping pks the counts will be higher than the fixture (existing rows
# preserved). The invariant that holds for BOTH cases is: every primary key
# from the fixture is now present in the target database.

VERIFY="$(
    python manage.py shell -c '
import json, os
d = os.environ["FIXTURE_DIR"]
from instructors.models import ClubQualificationType
fixture_pks = {o["pk"] for o in json.load(open(os.path.join(d, "instructors.ClubQualificationType.json")))}
present   = set(ClubQualificationType.objects.values_list("pk", flat=True))
missing   = fixture_pks - present
print(f"ClubQualificationType: fixture={len(fixture_pks)} present={len(present):>5}  "
      f"all_present={not missing}")
if missing:
    print(f"    MISSING pks ({len(missing)}): {sorted(missing)[:10]}")
    raise SystemExit(1)
' 2>&1
)" || true

echo "$VERIFY" | sed 's/^/    /'

# The inner python exits non-zero on any missing pk, but the `|| true` above
# keeps that status from tripping `set -e` (so the "MISSING pks" diagnostic
# above is still captured into $VERIFY and printed). The all_present=True
# check below therefore drives the script's exit code.
if [[ -z "$VERIFY" ]] || ! echo "$VERIFY" | grep -q "all_present=True"; then
    echo "    ERROR: at least one fixture primary key is missing from the target." >&2
    exit 5
fi

# Post-load counts (informational only).
POST="$(
    python manage.py shell -c '
from instructors.models import ClubQualificationType
print(ClubQualificationType.objects.count())
' 2>/dev/null | grep -EoE '^[0-9]+$' | head -n1 || true
)"
echo
echo "==> Post-load count: ClubQualificationType: ${POST:-(unreadable)}"
echo
echo "NOTE: the qualification catalog seed is preserved as-is (no sanitization)."
echo "      Icons were ${ICON_COPY_STATUS}. If skipped, the new tenant should re-upload"
echo "      any icons they want to use; the DB icon paths are intact either way."
