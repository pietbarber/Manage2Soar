# Training Syllabus Import Runbook

This runbook explains how to copy a known-good **training syllabus** out of one
tenant (the reference `tenant-demo` cluster) and import it into **another**
tenant that has an **empty** training program.

It is written for the "IaC-first" philosophy: the fixture and the import script
live **in the repo** so the operation is reproducible, reviewable, and does not
depend on copying files around by hand.

## 🎯 Quick Reference

| Operation | Command |
|-----------|---------|
| Dump the syllabus from a source tenant | See [Step 1](#step-1--dump-the-syllabus-from-the-source-tenant) |
| Import into an empty tenant (safe, recommended) | `bash loaddata/syllabus-demo/import_syllabus_demo.sh` |
| Inspect what a target tenant already has | See [Preflight](#step-2--import-into-the-target-tenant) |
| Force-load (upsert, **no delete**) | `bash loaddata/syllabus-demo/import_syllabus_demo.sh --force` |

## What "the training syllabus" is

The training program is modeled by three **self-contained** models in the
`instructors` app. None of them reference members, so they are safe to move
between tenants:

| Model | Purpose | Row count in this seed |
|-------|---------|------------------------|
| `instructors.TrainingPhase` | Phases that group lessons (e.g. "Before We Fly") | 9 |
| `instructors.TrainingLesson` | Individual lessons (code, title, HTML, FAR/PTS refs) | 88 |
| `instructors.SyllabusDocument` | Header / supplemental documents keyed by slug | 1 |

> ⚠️ The **other** models in `instructors` (`InstructionReport`, `LessonScore`,
> `GroundInstruction`, `GroundLessonScore`, `MemberQualification`,
> `StudentProgressSnapshot`, `ClubQualificationType`) are **member-specific or
> tenant-specific** and are **NOT** part of this seed. Do not include them when
> moving a syllabus between clubs.

## Repo layout

```
loaddata/syllabus-demo/
├── import_syllabus_demo.sh          # safe import script (preflight + load + verify)
├── instructors.TrainingPhase.json   # 9 phases
├── instructors.TrainingLesson.json  # 88 lessons
└── instructors.SyllabusDocument.json# 1 document (slug "header")
```

This is a **separate, named seed set** alongside the existing canonical seed in
`loaddata/instructors.*.json`. The two do not overwrite each other:

- `loaddata/instructors.*.json` + `loaddata/loaddata.sh` → the **default** seed
  applied to every new tenant.
- `loaddata/syllabus-demo/*` → the **demo syllabus** variant, applied **on
  demand** to a specific club that wants this particular curriculum.

---

## Step 0 — Prerequisites

- `kubectl` authenticated to the GKE cluster (`gcloud auth login`, and for
  GKE specifically `gcloud container clusters get-credentials manage2soar-cluster --region us-east1`).
- `gsutil`/`gcloud` access for the target project (not required for the DB
  steps, only if you need to peek at the DB host).
- You know the target tenant's **Kubernetes namespace** (e.g. `tenant-masa`,
  `tenant-svs`, `tenant-hh`).

### Find the target tenant's app pod

```bash
NS=tenant-masa   # <-- change to the target tenant
kubectl get pods -n "$NS" -o name \
  | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' \
  | head -1
```

The long-running pod (not the cronjob one-shots) is the one to `exec` into. The
Django container is named `django`.

---

## Step 1 — Dump the syllabus from the source tenant

This is only needed **if you are (re)capturing the seed from a different source
tenant**. The files already committed in `loaddata/syllabus-demo/` were dumped
from `tenant-demo`.

Run `dumpdata` **inside the source tenant's app pod** (it already has the right
DB credentials in its environment) and copy the JSON out:

```bash
SRC_NS=tenant-demo
SRC_POD=$(kubectl get pods -n "$SRC_NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed 's#pods/##')

for M in TrainingPhase TrainingLesson SyllabusDocument; do
  kubectl exec -n "$SRC_NS" -c django "$SRC_POD" -- \
    python manage.py dumpdata "instructors.$M" --natural-foreign --indent 2 \
    -o "/tmp/$M.json"
  kubectl cp "$SRC_NS/$SRC_POD:/tmp/$M.json" \
    "loaddata/syllabus-demo/instructors.$M.json" -c django
done

# Verify counts
python3 -c '
import json
for m in ("TrainingPhase","TrainingLesson","SyllabusDocument"):
    d=json.load(open(f"loaddata/syllabus-demo/instructors.{m}.json"))
    print(m, len(d))
'
```

Commit the JSON (and this runbook) via a feature branch + PR — **never** push
directly to `main`.

> 💡 `--natural-foreign` uses natural keys where the model supports them. The
> three syllabus models are loaded with plain integer PKs; `loaddata` handles
> the cross-refs between them automatically because it is given all three files.

---

## Step 2 — Import into the target tenant

The import script is **safe-by-default**. It:

1. **Preflights**: counts `TrainingPhase`, `TrainingLesson`, and
   `SyllabusDocument` in the **target** tenant.
2. **Aborts** (exit code 3) if **any** of those counts are non-zero, unless you
   pass `--force`.
3. Loads the three fixtures in dependency order.
4. Verifies and prints the resulting counts.

### Recommended: run inside the target tenant's app pod

```bash
NS=tenant-masa   # <-- target tenant
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed 's#pods/##')

kubectl exec -n "$NS" -c django "$POD" -- \
  bash /app/loaddata/syllabus-demo/import_syllabus_demo.sh
```

Expected output on a clean (empty) target:

```
==> Preflight: checking that the target tenant has no existing training syllabus
    TrainingPhase:     0
    TrainingLesson:    0
    SyllabusDocument:  0

==> Loading training syllabus fixtures (dependency order)
    loaddata instructors.TrainingPhase.json
    ...
==> Verifying loaded counts
    TrainingPhase:      9
    TrainingLesson:     88
    SyllabusDocument:   1

==> Done. Training syllabus import complete.
```

Expected output on a tenant that **already** has a syllabus (script refuses):

```
==> Preflight: checking that the target tenant has no existing training syllabus
    TrainingPhase:     9
    TrainingLesson:    63
    SyllabusDocument:  2

ABORT: This tenant already has a training syllabus.
...
```

### If the pod does not have the script mounted

Some images may not ship the repo's `loaddata/` tree at runtime. In that case,
`kubectl cp` the fixture directory in first, then run the script:

```bash
NS=tenant-masa
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed 's#pods/##')

kubectl cp "loaddata/syllabus-demo" "$NS/$POD:/tmp/syllabus-demo" -c django
kubectl exec -n "$NS" -c django "$POD" -- \
  bash /tmp/syllabus-demo/import_syllabus_demo.sh
```

### Manual (no script) — if you prefer raw commands

Only do this if you cannot use the script. The preflight check is on **you**:

```bash
NS=tenant-masa
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed 's#pods/##')

# 1) Verify the target is empty (all three MUST be 0)
kubectl exec -n "$NS" -c django "$POD" -- python manage.py shell -c \
  'from instructors.models import TrainingPhase as P, TrainingLesson as L, SyllabusDocument as D;
   print(P.objects.count(), L.objects.count(), D.objects.count())'

# 2) Copy fixtures in
kubectl cp "loaddata/syllabus-demo" "$NS/$POD:/tmp/syllabus-demo" -c django

# 3) Load in dependency order
kubectl exec -n "$NS" -c django "$POD" -- \
  python manage.py loaddata /tmp/syllabus-demo/instructors.TrainingPhase.json
kubectl exec -n "$NS" -c django "$POD" -- \
  python manage.py loaddata /tmp/syllabus-demo/instructors.TrainingLesson.json
kubectl exec -n "$NS" -c django "$POD" -- \
  python manage.py loaddata /tmp/syllabus-demo/instructors.SyllabusDocument.json
```

---

## Step 3 — Verify in the UI

1. Open the tenant's site (e.g. `https://masa.manage2soar.com/`).
2. As an instructor, navigate to **Training → Syllabus**.
   - Confirm the header document renders (`/TRAINING/syllabus/`).
   - Confirm all phases and lessons appear and sort correctly (natural
     ordering via `sort_key`).
3. Spot-check a lesson's FAR/PTS references and HTML content.

> 🖊️ **Per-club branding**: the `header` SyllabusDocument is club-branded
> (title + HTML). The version in this seed was authored on `tenant-demo` and
> currently reads **"Demo Soaring Club"** with a sample checklist row. After
> import, the receiving club should edit this document via the admin
> (`instructors → syllabus document`) or `edit_syllabus_document` view to
> reflect their own club name and any club-specific front matter.
>
> The `TrainingPhase` and `TrainingLesson` rows are curriculum content (FAR/PTS
> references, lesson objectives, etc.) and should generally be left as-is.

---

## Rollback

Because the three models are **independent** of member data, rolling back an
import is safe and simple. **This is a destructive delete** — confirm the target
tenant is the right one first.

```bash
NS=tenant-masa
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed 's#pods/##')

kubectl exec -n "$NS" -c django "$POD" -- python manage.py shell -c '
from instructors.models import TrainingPhase, TrainingLesson, SyllabusDocument
TrainingLesson.objects.delete()
SyllabusDocument.objects.delete()
TrainingPhase.objects.delete()
'
```

> Order matters: delete children (`TrainingLesson`, `SyllabusDocument`) before
> the parent (`TrainingPhase`) to avoid FK integrity issues.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `container django-app-demo is not valid for pod ...` | Wrong `-c` container name | Use `-c django` (container is named `django`) |
| `ABORT: This tenant already has a training syllabus` | Target is not empty | Intended protection. Use `--force` only if you truly want an upsert, or roll back first. |
| `django.core.exceptions.ImproperlyConfigured` | Ran `manage.py` without the tenant env | Run inside the tenant pod (env is already set) — do **not** run locally with the wrong `DB_*` env. |
| `IntegrityError` on `loaddata` | Partial load / stale rows | Roll back, then re-run. Ensure you load Phase → Lesson → Document in that order. |
| `command not found: bash` in pod | Slim image without bash | The script uses `#!/usr/bin/env bash`; if absent, run the manual (raw `loaddata`) steps above. |

## Safety & policy reminders

- **Never** commit to `main`. Use `feature/...` + PR.
- **Never** `--force` against a tenant you are not sure about — it upserts by
  PK and **does not delete** extra rows, so you can end up with a mixture of
  old and new lessons.
- This runbook only moves **curriculum** (syllabus) data. Member training
  progress, instruction reports, and scores are **member-owned** and must not
  be copied between clubs.
