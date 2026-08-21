# Badge Import Runbook

This runbook explains how to copy the **club's badge catalog** (the list of
badges a club recognizes — SSA A/B/C, Bronze, and the FAI Silver/Gold/Diamond
badges with their duration/altitude/distance/goal "legs") out of one tenant
(the reference `tenant-ssc` cluster, which holds the "good-enough" set) and
import it into **another** tenant, including the badge images that go with
each one.

It follows the **IaC-first** philosophy: the seed fixture and the
import/refresh scripts live **in the repo** so the operation is
reproducible, reviewable, and does not depend on copying files around by
hand.

> This mirrors the [Club Qualifications Import](club-qualifications-import.md),
> [Knowledge Test Bank Import](knowledge-test-import.md), and
> [Training Syllabus Import](syllabus-import.md) runbooks. The seeds are
> independent and do not interfere with each other.

## 🎯 Quick Reference

| Operation | Command |
|-----------|---------|
| **Refresh the repo seed from a source tenant** | `bash loaddata/badges-demo/refresh_seed_from_tenant.sh` |
| Refresh from a specific source tenant | `bash loaddata/badges-demo/refresh_seed_from_tenant.sh tenant-ssc` |
| **Import into an empty tenant (safe, recommended)** | `bash loaddata/badges-demo/import_badges_demo.sh` |
| Force-load (upsert, **no delete**) | `bash loaddata/badges-demo/import_badges_demo.sh --force` |
| Skip the image copy (re-upload images later) | `bash loaddata/badges-demo/import_badges_demo.sh --no-images` |
| Force-copy images over existing objects | `bash loaddata/badges-demo/import_badges_demo.sh --overwrite-images` |
| Copy images from a non-default source prefix | `bash loaddata/badges-demo/import_badges_demo.sh --source-prefix masa` |

## What "badges" is

The club's badge catalog is modeled by a single model in the `members` app.
It is **club-owned content** and safe to move between tenants.

| Model | Purpose | Row count in this seed |
|-------|---------|------------------------|
| `members.Badge` | Badges the club recognizes (name, image, description, order, optional `parent_badge` for FAI legs) | 15 (7 with images, 8 legs) |

The `parent_badge` field is what makes the FAI badge board work: a badge with
a parent is a "leg" (e.g. *Silver Duration* is a leg of *FAI Silver Badge*).
The refresh script verifies that every leg's parent pk is present in the same
fixture, and the import script re-verifies that after load.

> ⚠️ **Excluded (member-specific):** `members.MemberBadge`.
> This model records *which member earned which badge*, plus the award date
> and notes. It references `Member` rows that only exist in the source
> tenant. Do **not** include it when moving the catalog between clubs — the
> new tenant's members earn their badges through normal club processes.

## Why we copy images (not strip them)

The `image` field is an `ImageField` with a **prefix-free relative path**
(e.g. `badge_images/A-Soaring-Badge-Achievement.png`). In production,
`MEDIA_URL` is constructed from the **rendering tenant's** `CLUB_PREFIX`:

```
https://storage.googleapis.com/{GS_BUCKET_NAME}/{CLUB_PREFIX}/media/
```

(`manage2soar/settings.py` — `GS_MEDIA_LOCATION = f"{CLUB_PREFIX}/media"`.)

That means when the new tenant renders `{{ badge.image.url }}`, the browser
resolves it to `…/{GS_BUCKET_NAME}/{NEW_PREFIX}/media/badge_images/...` —
**the new tenant's own media area**, not the source tenant's. If we only ran
`loaddata` and left the DB value as-is, the badge images would **404** for
the new tenant (their `{NEW_PREFIX}/media/badge_images/` area is empty),
because the objects only exist under the source prefix in the shared bucket.

So the import script **copies the image objects** from the source tenant's
media area into the target tenant's media area, using the
`google.cloud.storage` Python client (already a transitive dependency of
`django-storages` in the pod image — no `gsutil`/`gcloud` CLI required).

The copy is **no-clobber by default**: if a destination object already exists
(e.g. the tenant already uploaded their own badge image), it is skipped. Pass
`--overwrite-images` to force-copy over existing objects.

> This is a deliberate choice over the alternative of stripping the image to
> `""` (which the knowledge-test seed does for `Question.media`). Badge
> images are **generic graphics**, not personal data, so there is no privacy
> concern in copying them — and a new tenant gets working badge art out of
> the box rather than a broken-image flash.

## Repo layout

```
loaddata/badges-demo/
├── refresh_seed_from_tenant.sh        # dump members.Badge from a source tenant
├── members.Badge.json                 # the seed fixture (15 rows, 7 images, 8 legs)
└── import_badges_demo.sh              # safe import script (preflight + image copy + load + verify)
docs/runbooks/badges-import.md         # this file
```

> **Note:** the repo also contains an older, stale `loaddata/members.Badge.json`
> (used by the legacy `loaddata/loaddata.sh` onboarding script). That fixture
> is missing the FAI leg structure (`parent_badge` is null for all rows).
> `loaddata/badges-demo/members.Badge.json` is the current, production-quality
> seed and is the one this runbook covers.

## Step 0 — Prerequisites

- `kubectl` authenticated to the cluster (and `gcloud auth login` fresh enough
  that the GKE auth plugin can mint tokens).
- The **source** tenant (default `tenant-ssc`) has the badge catalog you want
  to copy.
- The **target** tenant pod has the GCS env vars set (`GS_BUCKET_NAME`,
  `CLUB_PREFIX`) so the image-copy phase can run.

## Step 1 — Refresh the repo seed (only when the source tenant's catalog changes)

From the repo checkout:

```bash
bash loaddata/badges-demo/refresh_seed_from_tenant.sh            # defaults to tenant-ssc
bash loaddata/badges-demo/refresh_seed_from_tenant.sh tenant-masa # or another source
```

Expected output (abridged):

```
==> Source namespace: tenant-ssc
==> Source pod: django-app-ssc-...
==> Dumping from source tenant (plain FK pks, no --natural-foreign)
    dumpdata members.Badge
==> No sanitization needed (see header). Summary of image-bearing + leg rows:
    members.Badge.json: 15 objects (7 with images, 8 legs)
==> Row counts AFTER refresh (repo)
    Badge: 15
```

If the script prints `!! N leg parent pk(s) not in fixture`, stop and
investigate — the dump is malformed and importing it would produce dangling
legs.

Then review the diff and commit the refreshed fixture via the normal
feature-branch + PR flow (NEVER commit to main).

## Step 2 — Import into an empty target tenant

The deployed image may not ship this repo's `loaddata/` tree, so copy the
seed into the target pod first, then run it from the copied location:

```bash
NS=tenant-<newclub>
POD=$(kubectl get pods -n "$NS" -o name | grep -E 'django-app' \
      | grep -vE 'clearsessions|expire|notify|process|send|cron' | head -1 \
      | sed -E 's#^pods?/##')

kubectl cp "loaddata/badges-demo" "$NS/$POD:/tmp/bseed" -c django
kubectl exec -n "$NS" -c django "$POD" -- bash /tmp/bseed/import_badges_demo.sh
```

> **Keep `/tmp/bseed` for now.** The [Rollback](#rollback) section reads the
> fixture from `/tmp/bseed/members.Badge.json`. Once you are confident the
> import is correct and you won't need to roll back, remove it with
> `kubectl exec -n "$NS" -c django "$POD" -- rm -rf /tmp/bseed`.

Expected output (abridged):

```
==> Preflight: checking that the target tenant has no existing badge catalog
    Badge: 0

==> Copying badge images from the source tenant's GCS media area
    into the target tenant's GCS media area (no-clobber by default)
    Found 7 distinct image path(s) in the fixture.
    images: copied=7 skipped_existing=0

==> Loading badge catalog fixtures
    loaddata members.Badge.json
Installed 15 object(s) from 1 fixture(s)

==> Verifying that every fixture primary key is now present in the target
    Badge: fixture=15 present=  15  all_present=True  leg_integrity=True

==> Post-load count: Badge: 15
```

### Options

| Flag | Effect |
|------|--------|
| `--force` | Allow import into a tenant that already has badges (upsert by pk, **no delete**). |
| `--no-images` | Skip the GCS image-copy phase. DB image paths are preserved; the tenant re-uploads images to render them. |
| `--overwrite-images` | Force-copy images over existing objects in the target area (default is no-clobber). |
| `--source-prefix PFX` | Source tenant prefix to copy images from (default `ssc`). Independent of the target's `CLUB_PREFIX`. |

## Rollback

`loaddata` upserts by `(model, pk)` and does **not** delete rows it did not
see, so "rollback" is a matter of deleting the rows the import created. The
rollback reads the fixture from `/tmp/bseed` — if you already removed it
(see Step 2), copy the seed back into the pod first.

```bash
NS=tenant-<newclub>
POD=<app-pod>

# 1) Make sure the seed fixture is present in the pod (no-op if already there).
kubectl cp "loaddata/badges-demo" "$NS/$POD:/tmp/bseed" -c django

# 2) Delete the badge rows (and any member->badge links) the import created.
kubectl exec -n "$NS" -c django "$POD" -- python manage.py shell -c '
from members.models import Badge, MemberBadge
import json
pks = [o["pk"] for o in json.load(open("/tmp/bseed/members.Badge.json"))]
print("deleting", MemberBadge.objects.filter(badge_id__in=pks).delete())
print("deleting", Badge.objects.filter(pk__in=pks).delete())
'

# 3) Now safe to clean up the copied seed.
kubectl exec -n "$NS" -c django "$POD" -- rm -rf /tmp/bseed
```

If you also copied badge images, delete the objects in GCS:

```
gsutil rm gs://<GS_BUCKET_NAME>/<NEW_PREFIX>/media/badge_images/*
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ABORT: This tenant already has a badge catalog (N rows)` | Target already has badges | Confirm intent, re-run with `--force`. |
| `ERROR: GCS environment is missing (GS_BUCKET_NAME / CLUB_PREFIX)` | Running outside a tenant pod (or env mis-set) | Run inside the pod, or pass `--no-images`. |
| `ERROR: image copy did not complete successfully` | Source objects missing (wrong `--source-prefix`?) | Check `gsutil ls gs://manage2soar/<src>/media/badge_images/` and retry with the right prefix. |
| `ERROR: at least one fixture primary key is missing from the target` | `loaddata` failed or was interrupted | Re-run with `--force`; the upsert will repair. |
| `ERROR: a badge leg points at a parent badge that is missing` | Fixture is corrupt or target DB was tampered with | Re-run the refresh script from the source tenant; re-import with `--force`. |
| `ERROR: fixture not found: ...` | Ran the script without the fixtures next to it | `kubectl cp` the whole `loaddata/badges-demo` dir first, then run the script from there. |
| Badges show but images are broken | Image copy was skipped (`--no-images`) or source objects were gone | Re-run with `--overwrite-images`, or upload the images in the admin. |

## Safety reminders

- **NEVER commit to main.** Always feature-branch + PR.
- **`--force` does not delete** existing badge rows; it upserts by pk.
- **Image copy is no-clobber by default.** A re-run will never destroy a
  tenant's customized badge art.
- The seed excludes `members.MemberBadge` on purpose — new tenants earn
  badges through normal club processes.
