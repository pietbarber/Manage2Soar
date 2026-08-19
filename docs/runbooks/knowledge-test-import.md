# Knowledge Test Bank Import Runbook

This runbook explains how to copy the **knowledge test "test bank"** (the large
corpus of written-test questions, categories, test templates, and presets) out
of one tenant (the reference `tenant-ssc` cluster) and import it into
**another** tenant.

It follows the **IaC-first** philosophy: the seed fixtures and the import/refresh
scripts live **in the repo** so the operation is reproducible, reviewable, and
does not depend on copying files around by hand.

> This mirrors the [Training Syllabus Import](syllabus-import.md) runbook. The
> two seeds are independent and do not interfere with each other.

## 🎯 Quick Reference

| Operation | Command |
|-----------|---------|
| **Refresh the repo seed from a source tenant** | `bash loaddata/knowledge-test-demo/refresh_seed_from_tenant.sh` |
| Refresh from a specific source tenant | `bash loaddata/knowledge-test-demo/refresh_seed_from_tenant.sh tenant-ssc` |
| **Import into an empty tenant (safe, recommended)** | `bash loaddata/knowledge-test-demo/import_knowledge_test_demo.sh` |
| Force-load (upsert, **no delete**) | `bash loaddata/knowledge-test-demo/import_knowledge_test_demo.sh --force` |

## What "the knowledge test bank" is

The written-test engine is modeled by five models in the `knowledgetest` app.
Four of them are **club-owned content** and safe to move between tenants; the
fifth set (attempts/answers/assignments) is **member-specific history** and is
**excluded** from this seed.

| Model | Purpose | Row count in this seed |
|-------|---------|------------------------|
| `knowledgetest.QuestionCategory` | Categories/topics a question belongs to (PK = `code`) | 15 |
| `knowledgetest.Question` | Individual questions (A–D, HTML, explanation) | 276 |
| `knowledgetest.WrittenTestTemplate` | Named test templates (pass %, time limit) | 44 |
| `knowledgetest.WrittenTestTemplateQuestion` | M2M through-table linking templates → questions (ordered) | 1752 |
| `knowledgetest.TestPreset` | Presets of category weights (e.g. "Pilot") | 5 |

> ⚠️ **Excluded (member-specific):** `WrittenTestAttempt`, `WrittenTestAnswer`,
> `WrittenTestAssignment`. These record a *member's* performance and are tied to
> `Member`/`User` rows that do not exist in the target tenant. Do **not** include
> them when moving a test bank between clubs.

## Cross-tenant sanitization (why this seed is portable)

Two `knowledgetest` models point at identities that only exist in the **source**
tenant. If left as-is, `loaddata` in another tenant would fail with an
unresolvable FK. The **refresh script sanitizes them at capture time**:

| Field | Model | Problem | Sanitization |
|-------|-------|---------|--------------|
| `Question.updated_by` (FK→`Member`) | Question | Member PK only valid in source tenant | set to `null` |
| `WrittenTestTemplate.created_by` (FK→`User`) | WrittenTestTemplate | User PK only valid in source tenant | set to `null` |
| `Question.media` (FileField) | Question | per-tenant GCS path (`{CLUB_PREFIX}/media/...`) | set to empty |
| `WrittenTestTemplate.name` (display title) | WrittenTestTemplate | source names embed instructor names (e.g. "Test by <name> on <date>") | generalized to `Written test <pk>`; the meaningful test type is retained in the preserved `description` |

Because of this, the seed loads cleanly into **any** tenant with no dangling
`Member`/`User`/file references and no leaked source-club instructor names. **Trade-off:** the target tenant loses the
"last updated by" attribution and any question images/files — a club that needs
question media must upload it locally after import (there is no way to copy a
per-tenant GCS object into another tenant's GCS layout from this seed).

## Repo layout

```
loaddata/knowledge-test-demo/
├── import_knowledge_test_demo.sh          # safe import script (preflight + load + verify)
├── refresh_seed_from_tenant.sh            # refresh repo fixtures from a source tenant (with sanitization)
├── knowledgetest.QuestionCategory.json    # 15 categories
├── knowledgetest.Question.json            # 276 questions
├── knowledgetest.WrittenTestTemplate.json # 44 templates
├── knowledgetest.WrittenTestTemplateQuestion.json  # 1752 through-rows
└── knowledgetest.TestPreset.json          # 5 presets
```

This is a **separate, named seed set**. Do not confuse it with the old
`loaddata/knowledgetest_dump.json` (Issue #19), which **is not** portable (it
carries `updated_by` Member PKs) and should not be used for cross-tenant import.

---

## Step 0 — Prerequisites

- `kubectl` authenticated to the GKE cluster
  (`gcloud auth login` + `gcloud container clusters get-credentials
  manage2soar-cluster --region us-east1`).
- You know the **target** tenant's namespace (e.g. `tenant-masa`) and, if
  refreshing, the **source** tenant's namespace (default `tenant-ssc`).

### Find a tenant's app pod

```bash
NS=tenant-masa   # <-- the tenant you mean
POD=$(kubectl get pods -n "$NS" -o name \
  | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' \
  | head -1 | sed -E 's#^pods?/##')
```

The long-running pod (not the cronjob one-shots) is the one to `exec` into. The
Django container is named `django`.

---

## Step 1 — Refresh the repo seed from a source tenant

Only needed **if you are (re)capturing** the seed (e.g. `tenant-ssc` added
questions, or you want to seed from a different source club). The fixtures
already committed in `loaddata/knowledge-test-demo/` were captured from
`tenant-ssc`.

```bash
# From the default source (tenant-ssc):
bash loaddata/knowledge-test-demo/refresh_seed_from_tenant.sh

# Or from an explicit source namespace:
bash loaddata/knowledge-test-demo/refresh_seed_from_tenant.sh tenant-ssc
```

The script:

1. Dumps the five models via `dumpdata` **inside the source tenant's app pod**
   (so DB credentials are correct), without `--natural-foreign` (deliberate —
   FKs stay integer PKs so they can be nulled).
2. Copies the JSON out with `kubectl cp`.
3. **Sanitizes** (`updated_by`/`created_by` → null, `media` → empty) and prints
   how many of each were nulled/stripped.
4. Prints before/after object counts.

It does **not** commit. Review the diff, then commit via a feature branch + PR
(**never** push to `main` directly).

---

## Step 2 — Import into the target tenant

The import script is **safe-by-default**. It:

1. **Preflights**: counts the five models in the **target** tenant.
2. **Aborts** (exit code 3) if the target already has questions, unless you pass
   `--force`.
3. Loads the five fixtures in dependency order
   (Category → Question → Template → Through → Preset).
4. **Verifies** that every fixture primary key is now present in the target, and
   prints the resulting counts.

### Recommended: run inside the target tenant's app pod

```bash
NS=tenant-masa   # <-- target tenant
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed -E 's#^pods?/##')

# The deployed image does not always ship the repo's loaddata/ tree, so copy it in:
kubectl cp "loaddata/knowledge-test-demo" "$NS/$POD:/tmp/kseed" -c django

kubectl exec -n "$NS" -c django "$POD" -- \
  bash /tmp/kseed/import_knowledge_test_demo.sh
```

Expected output on a clean (empty) target:

```
==> Preflight: checking that the target tenant has no existing test bank
    QuestionCategory:            0
    Question:                    0
    WrittenTestTemplate:         0
    WrittenTestTemplateQuestion: 0
    TestPreset:                  0

==> Loading test bank fixtures (dependency order)
    loaddata knowledgetest.QuestionCategory.json
    ...
==> Verifying that every fixture primary key is now present in the target
                      QuestionCategory: fixture=15 present=   15  all_present=True
                              Question: fixture=276 present=  276  all_present=True
                   WrittenTestTemplate: fixture=44 present=   44  all_present=True
           WrittenTestTemplateQuestion: fixture=1752 present= 1752  all_present=True
                            TestPreset: fixture=5 present=    5  all_present=True

==> Done. Knowledge test bank import complete.
```

Expected output on a tenant that **already** has a test bank (script refuses):

```
==> Preflight: checking that the target tenant has no existing test bank
    QuestionCategory:            16
    Question:                    276
    ...

ABORT: This tenant already has a knowledge test bank (276 questions).
This script is meant for an EMPTY test bank.

If you are absolutely sure you want to overwrite it, re-run with --force.
NOTE: --force upserts by primary key and does NOT delete extra rows.
```

> 🖊️ **Per-club review:** the seed is the *reference club's* test bank. After
> import, the receiving club **must review** categories, questions, templates,
> and presets in the admin (`knowledgetest`) and adjust wording/answers to their
> own syllabus and standards before using it to grade members.

---

## Rollback

**Destructive delete** — confirm the target tenant is the right one first.
Delete children before parents to respect FK constraints (the M2M through-table
references both templates and questions).

```bash
NS=tenant-masa
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed -E 's#^pods?/##')

kubectl exec -n "$NS" -c django "$POD" -- python manage.py shell -c '
from knowledgetest.models import (
    WrittenTestTemplateQuestion, WrittenTestTemplate,
    Question, QuestionCategory,
)
# Order matters: through-table first, then templates, then questions, then categories.
WrittenTestTemplateQuestion.objects.delete()
WrittenTestTemplate.objects.delete()
Question.objects.delete()
QuestionCategory.objects.delete()
print("rolled back")
'
```

> If the target tenant had **its own** pre-existing test bank that you upserted
> over with `--force`, this rollback will also delete the club's original rows —
> there is no way to distinguish them afterward. Prefer testing `--force` against
> a scratch/demo tenant first.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `container django-app-demo is not valid for pod ...` | Wrong `-c` container name | Use `-c django` (container is named `django`) |
| `ABORT: This tenant already has a knowledge test bank` | Target is not empty | Intended protection. Use `--force` only if you truly want an upsert, or roll back first. |
| `django.core.exceptions.ImproperlyConfigured` | Ran `manage.py` without the tenant env | Run **inside** the tenant pod (env already set) — not locally with the wrong `DB_*`. |
| `IntegrityError` on `loaddata` | Out-of-order load / stale rows | Load in the fixed order Category → Question → Template → Through → Preset; roll back and retry. |
| `ERROR: fixture not found: ...` | Ran the script without the fixtures next to it | `kubectl cp` the whole `loaddata/knowledge-test-demo` dir first, then run the script from there. |
| Verification shows a `missing` pk | Partial load / aborted mid-import | Roll back, re-run cleanly. |

### `--force` semantics (important)

`loaddata` **upserts by primary key**. For a non-empty target:

- Fixture pks that already exist in the target are **replaced** with the fixture
  values.
- Target rows with pks **not** in the fixture are **left alone** (not deleted).
- The result is a **mixture** of the target's original rows and the seed's rows.

The post-load count is therefore **not** required to equal the fixture count;
the script instead verifies that **every fixture pk is present**, which holds in
both the empty and the collision cases.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | A fixture file is missing |
| 2 | Unknown CLI argument |
| 3 | Target not empty and `--force` not given |
| 4 | Could not read pre-load counts |
| 5 | Post-load verification failed (missing pk / unreadable counts) |

---

## Safety & policy reminders

- **Never** commit to `main`. Use `feature/...` + PR.
- **Never** `--force` against a tenant you are not sure about — it upserts by PK
  and **does not delete** extra rows, so you can end up with a mixture of the
  club's own and the seed's questions.
- This runbook only moves **test-bank content** (categories, questions,
  templates, presets). Member test **attempts/answers/assignments are
  member-owned** and must not be copied between clubs.
- After any `--force` upsert on a tenant that had its own bank, treat the result
  as needing a **human review** before it is used to grade anyone.
