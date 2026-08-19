#!/usr/bin/env bash
#
# import_knowledge_test_demo.sh
#
# Imports the portable knowledge-test "test bank" captured from the
# tenant-ssc cluster (the large corpus of test questions) into the CURRENT
# tenant (whichever DB this script's environment points at).
#
# The seed is ALREADY SANITIZED for cross-tenant import:
#   * Question.updated_by            nulled  (Member only exists in source)
#   * WrittenTestTemplate.created_by nulled  (User only exists in source)
#   * Question.media                 nulled  (per-tenant GCS path)
# So `loaddata` resolves cleanly against ANY tenant with no dangling Member
# or File references.
#
# What it imports (dependency order):
#   QuestionCategory -> Question -> WrittenTestTemplate ->
#   WrittenTestTemplateQuestion (M2M through) -> TestPreset
#
# It is intentionally SAFE-BY-DEFAULT:
#   * REFUSES to run if the target tenant already has a test bank (any
#     Question rows) unless you explicitly pass --force.
#   * Verifies after load that every fixture primary key is present in the
#     target (holds whether the target started empty or with overlapping pks).
#
# Intended use (production / per-tenant):
#   kubectl exec -n <tenant-ns> <app-pod> -- \
#       bash /app/loaddata/knowledge-test-demo/import_knowledge_test_demo.sh
#
# Local / dev use (with your Django env already active):
#   bash loaddata/knowledge-test-demo/import_knowledge_test_demo.sh
#
# Safety note: --force does NOT delete existing rows. loaddata upserts by
# (model, pk); rows with the same pk are replaced, other rows are left alone.
# If the target tenant has a genuinely different test bank you do not want to
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

# Resolve the fixture directory relative to this script, so the script works
# both from the repo root and from inside the container image.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR"
export FIXTURE_DIR

# Load in dependency order (categories -> questions -> templates -> through -> presets).
FIXTURES=(
    "knowledgetest.QuestionCategory.json"
    "knowledgetest.Question.json"
    "knowledgetest.WrittenTestTemplate.json"
    "knowledgetest.WrittenTestTemplateQuestion.json"
    "knowledgetest.TestPreset.json"
)

for f in "${FIXTURES[@]}"; do
    if [[ ! -f "$FIXTURE_DIR/$f" ]]; then
        echo "ERROR: fixture not found: $FIXTURE_DIR/$f" >&2
        exit 1
    fi
done

echo "==> Preflight: checking that the target tenant has no existing test bank"

# Django's `manage.py shell -c` prints a line like
#     "95 objects imported automatically (use -v 2 for details)."
# to STDOUT before our own print() runs. Filter it out so we only see the
# five counts on a single line.
EMPTY="$(
    python manage.py shell -c '
from knowledgetest.models import (
    QuestionCategory, Question, WrittenTestTemplate,
    WrittenTestTemplateQuestion, TestPreset,
)
print(
    QuestionCategory.objects.count(),
    Question.objects.count(),
    WrittenTestTemplate.objects.count(),
    WrittenTestTemplateQuestion.objects.count(),
    TestPreset.objects.count(),
)
' 2>/dev/null | grep -EoE '^[0-9]+ [0-9]+ [0-9]+ [0-9]+ [0-9]+$' | head -n1 || true
)"

if [[ -z "$EMPTY" ]]; then
    echo "    ERROR: could not read row counts from Django shell (unexpected output)." >&2
    echo "    Refusing to proceed without a reliable empty-check." >&2
    exit 4
fi

read -r PRE_CATS PRE_QNS PRE_TMPLS PRE_THRU PRE_PRESETS <<<"$EMPTY"
echo "    QuestionCategory:            $PRE_CATS"
echo "    Question:                    $PRE_QNS"
echo "    WrittenTestTemplate:         $PRE_TMPLS"
echo "    WrittenTestTemplateQuestion: $PRE_THRU"
echo "    TestPreset:                  $PRE_PRESETS"

# Question is the anchor for "does a test bank already exist?"
if [[ "$PRE_QNS" -ne 0 ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
        echo "    !! Existing test bank detected, but --force was given. Proceeding (upsert, no delete)."
    else
        echo
        echo "ABORT: This tenant already has a knowledge test bank ($PRE_QNS questions)."
        echo "This script is meant for an EMPTY test bank."
        echo
        echo "If you are absolutely sure you want to overwrite it, re-run with --force."
        echo "NOTE: --force upserts by primary key and does NOT delete extra rows."
        exit 3
    fi
fi

echo
echo "==> Loading test bank fixtures (dependency order)"
for f in "${FIXTURES[@]}"; do
    echo "    loaddata $f"
    python manage.py loaddata "$FIXTURE_DIR/$f"
done

echo
echo "==> Verifying that every fixture primary key is now present in the target"

# `loaddata` upserts by primary key without deleting other rows. For an
# EMPTY tenant this means post_count == fixture_count; for a NON-EMPTY
# tenant with overlapping pks the counts will be higher than the fixture
# (existing rows preserved) and the delta will be LOWER than the fixture
# (overlapping pks were updated, not added). The invariant that holds for
# BOTH cases is: every primary key from each fixture is now present in
# the target database.

VERIFY="$(
    python manage.py shell -c '
import json, os
d = os.environ["FIXTURE_DIR"]
from knowledgetest.models import (
    QuestionCategory, Question, WrittenTestTemplate,
    WrittenTestTemplateQuestion, TestPreset,
)
MODELS = [
    ("knowledgetest.QuestionCategory.json",            QuestionCategory),
    ("knowledgetest.Question.json",                    Question),
    ("knowledgetest.WrittenTestTemplate.json",         WrittenTestTemplate),
    ("knowledgetest.WrittenTestTemplateQuestion.json", WrittenTestTemplateQuestion),
    ("knowledgetest.TestPreset.json",                  TestPreset),
]
failures = 0
for fname, model in MODELS:
    fixture_pks = {o["pk"] for o in json.load(open(os.path.join(d, fname)))}
    present   = set(model.objects.values_list("pk", flat=True))
    missing   = fixture_pks - present
    updated   = fixture_pks & present
    print(f"{model.__name__:>34}: fixture={len(fixture_pks)} present={len(present):>5}  "
          f"all_present={not missing}")
    if missing:
        failures += 1
        print(f"    MISSING pks ({len(missing)}): {sorted(missing)[:10]}")
if failures:
    raise SystemExit(1)
' 2>&1
)"

echo "$VERIFY" | sed 's/^/    /'

# The inner python exits non-zero on any missing pk; capture that.
if [[ -z "$VERIFY" ]] || ! echo "$VERIFY" | grep -q "all_present=True"; then
    echo "    ERROR: at least one fixture primary key is missing from the target." >&2
    exit 5
fi
# Guard: make sure every one of the 5 models reported all_present=True.
if ! echo "$VERIFY" | grep -c "all_present=True" | grep -q "^5$"; then
    echo "    ERROR: not all 5 models verified." >&2
    exit 5
fi

# Post-load counts (informational only).
POST="$(
    python manage.py shell -c '
from knowledgetest.models import (
    QuestionCategory, Question, WrittenTestTemplate,
    WrittenTestTemplateQuestion, TestPreset,
)
print(
    QuestionCategory.objects.count(),
    Question.objects.count(),
    WrittenTestTemplate.objects.count(),
    WrittenTestTemplateQuestion.objects.count(),
    TestPreset.objects.count(),
)
' 2>/dev/null | grep -EoE '^[0-9]+ [0-9]+ [0-9]+ [0-9]+ [0-9]+$' | head -n1 || true
)"
if [[ -n "$POST" ]]; then
    read -r PC PQ PT PTH PP <<<"$POST"
    echo
    echo "    Post-load counts:"
    echo "      QuestionCategory:            $PC   (pre: $PRE_CATS)"
    echo "      Question:                    $PQ   (pre: $PRE_QNS)"
    echo "      WrittenTestTemplate:         $PT   (pre: $PRE_TMPLS)"
    echo "      WrittenTestTemplateQuestion: $PTH   (pre: $PRE_THRU)"
    echo "      TestPreset:                  $PP   (pre: $PRE_PRESETS)"
fi

echo
echo "==> Done. Knowledge test bank import complete."
echo
echo "NOTE: the seed is sanitized for portability. In this corpus, question"
echo "media (images/files) and the member 'updated_by' attribution were nulled"
echo "because they do not exist in the target tenant. If the target tenant"
echo "had a pre-existing test bank with overlapping primary keys, those rows"
echo "were UPDATED (not deleted) with the fixture content. Review the test"
echo "bank in the admin to confirm the content meets this club's needs."
