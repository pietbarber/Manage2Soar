#!/usr/bin/env bash
#
# import_syllabus_demo.sh
#
# Imports the "good-enough" training syllabus captured from the tenant-demo
# cluster into the CURRENT tenant (whichever DB this script's environment
# points at). It is intentionally safe-by-default:
#
#   * It REFUSES to run if the target tenant already has a training syllabus
#     (any TrainingPhase, TrainingLesson, or SyllabusDocument rows), unless
#     you explicitly pass --force.
#   * It loads the three seed models in a safe dependency order.
#   * It verifies the row counts after load and reports them.
#
# Intended use (production / per-tenant):
#   kubectl exec -n <tenant-ns> <app-pod> -- \
#       bash /app/loaddata/syllabus-demo/import_syllabus_demo.sh
#
# Local / dev use (with your Django env already active):
#   bash loaddata/syllabus-demo/import_syllabus_demo.sh
#
# Safety note: --force does NOT delete existing rows. loaddata upserts by
# (model, pk); rows with the same pk are replaced, other rows are left alone.
# If a target tenant has a genuinely different syllabus you do not want to
# clobber, do NOT use --force.

set -euo pipefail

FORCE=0
for arg in "$@"; do
    case "$arg" in
        -f|--force) FORCE=1 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg (see --help)" >&2
            exit 2
            ;;
    esac
done

# Resolve path to the fixture directory relative to this script, so the
# script works both from the repo root and from inside the container image.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR"

FIXTURES=(
    "instructors.TrainingPhase.json"
    "instructors.TrainingLesson.json"
    "instructors.SyllabusDocument.json"
)

for f in "${FIXTURES[@]}"; do
    if [[ ! -f "$FIXTURE_DIR/$f" ]]; then
        echo "ERROR: fixture not found: $FIXTURE_DIR/$f" >&2
        exit 1
    fi
done

echo "==> Preflight: checking that the target tenant has no existing training syllabus"

# Django's `manage.py shell -c` prints a line like
#     "95 objects imported automatically (use -v 2 for details)."
# to STDOUT before our own print() runs. We filter that out so we only see
# the three counts on a single line.
EMPTY="$(
    python manage.py shell -c '
from instructors.models import TrainingPhase, TrainingLesson, SyllabusDocument
print(
    TrainingPhase.objects.count(),
    TrainingLesson.objects.count(),
    SyllabusDocument.objects.count(),
)
' 2>/dev/null | grep -EoE '^[0-9]+ [0-9]+ [0-9]+$' | head -n1 || true
)"

if [[ -z "$EMPTY" ]]; then
    echo "    ERROR: could not read row counts from Django shell (unexpected output)." >&2
    echo "    Refusing to proceed without a reliable empty-check." >&2
    exit 4
fi

read -r PHASES LESSONS DOCS <<<"$EMPTY"
echo "    TrainingPhase:     $PHASES"
echo "    TrainingLesson:    $LESSONS"
echo "    SyllabusDocument:  $DOCS"

if [[ "$PHASES" -ne 0 || "$LESSONS" -ne 0 || "$DOCS" -ne 0 ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
        echo "    !! Existing syllabus detected, but --force was given. Proceeding (upsert, no delete)."
    else
        echo
        echo "ABORT: This tenant already has a training syllabus."
        echo "This script is meant for an EMPTY training program."
        echo
        echo "If you are absolutely sure you want to overwrite it, re-run with --force."
        echo "NOTE: --force upserts by primary key and does NOT delete extra rows."
        exit 3
    fi
fi

echo
echo "==> Loading training syllabus fixtures (dependency order)"
for f in "${FIXTURES[@]}"; do
    echo "    loaddata $f"
    python manage.py loaddata "$FIXTURE_DIR/$f"
done

echo
echo "==> Verifying loaded counts"

LOADED_COUNTS="$(
    python manage.py shell -c '
from instructors.models import TrainingPhase, TrainingLesson, SyllabusDocument
print(TrainingPhase.objects.count(), TrainingLesson.objects.count(), SyllabusDocument.objects.count())
' 2>/dev/null | grep -Eo '^[0-9]+ [0-9]+ [0-9]+$' | head -n1 || true
)"

if [[ -z "$LOADED_COUNTS" ]]; then
    echo "    ERROR: could not read post-load row counts from Django shell (unexpected output)." >&2
    exit 5
fi

read -r PHASES LESSONS DOCS <<<"$LOADED_COUNTS"
echo "    TrainingPhase:     $PHASES"
echo "    TrainingLesson:    $LESSONS"
echo "    SyllabusDocument:  $DOCS"

# Expected counts are derived from the fixture files themselves (not
# hardcoded), so the check stays correct across seed refreshes.
EXPECT="$(
    python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
counts = []
for m in ("TrainingPhase", "TrainingLesson", "SyllabusDocument"):
    with open(f"{d}/instructors.{m}.json") as fh:
        counts.append(str(len(json.load(fh))))
print(" ".join(counts))
PY
)"

if [[ -z "$EXPECT" ]]; then
    echo "    ERROR: could not compute expected counts from fixtures." >&2
    exit 6
fi

read -r EXP_PHASES EXP_LESSONS EXP_DOCS <<<"$EXPECT"
if [[ "$PHASES" -ne "$EXP_PHASES" || "$LESSONS" -ne "$EXP_LESSONS" || "$DOCS" -ne "$EXP_DOCS" ]]; then
    echo "    ERROR: unexpected counts after import (expected: $EXP_PHASES $EXP_LESSONS $EXP_DOCS)." >&2
    exit 6
fi

echo
echo "==> Done. Training syllabus import complete."
