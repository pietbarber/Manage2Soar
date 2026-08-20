# Club Qualifications Import Runbook

This runbook explains how to copy the **club's qualification catalog** (the
list of qualification types a club recognizes — CFI, ASK-21 endorsements,
tow-pilot endorsements, etc.) out of one tenant (the reference `tenant-ssc`
cluster, which holds the "good-enough" set) and import it into **another**
tenant, including the icon images that go with each qualification.

It follows the **IaC-first** philosophy: the seed fixture and the import/refresh
scripts live **in the repo** so the operation is reproducible, reviewable, and
does not depend on copying files around by hand.

> This mirrors the [Knowledge Test Bank Import](knowledge-test-import.md) and
> [Training Syllabus Import](syllabus-import.md) runbooks. The three seeds are
> independent and do not interfere with each other.

## 🎯 Quick Reference

| Operation | Command |
|-----------|---------|
| **Refresh the repo seed from a source tenant** | `bash loaddata/club-qualifications-demo/refresh_seed_from_tenant.sh` |
| Refresh from a specific source tenant | `bash loaddata/club-qualifications-demo/refresh_seed_from_tenant.sh tenant-ssc` |
| **Import into an empty tenant (safe, recommended)** | `bash loaddata/club-qualifications-demo/import_club_qualifications_demo.sh` |
| Force-load (upsert, **no delete**) | `bash loaddata/club-qualifications-demo/import_club_qualifications_demo.sh --force` |
| Skip the icon copy (re-upload icons later) | `bash loaddata/club-qualifications-demo/import_club_qualifications_demo.sh --no-icons` |
| Force-copy icons over existing objects | `bash loaddata/club-qualifications-demo/import_club_qualifications_demo.sh --overwrite-icons` |
| Copy icons from a non-default source prefix | `bash loaddata/club-qualifications-demo/import_club_qualifications_demo.sh --source-prefix masa` |

## What "club qualifications" is

The club's qualification catalog is modeled by a single model in the
`instructors` app. It is **club-owned content** and safe to move between
tenants.

| Model | Purpose | Row count in this seed |
|-------|---------|------------------------|
| `instructors.ClubQualificationType` | Qualification types the club recognizes (code, name, icon, scope, tooltip) | 30 |

> ⚠️ **Excluded (member-specific):** `instructors.MemberQualification`.
> This model records *which member holds which qualification*, plus the
> instructor who awarded it, the award date, and the expiration date. It
> references `Member` rows that only exist in the source tenant. Do **not**
> include it when moving the catalog between clubs — the new tenant's members
> will earn their qualifications through normal club processes.

## Why we copy icons (not strip them)

The `icon` field is an `ImageField` with a **prefix-free relative path**
(e.g. `quals/icons/CFI-abc123.jpg`). In production, `MEDIA_URL` is
constructed from the **rendering tenant's** `CLUB_PREFIX`:

```
https://storage.googleapis.com/{GS_BUCKET_NAME}/{CLUB_PREFIX}/media/
```

(`manage2soar/settings.py` — `GS_MEDIA_LOCATION = f"{CLUB_PREFIX}/media"`.)

That means when the new tenant renders `{{ qual.icon.url }}`, the browser
resolves it to `…/{GS_BUCKET_NAME}/{NEW_PREFIX}/media/quals/icons/...` —
**the new tenant's own media area**, not the source tenant's. If we only ran
`loaddata` and left the DB value as-is, the icons would **404** for the new
tenant (their `{NEW_PREFIX}/media/quals/icons/` area is empty), because the
objects only exist under the source prefix in the shared bucket.

So the import script **copies the icon objects** from the source tenant's
media area into the target tenant's media area, using the
`google.cloud.storage` Python client (already a transitive dependency of
`django-storages` in the pod image — no `gsutil`/`gcloud` CLI required).

The copy is **no-clobber by default**: if a destination object already exists
(e.g. the tenant already uploaded their own icon for that qualification), it is
skipped. Pass `--overwrite-icons` to force-copy over existing objects.

> This is a deliberate choice over the alternative of stripping the icon to
> `""` (which the knowledge-test seed does for `Question.media`). Qualification
> icons are **generic graphics**, not personal data, so there is no privacy
> concern in copying them — and a new tenant gets working icons out of the box
> rather than a broken-image flash.

## Repo layout

```
loaddata/club-qualifications-demo/
├── import_club_qualifications_demo.sh   # safe import script (preflight + icon copy + load + verify)
├── refresh_seed_from_tenant.sh          # refresh repo fixture from a source tenant (no sanitization needed)
└── instructors.ClubQualificationType.json  # 30 qualification types
```

---

## Step 0 — Prerequisites

- `kubectl` authenticated to the GKE cluster
  (`gcloud auth login` + `gcloud container clusters get-credentials
  manage2soar-cluster --region us-east1`).
- You know the **target** tenant's namespace (e.g. `tenant-masa`) and, if
  refreshing, the **source** tenant's namespace (default `tenant-ssc`).
- The target tenant's pod has the `GS_BUCKET_NAME` and `CLUB_PREFIX` env vars
  set (they are, by default, via the K8s secrets manifest).
- The pod's service account has `storage.objects.get` / `storage.objects.create`
  on the shared GCS bucket (it does — that's how the app itself serves media).

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

Only needed **if you are (re)capturing** the seed (e.g. `tenant-ssc` added or
removed qualifications, or you want to seed from a different source club). The
fixture already committed in `loaddata/club-qualifications-demo/` was captured
from `tenant-ssc`.

```bash
# From the default source (tenant-ssc):
bash loaddata/club-qualifications-demo/refresh_seed_from_tenant.sh

# Or from an explicit source namespace:
bash loaddata/club-qualifications-demo/refresh_seed_from_tenant.sh tenant-ssc
```

The script:

1. Dumps the model via `dumpdata` **inside the source tenant's app pod** (so
   DB credentials are correct), without `--natural-foreign` (the model has no
   FKs, but this keeps the fixture format consistent with the other seeds).
2. Copies the JSON out with `kubectl cp`.
3. Prints before/after object counts and a summary of how many rows carry
   icons (informational — the icon-copy step at import time will handle them).

> No sanitization is performed: the model has no Member/User FKs and the icon
> is a generic graphic (not PII). The `code` and `name` fields are generic
> labels that travel fine between tenants.

It does **not** commit. Review the diff, then commit via a feature branch + PR
(**never** push to `main` directly).

---

## Step 2 — Import into the target tenant

The import script is **safe-by-default**. It:

1. **Preflights**: counts `ClubQualificationType` rows in the **target** tenant.
2. **Aborts** (exit code 3) if the target already has any, unless you pass
   `--force`.
3. **Copies icons** from the source tenant's GCS media area into the target
   tenant's area (no-clobber by default; `--overwrite-icons` to force).
4. **Loads** the fixture with `loaddata`.
5. **Verifies** that every fixture primary key is now present in the target.

### Recommended: run inside the target tenant's app pod

```bash
NS=tenant-masa   # <-- target tenant
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed -E 's#^pods?/##')

# The deployed image does not always ship the repo's loaddata/ tree, so copy it in:
kubectl cp "loaddata/club-qualifications-demo" "$NS/$POD:/tmp/cseed" -c django

kubectl exec -n "$NS" -c django "$POD" -- \
  bash /tmp/cseed/import_club_qualifications_demo.sh
```

Expected output on a clean (empty) target:

```
==> Preflight: checking that the target tenant has no existing qualification catalog
    ClubQualificationType: 0

==> Copying qualification icons from the source tenant's GCS media area
    into the target tenant's GCS media area (no-clobber by default)
    Found 30 distinct icon path(s) in the fixture.
    icons: copied=30 skipped_existing=0

==> Loading qualification catalog fixtures
    loaddata instructors.ClubQualificationType.json
    ...

==> Verifying that every fixture primary key is now present in the target
    ClubQualificationType: fixture=30 present=  30  all_present=True

==> Post-load count: ClubQualificationType: 30
```

Expected output on a tenant that **already** has qualifications (script refuses):

```
==> Preflight: checking that the target tenant has no existing qualification catalog
    ClubQualificationType: 12

ABORT: This tenant already has a qualification catalog (12 rows).
This script is meant for an EMPTY catalog.

If you are absolutely sure you want to overwrite it, re-run with --force.
NOTE: --force upserts by primary key and does NOT delete extra rows.
```

> 🖊️ **Per-club review:** the seed is the *reference club's* catalog. After
> import, the receiving club **should review** the qualification types in the
> admin (`instructors → ClubQualificationType`) and adjust wording, scope
> (`applies_to`), and icons to their own standards before using them to track
> member qualifications.

---

## Rollback

**Destructive delete** — confirm the target tenant is the right one first.

```bash
NS=tenant-masa
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
  | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 | sed -E 's#^pods?/##')

kubectl exec -n "$NS" -c django "$POD" -- python manage.py shell -c '
from instructors.models import ClubQualificationType
n = ClubQualificationType.objects.delete()[0]
print(f"deleted {n} qualification types")
'
```

> ⚠️ **Icon objects are NOT rolled back.** If the import copied icons into the
> tenant's GCS media area, they remain after the DB rollback. That is
> generally fine (they are generic graphics and harmless to keep), but if you
> want a clean slate, delete them with:
>
> ```bash
> gcloud storage rm -r "gs://$GS_BUCKET_NAME/$CLUB_PREFIX/media/quals/icons/"
> ```
>
> (Or with the Python client, if `gcloud` CLI is unavailable.)

> If the target tenant had **its own** pre-existing catalog that you upserted
> over with `--force`, this rollback will also delete the club's original rows
> — there is no way to distinguish them afterward. Prefer testing `--force`
> against a scratch/demo tenant first.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `container django-app-ssc is not valid for pod ...` | Wrong `-c` container name | Use `-c django` (container is named `django`) |
| `ABORT: This tenant already has a qualification catalog` | Target is not empty | Intended protection. Use `--force` only if you truly want an upsert, or roll back first. |
| `django.core.exceptions.ImproperlyConfigured` | Ran `manage.py` without the tenant env | Run **inside** the tenant pod (env already set) — not locally with the wrong `DB_*`. |
| `IntegrityError` on `loaddata` | Out-of-order load / stale rows | Roll back and retry. (Single-model seed, so this is unlikely.) |
| `ERROR: fixture not found: ...` | Ran the script without the fixtures next to it | `kubectl cp` the whole `loaddata/club-qualifications-demo` dir first, then run the script from there. |
| `ERROR: GS_BUCKET_NAME is not set in the environment.` (exit 7) | Ran outside a pod / env not set | Run inside the tenant pod, or pass `--no-icons` to skip the icon copy. |
| `ERROR: icon copy did not complete successfully.` (exit 6) | GCS permission or network failure | Check the pod SA's GCS permissions on the shared bucket, retry. Or pass `--no-icons` to skip. |
| Icons 404 in the new tenant's UI after import | Icon copy was skipped or failed | Re-run with `--overwrite-icons`, or re-upload the icons via the admin. |

### `--force` semantics (important)

`loaddata` **upserts by primary key**. For a non-empty target:

- Fixture pks that already exist in the target are **replaced** with the fixture
  values.
- Target rows with pks **not** in the fixture are **left alone** (not deleted).
- The result is a **mixture** of the target's original rows and the seed's rows.

The post-load count is therefore **not** required to equal the fixture count;
the script instead verifies that **every fixture pk is present**, which holds in
both the empty and the collision cases.

### Icon-copy semantics

- **Default (no-clobber):** if the destination object
  (`gs://{GS_BUCKET_NAME}/{CLUB_PREFIX}/media/{icon}`) already exists, it is
  **skipped**. The icon in the DB is unchanged. Safe to re-run.
- **`--overwrite-icons`:** force-copies over existing destination objects. Use
  this if the source tenant's icons are newer / better and you want to replace
  the target's.
- **`--no-icons`:** skips the GCS copy phase entirely. The DB icon values are
  preserved (so re-running the copy later is still possible), but the new
  tenant's icons will 404 until they re-upload their own.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | A fixture file is missing |
| 2 | Unknown CLI argument |
| 3 | Target not empty and `--force` not given |
| 4 | Could not read pre-load counts |
| 5 | Post-load verification failed (missing pk) |
| 6 | GCS icon copy failed |
| 7 | GCS env missing (`GS_BUCKET_NAME` or `CLUB_PREFIX` not set) |

---

## Safety & policy reminders

- **Never** commit to `main`. Use `feature/...` + PR.
- **Never** `--force` against a tenant you are not sure about — it upserts by PK
  and **does not delete** extra rows, so you can end up with a mixture of the
  club's own and the seed's qualification types.
- This runbook only moves the **catalog** (`ClubQualificationType`). Member
  qualifications (`MemberQualification`) are **member-owned** and must not be
  copied between clubs.
- After any `--force` upsert on a tenant that had its own catalog, treat the
  result as needing a **human review** before it is used to track members.
