#!/usr/bin/env bash
#
# refresh_seed_from_tenant.sh
#
# Refreshes the knowledge-test seed fixtures in this repo by re-dumping the
# full "test bank" from a SOURCE tenant (default: tenant-ssc, which holds the
# large corpus of test questions) and SANITIZING them for portable import.
#
# Why sanitization is required (cross-tenant traps):
#   * Question.updated_by        -> Member FK.  The member only exists in the
#     source tenant; if left as a pk, `loaddata` FAILS against any other
#     tenant (it tries to resolve a nonexistent Member).  -> nulled.
#   * WrittenTestTemplate.created_by -> User FK.  Same problem.             -> nulled.
#   * Question.media             -> FileField under {CLUB_PREFIX}/media/...,
#     i.e. a per-tenant GCS path the target tenant does not have.           -> stripped.
# Categories, templates, the template-question through table, and presets have
# no member/user/media references and are exported verbatim.
#
# Models captured (the portable "test bank"):
#   knowledgetest.QuestionCategory
#   knowledgetest.Question
#   knowledgetest.WrittenTestTemplate
#   knowledgetest.WrittenTestTemplateQuestion   (the M2M through-table)
#   knowledgetest.TestPreset
#
# Deliberately EXCLUDED (per-member history, not part of a question bank):
#   WrittenTestAttempt, WrittenTestAnswer, WrittenTestAssignment
#
# What it does:
#   1. Locates a long-running app pod in the source tenant's namespace.
#   2. Dumps the five models inside that pod (plain FK pks, NOT --natural-foreign).
#   3. Copies the JSON into loaddata/knowledge-test-demo/ and sanitizes in place.
#   4. Prints before/after row counts and a per-file sanitization summary.
#   5. Prints a `git diff --stat` hint. It does NOT commit or push.
#
# Usage:
#   bash loaddata/knowledge-test-demo/refresh_seed_from_tenant.sh [namespace]
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
    "QuestionCategory|knowledgetest.QuestionCategory|knowledgetest.QuestionCategory.json"
    "Question|knowledgetest.Question|knowledgetest.Question.json"
    "WrittenTestTemplate|knowledgetest.WrittenTestTemplate|knowledgetest.WrittenTestTemplate.json"
    "WrittenTestTemplateQuestion|knowledgetest.WrittenTestTemplateQuestion|knowledgetest.WrittenTestTemplateQuestion.json"
    "TestPreset|knowledgetest.TestPreset|knowledgetest.TestPreset.json"
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
import json, os, sys
d = sys.argv[1]
for name in ("QuestionCategory", "Question", "WrittenTestTemplate",
             "WrittenTestTemplateQuestion", "TestPreset"):
    p = f"{d}/knowledgetest.{name}.json"
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
        python manage.py dumpdata "$MODEL" --indent 2 -o "/tmp/kt_$LABEL.json" 2>/dev/null
    kubectl cp "$NS/$POD:/tmp/kt_$LABEL.json" "$FIXTURE_DIR/knowledgetest.$LABEL.json" -c django 2>&1 \
        | grep -viE 'tar: Removing|exiting' || true
done
kubectl exec -n "$NS" -c django "$POD" -- bash -c 'rm -f /tmp/kt_*.json'

echo
echo "==> Sanitizing fixtures for portable import"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]

# Per-model field sanitization: field -> rule.
#   "null"  -> set the FK field to None (member/user only exists in source)
#   "strip" -> set the media FileField to None (per-tenant GCS path)
RULES = {
    "knowledgetest.question": {"updated_by": "null", "media": "strip"},
    "knowledgetest.writtentesttemplate": {"created_by": "null"},
    # QuestionCategory, WrittenTestTemplateQuestion, TestPreset have no
    # member/user/media references, so they are exported verbatim.
}

summary = {}
for fn in (
    "knowledgetest.QuestionCategory.json",
    "knowledgetest.Question.json",
    "knowledgetest.WrittenTestTemplate.json",
    "knowledgetest.WrittenTestTemplateQuestion.json",
    "knowledgetest.TestPreset.json",
):
    path = f"{d}/{fn}"
    with open(path) as fh:
        data = json.load(fh)
    nulls = strips = 0
    for obj in data:
        model = obj.get("model")
        fields = obj.get("fields", {})
        for fname, rule in RULES.get(model, {}).items():
            if rule == "null" and fields.get(fname) not in (None, ""):
                nulls += 1
                fields[fname] = None
            elif rule == "strip" and fields.get(fname) not in (None, ""):
                strips += 1
                fields[fname] = None
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    summary[fn] = (len(data), nulls, strips)

for fn, (n, nulls, strips) in summary.items():
    extras = []
    if nulls:
        extras.append(f"{nulls} member/user FK(s) nulled")
    if strips:
        extras.append(f"{strips} media path(s) stripped")
    suffix = (" (" + ", ".join(extras) + ")") if extras else " (no member/media refs)"
    print(f"    {fn}: {n} objects{suffix}")
PY

echo
echo "==> Row counts AFTER refresh (repo)"
python3 - "$FIXTURE_DIR" <<'PY'
import json, sys
d = sys.argv[1]
for name in ("QuestionCategory", "Question", "WrittenTestTemplate",
             "WrittenTestTemplateQuestion", "TestPreset"):
    n = len(json.load(open(f"{d}/knowledgetest.{name}.json")))
    print(f"    {name}: {n}")
PY

echo
echo "==> Review the diff before committing:"
echo
echo "    cd $REPO_ROOT"
echo "    git status --short loaddata/knowledge-test-demo/"
echo "    git diff --stat loaddata/knowledge-test-demo/"
echo
echo "Then commit via the normal feature-branch + PR flow (NEVER commit to main)."
