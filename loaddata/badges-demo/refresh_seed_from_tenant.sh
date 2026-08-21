#!/usr/bin/env bash
#
# refresh_seed_from_tenant.sh
#
# Refreshes the badge seed fixture in this repo by re-dumping the
# `members.Badge` catalog from a SOURCE tenant (default: tenant-ssc, which
# holds the "good-enough" SSA + FAI badge set, including the FAI leg
# parent/child structure) into loaddata/badges-demo/.
#
# Why NO sanitization is needed here (unlike the knowledge-test seed):
#   * The model has no Member/User FKs, so there are no cross-tenant dangling
#     references to null out.
#   * `name` is a generic human label (e.g. "A Badge", "FAI Silver Badge").
#     `parent_badge` is a self-referential FK (a badge leg pointing at its
#     parent badge) whose pk lives INSIDE this same fixture, so it resolves
#     cleanly on load in any tenant.
#   * `image` is a per-tenant GCS *relative* path (e.g.
#     `badge_images/A-Soaring-Badge-Achievement.png`) — a generic badge
#     graphic, not PII. We deliberately PRESERVE the image path in the
#     fixture. The accompanying import script (import_badges_demo.sh) copies
#     the image objects from the source tenant's media area into the new
#     tenant's media area so the badges render out of the box (see that
#     script's header and docs/runbooks/badges-import.md for details).
#
# Models captured (the portable "badge catalog"):
#   members.Badge
#
# Deliberately EXCLUDED (per-member history, not part of a catalog):
#   members.MemberBadge (references Member; only exists in source). A new
#   tenant's members earn their badges through normal club processes.
#
# What it does:
#   1. Locates a long-running app pod in the source tenant's namespace.
#   2. Dumps the model inside that pod (plain FK pks, NOT --natural-foreign).
#   3. Copies the JSON into loaddata/badges-demo/.
#   4. Prints before/after row counts and a per-file summary (how many rows
#      carry an image, and how many are "legs" via parent_badge —
#      informational, so operators know an image copy is expected at import
#      time and that the FAI leg structure is intact).
#   5. Prints a `git diff --stat` hint. It does NOT commit or push.
#
# Usage:
#   bash loaddata/badges-demo/refresh_seed_from_tenant.sh [namespace]
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
    "Badge|members.Badge|members.Badge.json"
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
for name in ("Badge",):
    p = f"{d}/members.{name}.json"
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
        python manage.py dumpdata "$MODEL" --indent 2 -o "/tmp/badge_$LABEL.json" 2>/dev/null
    # Capture kubectl cp's output/exit status WITHOUT letting a non-zero exit
    # trip `set -euo pipefail` (which would abort here, before we can report
    # which model failed and that the fixture is stale). `|| true` neutralizes
    # the status while still preserving stdout/stderr.
    CP_OUT="$(kubectl cp "$NS/$POD:/tmp/badge_$LABEL.json" "$FIXTURE_DIR/members.$LABEL.json" -c django 2>&1)" || true
    echo "$CP_OUT" | grep -viE 'tar: Removing|exiting' || true
    if [[ ! -s "$FIXTURE_DIR/members.$LABEL.json" ]]; then
        echo "ERROR: kubectl cp for $LABEL did not produce a non-empty fixture" >&2
        echo "       (the previous fixture, if any, may be stale). See kubectl cp output above." >&2
        exit 1
    fi
done
kubectl exec -n "$NS" -c django "$POD" -- bash -c 'rm -f /tmp/badge_*.json'

echo
echo "==> No sanitization needed (see header). Summary of image-bearing + leg rows:"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
for fn in ("members.Badge.json",):
    path = f"{d}/{fn}"
    data = json.load(open(path))
    with_img = sum(1 for o in data if o.get("fields", {}).get("image"))
    legs = sum(1 for o in data if o.get("fields", {}).get("parent_badge"))
    # Leg parent pks must all resolve to a pk within this fixture.
    pks = {o["pk"] for o in data}
    bad_parent = [o["pk"] for o in data
                  if o.get("fields", {}).get("parent_badge")
                  and o["fields"]["parent_badge"] not in pks]
    print(f"    {fn}: {len(data)} objects ({with_img} with images, {legs} legs)")
    if bad_parent:
        print(f"    !! {len(bad_parent)} leg parent pk(s) not in fixture: {bad_parent}")
PY

echo
echo "==> Row counts AFTER refresh (repo)"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
for name in ("Badge",):
    n = len(json.load(open(f"{d}/members.{name}.json")))
    print(f"    {name}: {n}")
PY

echo
echo "==> Review the diff before committing:"
echo
echo "    cd $REPO_ROOT"
echo "    git status --short loaddata/badges-demo/"
echo "    git diff --stat loaddata/badges-demo/"
echo
echo "Then commit via the normal feature-branch + PR flow (NEVER commit to main)."
