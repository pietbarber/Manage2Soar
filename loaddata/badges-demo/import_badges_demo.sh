#!/usr/bin/env bash
#
# import_badges_demo.sh
#
# Imports the portable badge catalog captured from the tenant-ssc cluster
# (the "good-enough" set of 15 SSA/FAI badges, including the FAI
# Silver/Gold/Diamond leg structure) into the CURRENT tenant (whichever DB
# this script's environment points at).
#
# The seed is NOT sanitized:
#   * No Member/User FKs to null.
#   * `parent_badge` is a self-referential FK (a badge leg -> its parent
#     badge) whose target pk lives INSIDE this same fixture, so it resolves
#     cleanly on load in any tenant.
#   * `image` is a prefix-free GCS relative path (e.g.
#     `badge_images/A-Soaring-Badge-Achievement.png`). This is a generic
#     badge graphic, not PII. We preserve it in the DB.
#
# The one cross-tenant concern — the image OBJECTS — is handled by an
# IMAGE-COPY phase that runs BEFORE loaddata. Because `MEDIA_URL` in prod is
# `https://storage.googleapis.com/{GS_BUCKET_NAME}/{CLUB_PREFIX}/media/`
# (where `CLUB_PREFIX` is the RENDERING tenant's prefix), a new tenant's own
# `{NEW_PREFIX}/media/badge_images/` area is empty. If we only ran loaddata,
# the badge images would 404. So this script copies the image objects from
# the source tenant's area into the new tenant's area using the
# `google.cloud.storage` Python client (already a transitive dep of
# `django-storages` in the pod).
#
#   Default behavior: NO-CLOBBER. If a destination object already exists, it
#   is skipped (so a re-run is safe and never destroys a tenant's customized
#   badge images). Use --overwrite-images to force-copy over existing objects.
#
# Intended use (production / per-tenant):
#   The deployed image may not ship this repo's loaddata/ tree, so copy the
#   seed into the pod first, then run it from the copied location:
#     NS=<tenant-ns>
#     POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
#           | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 \
#           | sed -E 's#^pods?/##')
#     kubectl cp "loaddata/badges-demo" "$NS/$POD:/tmp/bseed" -c django
#     kubectl exec -n "$NS" -c django "$POD" -- bash /tmp/bseed/import_badges_demo.sh
#   (See docs/runbooks/badges-import.md for the full walkthrough.)
#
# Local / dev use (with your Django env already active):
#   bash loaddata/badges-demo/import_badges_demo.sh
#
# Options:
#   -f, --force               Allow overwriting an existing badge catalog
#                             (upsert, no delete).
#   -n, --no-images           Skip the GCS image-copy phase (image DB values
#                             are preserved; the new tenant re-uploads images
#                             to render them).
#   -o, --overwrite-images    Force-copy images over existing objects in the
#                             target area (default is no-clobber).
#   -s, --source-prefix PFX   Source tenant prefix to copy images from
#                             (default: ssc). Separate from the target's
#                             CLUB_PREFIX which comes from the pod env.
#   -h, --help                Show this help.
#
# Safety notes:
#   * --force does NOT delete existing rows. loaddata upserts by (model, pk);
#     rows with the same pk are replaced, other rows are left alone.
#   * Image copy is NO-CLOBBER by default. Use --overwrite-images to force.
#
# Exit codes:
#   0  success
#   1  fixture not found
#   2  bad argument
#   3  target already has badges and --force was not given
#   4  could not read the row count from Django
#   5  verification failed (a fixture pk is missing after loaddata)
#   6  image copy failed
#   7  GCS environment not present in the target pod

set -euo pipefail

FORCE=0
NO_IMAGES=0
OVERWRITE_IMAGES=0
SOURCE_PREFIX="ssc"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force) FORCE=1; shift ;;
        -n|--no-images) NO_IMAGES=1; shift ;;
        -o|--overwrite-images) OVERWRITE_IMAGES=1; shift ;;
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
    "members.Badge.json"
)

for f in "${FIXTURES[@]}"; do
    if [[ ! -f "$FIXTURE_DIR/$f" ]]; then
        echo "ERROR: fixture not found: $FIXTURE_DIR/$f" >&2
        exit 1
    fi
done

echo "==> Preflight: checking that the target tenant has no existing badge catalog"

# Django's `manage.py shell -c` prints a line like
#     "95 objects imported automatically (use -v 2 for details)."
# to STDOUT before our own print() runs. Filter it out so we only see the
# count on a single line.
COUNT="$(
    python manage.py shell -c '
from members.models import Badge
print(Badge.objects.count())
' 2>/dev/null | grep -EoE '^[0-9]+$' | head -n1 || true
)"

if [[ -z "$COUNT" ]]; then
    echo "    ERROR: could not read row count from Django shell (unexpected output)." >&2
    echo "    Refusing to proceed without a reliable empty-check." >&2
    exit 4
fi

echo "    Badge: $COUNT"

if [[ "$COUNT" -ne 0 ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
        echo "    !! Existing badge catalog detected, but --force was given. Proceeding (upsert, no delete)."
    else
        echo
        echo "ABORT: This tenant already has a badge catalog ($COUNT rows)."
        echo "This script is meant for an EMPTY catalog."
        echo
        echo "If you are absolutely sure you want to overwrite it, re-run with --force."
        echo "NOTE: --force upserts by primary key and does NOT delete extra rows."
        exit 3
    fi
fi

# ---------------------------------------------------------------------------
# Image copy phase (GCS) — copy badge image objects from the source tenant's
# media area into the target tenant's media area, so the images resolve for
# the new tenant (their MEDIA_URL points at their own {CLUB_PREFIX}/media/...).
# ---------------------------------------------------------------------------

if [[ "$NO_IMAGES" -eq 1 ]]; then
    echo
    echo "==> Skipping image copy (--no-images). Image DB values are preserved;"
    echo "    the new tenant will need to re-upload images for them to render."
    IMAGE_COPY_STATUS="skipped"
else
    echo
    echo "==> Copying badge images from the source tenant's GCS media area"
    echo "    into the target tenant's GCS media area (no-clobber by default)"

    # Extract the set of non-empty image relative paths from the fixture.
    IMAGE_PATHS="$(python3 -c '
import json, os
d = os.environ["FIXTURE_DIR"]
data = json.load(open(f"{d}/members.Badge.json"))
paths = sorted({o["fields"]["image"] for o in data if o["fields"].get("image")})
print("\n".join(paths))
')"
    IMAGE_COUNT="$(echo "$IMAGE_PATHS" | grep -c . || true)"
    echo "    Found $IMAGE_COUNT distinct image path(s) in the fixture."

    if [[ "$IMAGE_COUNT" -eq 0 ]]; then
        echo "    (No images to copy — skipping GCS phase.)"
        IMAGE_COPY_STATUS="empty"
    else
        COPY_OUT="$(
            BADGE_OVERWRITE_IMAGES="$OVERWRITE_IMAGES" BADGE_IMAGE_PATHS="$IMAGE_PATHS" \
            BADGE_SOURCE_PREFIX="$SOURCE_PREFIX" \
            python manage.py shell -c '
import os
from google.cloud import storage

overwrite = os.environ.get("BADGE_OVERWRITE_IMAGES") == "1"
paths = [p.strip() for p in os.environ["BADGE_IMAGE_PATHS"].splitlines() if p.strip()]

bucket_name = os.environ.get("GS_BUCKET_NAME")
if not bucket_name:
    print("ERROR: GS_BUCKET_NAME is not set in the environment.")
    raise SystemExit(1)
src_prefix = os.environ.get("BADGE_SOURCE_PREFIX", "ssc")
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
    # Same shared bucket for source and target; copy_blob destination
    # argument must be a Bucket object (not a string).
    if overwrite:
        # Overwrite: unconditional copy, replacing any existing destination.
        bucket.copy_blob(bucket.blob(src), bucket, dst)
        copied += 1
    else:
        # No-clobber, made ATOMIC by a GCS precondition instead of a
        # check-then-copy (which had a TOCTOU race: the destination could be
        # created between get_blob() and the copy, and the copy would then
        # overwrite it). if_generation_match=0 tells GCS to copy ONLY if the
        # destination does not exist (generation 0); if it does, GCS rejects
        # with 412 Precondition Failed and nothing is written.
        try:
            bucket.copy_blob(bucket.blob(src), bucket, dst, if_generation_match=0)
            copied += 1
        except Exception as e:  # noqa: BLE001 - distinguish no-clobber skip vs real failure
            if getattr(e, "response", None) is not None and e.response.status_code == 412:
                skipped += 1
                continue
            raise
print(f"images: copied={copied} skipped_existing={skipped}")
' 2>&1
        )" || true

        echo "$COPY_OUT" | sed 's/^/    /'

        if echo "$COPY_OUT" | grep -qE 'GS_BUCKET_NAME is not set|CLUB_PREFIX is not set'; then
            echo "    ERROR: GCS environment is missing (GS_BUCKET_NAME / CLUB_PREFIX)." >&2
            echo "    Run inside the tenant pod, or pass --no-images to skip the image copy." >&2
            exit 7
        fi
        if ! echo "$COPY_OUT" | grep -qE '^images: copied='; then
            echo "    ERROR: image copy did not complete successfully." >&2
            echo "    Retry, or pass --no-images to skip the image copy." >&2
            exit 6
        fi
        IMAGE_COPY_STATUS="done"
    fi
fi

echo
echo "==> Loading badge catalog fixtures"
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
from members.models import Badge
fixture_pks = {o["pk"] for o in json.load(open(os.path.join(d, "members.Badge.json")))}
present   = set(Badge.objects.values_list("pk", flat=True))
missing   = fixture_pks - present
legs_ok   = all(
    b.parent_badge_id is None or b.parent_badge_id in present
    for b in Badge.objects.all()
    if b.pk in fixture_pks
)
print(f"Badge: fixture={len(fixture_pks)} present={len(present):>5}  "
      f"all_present={not missing}  leg_integrity={legs_ok}")
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
if ! echo "$VERIFY" | grep -q "leg_integrity=True"; then
    echo "    ERROR: a badge leg points at a parent badge that is missing." >&2
    exit 5
fi

# Post-load counts (informational only).
POST="$(
    python manage.py shell -c '
from members.models import Badge
print(Badge.objects.count())
' 2>/dev/null | grep -EoE '^[0-9]+$' | head -n1 || true
)"
echo
echo "==> Post-load count: Badge: ${POST:-(unreadable)}"
echo
echo "NOTE: the badge catalog seed is preserved as-is (no sanitization)."
echo "      Images were ${IMAGE_COPY_STATUS}. If skipped, the new tenant should"
echo "      re-upload any images they want to use; the DB image paths are intact"
echo "      either way. FAI legs are linked to their parent badges in this seed."
