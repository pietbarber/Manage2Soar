#!/usr/bin/env bash
#
# refresh_seed_from_tenant.sh
#
# Refreshes the club-qualifications seed fixture in this repo by re-dumping
# the `instructors.ClubQualificationType` catalog from a SOURCE tenant
# (default: tenant-ssc, which holds the "good-enough" set) into
# loaddata/club-qualifications-demo/.
#
# Why NO sanitization is needed here (unlike the knowledge-test seed):
#   * The model has no Member/User FKs, so there are no cross-tenant dangling
#     references to null out.
#   * `code` is a unique business key (e.g. "CFI", "ASK-Back") and `name` is a
#     generic human label (e.g. "Certified Flight Instructor"). Neither leaks
#     personal data.
#   * `icon` is a per-tenant GCS *relative* path (e.g.
#     `quals/icons/CFI-abc123.jpg`) — a generic qualification graphic, not PII.
#     We deliberately PRESERVE the icon path in the fixture. The accompanying
#     import script (import_club_qualifications_demo.sh) copies the icon
#     objects from the source tenant's media area into the new tenant's media
#     area so the icons render out of the box (see that script's header and
#     docs/runbooks/club-qualifications-import.md for details).
#
# Models captured (the portable "qualification catalog"):
#   instructors.ClubQualificationType
#
# Deliberately EXCLUDED (per-member history, not part of a catalog):
#   instructors.MemberQualification (references Member; only exists in source)
#
# What it does:
#   1. Locates a long-running app pod in the source tenant's namespace.
#   2. Dumps the model inside that pod (plain FK pks, NOT --natural-foreign).
#   3. Copies the JSON into loaddata/club-qualifications-demo/.
#   4. Prints before/after row counts and a per-file summary (how many rows
#      carry an icon — informational, so operators know an icon copy is
#      expected at import time).
#   5. Prints a `git diff --stat` hint. It does NOT commit or push.
#
# Usage:
#   bash loaddata/club-qualifications-demo/refresh_seed_from_tenant.sh [namespace]
#     namespace   optional, defaults to tenant-ssc
#
# Requirements: kubectl authenticated to the cluster, repo checked out.

set -euo pipefail

NS="${1:-tenant-ssc}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# (Model label, app.Model for dumpdata, fixture filename)
MODELS=(
    "ClubQualificationType|instructors.ClubQualificationType|instructors.ClubQualificationType.json"
)

echo "==> Source namespace: $NS"

POD="$(kubectl get pods -n "$NS" -o name \
        | grep -E 'django-app' \
        | grep -vE 'clearsessions|expire|notify|process|send|cron' \
        | head -1 | sed -E 's#^pods?/##' || true)"

if [[ -z "$POD" ]]; then
    echo "ERROR: no long-running app pod found in namespace $NS" >&2
    exit 1
fi
echo "==> Source pod: $POD"

echo
echo "==> Row counts BEFORE refresh (repo)"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
for name in ("ClubQualificationType",):
    p = f"{d}/instructors.{name}.json"
    try:
        print(f"    {name}: {len(json.load(open(p)))}")
    except FileNotFoundError:
        print(f"    {name}: (missing)")
PY

echo
echo "==> Dumping from source tenant (plain FK pks, no --natural-foreign)"
for entry in "${MODELS[@]}"; do
    LABEL="${entry%%|*}"; rest="${entry#*|}"
    MODEL="${rest%%|*}"
    echo "    dumpdata $MODEL"
    kubectl exec -n "$NS" -c django "$POD" -- \
        python manage.py dumpdata "$MODEL" --indent 2 -o "/tmp/cq_$LABEL.json" 2>/dev/null
    kubectl cp "$NS/$POD:/tmp/cq_$LABEL.json" "$FIXTURE_DIR/instructors.$LABEL.json" -c django 2>&1 \
        | grep -viE 'tar: Removing|exiting' || true
done
kubectl exec -n "$NS" -c django "$POD" -- bash -c 'rm -f /tmp/cq_*.json'

echo
echo "==> No sanitization needed (see header). Summary of icon-bearing rows:"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
for fn in ("instructors.ClubQualificationType.json",):
    path = f"{d}/{fn}"
    data = json.load(open(path))
    with_icon = sum(1 for o in data if o.get("fields", {}).get("icon"))
    print(f"    {fn}: {len(data)} objects ({with_icon} with icons)")
PY

echo
echo "==> Row counts AFTER refresh (repo)"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
for name in ("ClubQualificationType",):
    n = len(json.load(open(f"{d}/instructors.{name}.json")))
    print(f"    {name}: {n}")
PY

echo
echo "==> Review the diff before committing:"
echo
echo "    cd $REPO_ROOT"
echo "    git status --short loaddata/club-qualifications-demo/"
echo "    git diff --stat loaddata/club-qualifications-demo/"
echo
echo "Then commit via the normal feature-branch + PR flow (NEVER commit to main)."
