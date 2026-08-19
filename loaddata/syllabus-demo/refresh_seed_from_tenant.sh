#!/usr/bin/env bash
#
# refresh_seed_from_tenant.sh
#
# Refreshes the syllabus-demo seed fixtures in this repo by re-dumping them
# from a SOURCE tenant (default: tenant-demo, the known-good reference).
#
# Use this whenever the source tenant's syllabus has been edited in the admin
# (HTML fixes, new lessons, reordering phases, etc.) and the repo copy needs
# to be brought back in line.
#
# What it does:
#   1. Locates a long-running app pod in the source tenant's namespace.
#   2. Runs `dumpdata` for the three syllabus models inside that pod.
#   3. Copies the JSON into loaddata/syllabus-demo/ (overwriting in place).
#   4. Prints before/after row counts for the three models.
#   5. Prints a `git diff --stat` hint so you can review what changed.
#
# It does NOT commit or push. Review the diff yourself, then commit via the
# normal feature-branch + PR flow.
#
# Usage:
#   bash loaddata/syllabus-demo/refresh_seed_from_tenant.sh [namespace]
#     namespace   optional, defaults to tenant-demo
#
# Requirements: kubectl authenticated to the cluster, repo checked out.

set -euo pipefail

NS="${1:-tenant-demo}"

# Resolve repo paths relative to this script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

FIXTURES=(
    "instructors.TrainingPhase.json"
    "instructors.TrainingLesson.json"
    "instructors.SyllabusDocument.json"
)

echo "==> Source namespace: $NS"

POD="$(kubectl get pods -n "$NS" -o name \
        | grep -E 'django-app' \
        | grep -vE 'clearsessions|expire|notify|process|send|cron' \
        | head -1 | sed -E 's#^pods?/##')"

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
for m in ("TrainingPhase", "TrainingLesson", "SyllabusDocument"):
    try:
        n = len(json.load(open(f"{d}/instructors.{m}.json")))
        print(f"    {m}: {n}")
    except FileNotFoundError:
        print(f"    {m}: (missing)")
PY

echo
echo "==> Dumping from source tenant"
for M in TrainingPhase TrainingLesson SyllabusDocument; do
    echo "    dumpdata instructors.$M"
    kubectl exec -n "$NS" -c django "$POD" -- \
        python manage.py dumpdata "instructors.$M" --natural-foreign --indent 2 \
        -o "/tmp/$M.json" 2>/dev/null
    kubectl cp "$NS/$POD:/tmp/$M.json" "$FIXTURE_DIR/instructors.$M.json" -c django 2>&1 \
        | grep -viE 'tar: Removing|exiting' || true
done
kubectl exec -n "$NS" -c django "$POD" -- rm -f \
    /tmp/TrainingPhase.json /tmp/TrainingLesson.json /tmp/SyllabusDocument.json

echo
echo "==> Row counts AFTER refresh (repo)"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
for m in ("TrainingPhase", "TrainingLesson", "SyllabusDocument"):
    n = len(json.load(open(f"{d}/instructors.{m}.json")))
    print(f"    {m}: {n}")
PY

echo
echo "==> Review the diff before committing:"
echo
echo "    cd $REPO_ROOT"
echo "    git status --short loaddata/syllabus-demo/"
echo "    git diff --stat loaddata/syllabus-demo/"
echo "    git diff loaddata/syllabus-demo/"   # spot-check HTML changes
echo
echo "Then commit via the normal feature-branch + PR flow (NEVER commit to main)."
