# Private stats exports (issue #1159)

Stats CSVs contain flight history, participant names and charges. Creation and
download require active membership, `stats_monger`, and requester ownership;
superusers retain their existing exception. Permission is checked again for
every download. Downloads stream through Django; there are no object URL links
or signed bearer URLs. Responses and GCS objects use private/no-store caching.

## Storage and retention

GCS deployments use `GS_IMPORT_EXPORT_BUCKET_NAME`, which must be set and must
differ from `GS_BUCKET_NAME`. The existing private import/export bucket is reused,
but stats objects live at `stats-dumps/<CLUB_PREFIX>/<random UUID>.csv`. The
one-day `django-import-export/` lifecycle rule does not apply to them. The updated
Ansible lifecycle file expires stats objects after seven days, including orphaned
objects. GCS lifecycle deletion is asynchronous. Django denies downloads after
seven days regardless of when the storage deletion happens.

Each tenant has its own database and settings environment. `CLUB_PREFIX` must be
unique and identical in that tenant's web and worker environments. Storage checks
the prefix on every read, write and delete, including for superusers. Do not copy
another tenant's prefix when provisioning. Namespace checks isolate application
requests; they do not isolate a compromised service account that has bucket-wide
access. Use separate buckets/service identities if that additional boundary is
required.

Local production uses `STATS_DUMP_ROOT` (Ansible default:
`{{ m2s_app_home }}/stats-dumps`). Web and worker processes must share that
directory. It must be outside the checkout, `MEDIA_ROOT`, `STATIC_ROOT`, and every
web-server alias. Directories use mode 0700 and files 0600. Development may omit
the setting and use an OS temporary directory outside the checkout. Production
fails closed if the root is missing. A root overlapping a served directory or the
checkout is rejected, including resolved symlinks. Do not add a web route to it.

The existing `process_stats_dump_outbox` scheduled job deletes expired private
files and clears their DB references even when there are no pending jobs. Keep
that schedule enabled. Local storage does not have GCS's orphan lifecycle safety
net: inspect the private directory for unreferenced files older than seven days
after failed workers or DB restores, and remove those as an operator. Do not use
the one-day import staging cleanup for stats files.

## Rollout: repeat for every tenant, including suspended/retired tenants

This change deliberately **retires** old public exports rather than moving them.
Members can generate a fresh private export. The schema migration only changes
storage metadata/status choices; it does not access storage or delete files.

1. Disable export generation and suspend/drain all old export workers/CronJobs.
   Use a maintenance window if the queue route cannot be disabled separately.
   Wait for existing jobs to finish; the retirement command refuses to apply
   while a job is `processing`. Inspect stale jobs before clearing their status.
   Do not allow old and new workers to run simultaneously.
2. Inventory current public objects promptly, including orphans and tenant
   prefixes with no running application. Record public bucket IAM/listing access
   and object versioning/soft-delete settings. Restrict or remove the export
   objects as soon as practicable; do not wait for a filename-only change.
   Leave intentionally public photos, CMS media and static assets public.
3. Run `infrastructure/ansible/playbooks/gcp-storage.yml` with the correct
   inventory (full playbook, not just `--tags bucket`). It provisions uniform
   bucket-level access, enforces Public access prevention, grants the configured
   application service account `roles/storage.objectAdmin` on the private
   bucket, and applies the authoritative two-prefix lifecycle policy. Review
   existing lifecycle policies before applying this managed policy.
   Review bucket **and inherited project IAM**: remove unnecessary public or
   other broad principals; limit access to application/export-worker identities
   and required operators. If workers use a different identity, explicitly grant
   that identity the same private-bucket object permissions. Do not grant
   `allUsers` or `allAuthenticatedUsers`. Confirm the GKE secret supplies
   `GS_IMPORT_EXPORT_BUCKET_NAME` to both web and CronJob pods. For single-host
   deployments, run the application role to provision the private directory and
   `STATS_DUMP_ROOT` before starting new processes.
4. Deploy this application version to web and workers, run `manage.py migrate`
   against **each tenant database**, and keep workers suspended. Using each
   tenant's normal environment/settings and current legacy media configuration,
   run:

   ```bash
   python manage.py retire_public_stats_dumps
   python manage.py retire_public_stats_dumps --apply
   python manage.py retire_public_stats_dumps
   ```

   The first command prints a JSON inventory without mutation. It includes DB
   references and orphan objects under `exports/stats_dumps/` in that tenant's
   default media backend. Save that inventory securely. `--apply` deletes the
   public files, checks they are gone, clears DB references, and marks jobs
   expired/retired. Repeating it is safe. A failed deletion leaves its DB reference
   intact for retry. The final inventory must contain no legacy objects/references.
   If a tenant has changed buckets/media prefixes, also inventory and retire its
   historical locations; this command only knows the current default backend.
5. Review **all generations** of old GCS objects, not just live objects. Remove
   publicly accessible historical versions and prevent restoring public access
   from soft-deleted objects/backups. Retention holds can prevent deletion: resolve
   them or make those exact exports inaccessible before declaring rollout done.
   The command cannot prove this from a live-object listing.
6. Verify private access using the checks below, then resume new workers and
   export generation. Run a fresh export and confirm it downloads through Django.
   Record per-tenant deployment, retirement, and verification results. This work
   is not completed merely by merging the application PR.

## Verify actual deployment privacy

Use an actual generated object name, not a nonexistent probe (a 404 proves
nothing about permissions). Run anonymous requests from a clean client with no
Authorization header or cookies. Substitute the actual names in these examples:

```bash
# Known object: must deny anonymous reads (normally HTTP 403).
curl -i 'https://storage.googleapis.com/PRIVATE_BUCKET/stats-dumps/TENANT/KNOWN_UUID.csv'
# JSON API anonymous listing: must deny access (normally HTTP 401 or 403).
curl -i 'https://storage.googleapis.com/storage/v1/b/PRIVATE_BUCKET/o?prefix=stats-dumps%2FTENANT%2F'
# Also check the XML API listing endpoint.
curl -i 'https://storage.googleapis.com/PRIVATE_BUCKET?prefix=stats-dumps/TENANT/'
```

Verify Public access prevention is **enforced** and uniform bucket-level access
is **enabled** with `gcloud storage buckets describe gs://PRIVATE_BUCKET`.
Inspect IAM and the object's Cache-Control metadata with operator credentials.
Test the authorized owner, anonymous client, another stats monger, inactive
member, and a member whose `stats_monger` permission was just revoked. Check the
download response includes `private` and `no-store`. Repeat with two tenants whose
job IDs overlap. Test public assets still load. Local deployments must deny
`/media/exports/stats_dumps/...` (including DEBUG media routes) and must not expose
the private directory. The service worker bypasses stats export routes.

Check the previously recorded **exact public URLs**, including historical object
generation URLs, anonymously after retirement. Account for public cache copies:
the old backend set `public, max-age=3600`. Purge any CDN caches you control and
allow previous cache lifetimes to expire; test without a local browser cache and
from an independent client. Removing an origin object does not retract already
cached/downloaded copies, and no deployment can revoke data already downloaded.

Django unit tests and mocked GCS options do **not** establish real bucket privacy.
These checks require production/operator access and must be recorded at rollout.

## Rollback

Pause export generation/workers first. Keep private bucket protections, private
files, and legacy media blocking in place. Keep public exports deleted. Do not
restore old public files or change private references back to default media.
If rolling back application code, disable the stats queue/status/download routes
and worker schedules until the private-storage fix is restored; old code writes
to public media. Preserve the retirement inventory and inspect DB restores for
resurrected legacy references. Regenerate exports privately after recovery.
