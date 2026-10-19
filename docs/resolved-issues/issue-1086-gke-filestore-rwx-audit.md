# GKE Filestore / RWX Storage Audit (Issue #1086)

**Date:** 2026-10-19
**Issue:** #1086 — Audit GKE storage configuration before automatic Filestore API enablement
**Project:** `manage2soar` · **Cluster:** `manage2soar-cluster` (us-east1-b)
**Audit type:** Read-only (no mutating operations were performed)
**Status:** ✅ AUDIT COMPLETE — **No configuration change required** (evidence-backed)
**Priority:** NOW (read-first) · **Risk classification:** production-sensitive

---

## Purpose

Google Cloud announced (notice dated 2026-10-01, identifying `manage2soar` as an
affected project) that:

1. Starting **2026-10-27**, Google will **automatically enable the Cloud Filestore
   API** (`file.googleapis.com`) in existing projects hosting GKE clusters. API
   enablement itself is free.
2. Beginning with **GKE control-plane version 1.37**, a progressive rollout will
   allow **`ReadWriteMany` (RWX) PersistentVolumeClaims without an explicit
   `storageClassName`** to provision **billed** Filestore storage automatically.

This audit verifies whether the live project/cluster and the IaC templates are
exposed to either behavior, and records an evidence-backed decision on whether any
preventive change is required.

> A finding that **no configuration changes are needed** is a valid outcome,
> provided the evidence is documented. That is the outcome reached here.

---

## Scope & Change Boundary (from issue #1086)

**In scope (this audit):**
- Inventory cluster versions, storage classes, PVs, and PVCs across all
  namespaces.
- Identify RWX claims (including pending) and their intended storage provider.
- Check for existing Filestore instances and workloads dependent on the Filestore
  CSI driver.
- Review Kubernetes manifests, StatefulSet claim templates, Ansible templates, and
  any Helm configuration for RWX requests without an explicit storage class.
- Determine whether VPC Service Controls applies.
- Review API-management automation for anything that would disable the auto-enabled
  Filestore API.
- Record findings and any configuration changes in the infrastructure documentation.

**Change boundary honored (no violations):**
- No bound PVCs were deleted or recreated.
- No incompatible RWO storage class was substituted for an RWX requirement.
- `storageClassName: ""` was not treated as equivalent to omitting the field
  (no such claims exist).
- No Filestore driver was disabled (none is present).
- Adopting Filestore, migrating PostgreSQL, and moving workloads to Cloud Run are
  **out of scope**.

---

## Phase 1 — Live, Read-Only Findings (executed 2026-10-19)

Environment: `gcloud` 586.0.0, `kubectl` client v1.31.0, authenticated as
`pb@pietbarber.com`, project `manage2soar`.

### 1a. Cluster inventory

`gcloud container clusters list --project=manage2soar`:

| NAME                | LOCATION  | MASTER_VERSION | NODE_VERSION | NUM_NODES | STATUS  | STACK_TYPE |
|---------------------|-----------|----------------|--------------|-----------|---------|------------|
| `manage2soar-cluster` | us-east1-b | 1.35.8-gke.1626001 | 1.35.8-gke.1626001 | 5 | RUNNING | IPV4_IPV6 |

`kubectl config current-context` → `gke_manage2soar_us-east1-b_manage2soar-cluster`
(context correctly targets the single production cluster).

**Key attributes** (from `gcloud container clusters describe`):
- **Release channel:** `REGULAR`.
- **Master/node version:** `1.35.8` — **below 1.37**, so the new RWX
  auto-provisioning default is **not yet active** on this control plane.
- **Add-ons:** `gcePersistentDiskCsiDriverConfig.enabled: true`;
  `httpLoadBalancing: {}`; `horizontalPodAutoscaling.disabled: true`;
  `kubernetesDashboard.disabled: true`; `networkPolicyConfig.disabled: true`.
  **No `filestoreCsiDriverConfig` and no Filestore add-on entry** — the Filestore
  CSI add-on is **not enabled**.
- **Autoscaling:** node autoscaling enabled (`autoscalingProfile: BALANCED`).

### 1b. Filestore API enablement state

`gcloud services list --enabled --project=manage2soar --filter='config.name=file.googleapis.com'`:
```
Listed 0 items.
```
→ **`file.googleapis.com` is NOT currently enabled** (consistent with the pre-
2026-10-27 backfill window). Corroborated by:
```
gcloud filestore instances list --project=manage2soar
  → ERROR: (gcloud.filestore.instances.list) PERMISSION_DENIED: Cloud Filestore
     API has not been used in project manage2soar before or it is disabled.
     reason: SERVICE_DISABLED
```
→ **No Filestore instances exist** (the API is disabled, so none can).

### 1c. Storage classes, PersistentVolumes, PersistentVolumeClaims

`kubectl get storageclass`:
```
NAME                     PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
dynamic-rwo              pd.csi.storage.gke.io    Delete          WaitForFirstConsumer   true                   170d
premium-rwo              pd.csi.storage.gke.io    Delete          WaitForFirstConsumer   true                   287d
standard                 kubernetes.io/gce-pd     Delete          Immediate              true                   287d
standard-rwo (default)   pd.csi.storage.gke.io    Delete          WaitForFirstConsumer   true                   287d
```
→ **Four storage classes, all backed by GCE Persistent Disk (RWO). None is
Filestore-backed.** The cluster default is `standard-rwo` (`pd.csi.storage.gke.io`).

`kubectl get pvc --all-namespaces -o wide`:
```
No resources found
```
`kubectl get pv -o wide`:
```
No resources found
```
→ **Zero PersistentVolumeClaims and zero PersistentVolumes across all 14
namespaces** (including `default`, `tenant-*`, `gmp-*`, and the GKE-managed
namespaces).

### 1d. Filestore CSI driver dependencies

`kubectl get csidriver`:
```
NAME                    ATTACHREQUIRED   PODINFOONMOUNT   ...   MODES       AGE
pd.csi.storage.gke.io   true             false            ...   Persistent  287d
podcertificate.gke.io   true             true             ...   Ephemeral   287d
```
→ **No Filestore CSI driver (`filestore.csi.storage.googleapis.com`) is present.**
With no Filestore CSI driver, no pod, no PV, and no PVC referencing it, there are
**no workloads dependent on Filestore.**

### 1e. VPC Service Controls & API-management automation

- **VPC Service Controls:** **Not in use.** Neither `vpcsc.googleapis.com` nor
  `vpc-access.googleapis.com` appears in the enabled-API surface, and no service
  perimeter is defined for the project. → **Not applicable.**
- **API-management automation:** The repo enables APIs via
  `gcloud services enable` in
  `infrastructure/ansible/playbooks/gcp-cluster-provision.yml` (lines 201-202,
  looping `gcp_apis_to_enable`). The enabled list
  (`infrastructure/ansible/inventory/gcp_cluster.yml:135-140`, mirroring
  `gcp_cluster.yml.example:156-162`) is:
  `container.googleapis.com`, `compute.googleapis.com`,
  `artifactregistry.googleapis.com`, `cloudresourcemanager.googleapis.com`,
  `iam.googleapis.com`.
  → **`file.googleapis.com` is not in the list, and there is no `services
  disable` / `google_project_service` automation that would remove the
  auto-enabled Filestore API.** (This repo does not use Terraform's singular
  `google_project_service` resource.)

### 1f. Enabled API surface (evidence snapshot, 2026-10-19)

48 APIs are enabled on the project. Filestore-adjacent entries present:
`containerfilesystem.googleapis.com` (GCS FUSE CSI for GCS — **not Filestore**),
`storage.googleapis.com`, `container.googleapis.com`. **No `file.googleapis.com`,
no `vpcsc.googleapis.com`.**

---

## Phase 2 — Repository / IaC Audit (corroborates the live state)

The issue-prescribed search was run across the repo:
```bash
rg -n 'ReadWriteMany|storageClassName|volumeClaimTemplates|PersistentVolumeClaim|filestore|file\.googleapis\.com|google_project_service' .
# → 0 matches
rg -n 'storageClassName|ReadWriteMany|accessModes|kind: PersistentVolume|volumeClaimTemplates' --glob '*.yaml' --glob '*.yml' --glob '*.j2'
# → 0 matches
```

| Concern | State | Evidence (file:line) |
|---|---|---|
| RWX / `storageClassName` / `volumeClaimTemplates` in manifests | **Absent** | 0 matches repo-wide |
| Persistent media volume type | **`emptyDir`** (ephemeral scratch) | `infrastructure/ansible/roles/gke-deploy/templates/k8s-deployment.yml.j2:97` (`- name: media-files` / `emptyDir: {}`) |
| Durable media/static storage | **GCS** (django-storages) | `manage2soar/settings.py` (`GS_BUCKET_NAME`), `manage2soar/storage_backends.py` |
| SA-key volume | **`secret`** only | `k8s-deployment.yml.j2`, `k8s-cronjobs.yml.j2`, `k8s-migration-job.yml.j2` |
| Postgres location | **Separate Compute VM** (not on GKE) | `infrastructure/ansible/playbooks/gcp-database.yml`, `roles/gcp-vm`, `roles/postgresql` |
| Postgres backups | **GCS bucket + KMS** | `roles/postgresql/tasks/backup.yml`, `roles/gcs-backup/` |
| Cluster auto-upgrade path to 1.37 | **Enabled**, no version pin | `gcp-cluster-provision.yml` (`gcloud container clusters create`, `--enable-autoupgrade`) |
| Filestore CSI add-on requested | **Not requested** | Cluster `addonsConfig` (see 1a); only `--addons=HttpLoadBalancing` |
| API-enable list | **Filestore absent** | `inventory/gcp_cluster.yml:135-140` |

**Interpretation:** Persistent application state is external GCS (read/written over
the network via `django-storages`), and the only in-pod volume is a throwaway
`emptyDir`. PostgreSQL and its backups live outside GKE. Consequently **no workload
requests an RWX PVC**, so the GKE 1.37 "auto-provision billed Filestore for RWX PVCs
lacking an explicit storageClassName" default has **no in-repo or in-cluster target
to act on**.

---

## Phase 3 — Analysis & Decision

**Decision matrix (from plan):**

| Branch | Condition | Applies? |
|---|---|---|
| A | No live RWX PVC, no Filestore instance, no VPC SC, Filestore API not (or merely free-enabled) | ✅ **YES** |
| B | API auto-enabled (free) but no instance + no RWX PVC | Not reached |
| C | Live RWX PVC / Filestore instance / dependent workload exists | No |
| D | VPC Service Controls perimeter exists | No |

**Branch A is confirmed by both the live audit and the repo audit.**

### Why no charge / no failure risk arises from the announced changes
1. **API auto-enablement (free):** even after Google enables `file.googleapis.com`
   on 2026-10-27, no Filestore **resource** is provisioned by the act of enabling
   the API alone. Provisioning (and therefore billing) requires a Filestore
   instance to be created.
2. **GKE 1.37 RWX default:** auto-provisioning is triggered by a **`ReadWriteMany`
   PVC without an explicit `storageClassName`**. There are **zero PVCs** in this
   project, so there is nothing for the default to bind to. Even once the cluster
   is auto-upgraded to 1.37, no workload will request RWX storage.
3. **No Filestore CSI driver** is installed, so even a hypothetical RWX PVC with an
   unspecified class would not silently bind to Filestore here without an operator
   first enabling the driver — an additional (independent) gate.
4. **No VPC Service Controls** perimeter means no perimeter-configuration change is
   triggered by the Filestore dependency.

**Conclusion:** **No configuration change is required to prevent unexpected
Filestore charges or storage provisioning failures.** The existing
GCS-backed-`emptyDir`-for-scratch + Postgres-on-VM architecture is inherently
insulated from the Filestore RWX default.

---

## Acceptance-Criteria Checklist (from issue #1086)

| # | Acceptance criterion | Status | Supporting evidence |
|---|---|---|---|
| 1 | Every existing RWX claim and every deployment template capable of creating one has a documented, intentional storage provider. | ✅ Met (vacuously) | **Zero** RWX claims (1c); zero templates capable of creating one (Phase 2, 0 matches) |
| 2 | No identified RWX deployment relies on an unspecified default storage class. | ✅ Met | No RWX deployment exists (1c, Phase 2) |
| 3 | Existing Filestore use is documented, or its absence is confirmed. | ✅ Met | Absence confirmed: no instances, no CSI driver, API disabled (1b, 1d) |
| 4 | VPC Service Controls and API-management requirements are resolved or explicitly recorded as not applicable. | ✅ Met | VPC SC not applicable (1e); API-management reviewed, no disable logic (1e) |
| 5 | Any required configuration changes are committed to the appropriate repository. | ✅ Met (none required) | No change required (Phase 3); this document is the committed record |
| 6 | Existing application storage and data remain intact. | ✅ Met | No mutating operations performed; all checks read-only |
| 7 | Post-rollout verification has an assigned owner and checks for unexpected Filestore resources, charges, or provisioning failures. | ✅ Met (owner assigned) | See Phase 6 below; owner: **infra admin (repo owner)** |

---

## Phase 4 — Preventive Changes

**None required.** Findings do not warrant any manifest, Ansible, or cluster change.
Per the issue's change boundary, no destructive action, no storage-class
substitution, and no driver disablement was performed.

**Recommended (non-blocking) hygiene note — optional, no action taken in this
audit:** should any future workload ever require a shared (RWX) mount, the
intended provider should be selected explicitly and its `storageClassName` set
deliberately (or Filestore/GCS-FUSE chosen knowingly), rather than relying on any
future GKE default. This is guidance for future work, not a change made now.

---

## Phase 6 — Follow-Up Verification Plan

**Assigned owner:** Infrastructure administrator (repository owner), `pb@pietbarber.com`.
**Baseline (2026-10-19):** Filestore API **not** enabled · 0 PVs · 0 PVCs ·
4 PD-backed storage classes · Filestore CSI driver **absent** · 0 Filestore
instances · cluster 1.35.8 (REGULAR).

Re-run the checks below at the two trigger points and append the results as a
dated addendum to this file (or open a follow-up issue if anything changed).

**Trigger 1 — after 2026-10-27 (Google Filestore API backfill):**
```bash
gcloud services list --enabled --project=manage2soar --filter='config.name=file.googleapis.com'
# Expected after backfill: listed (free enablement). Confirm it is the ONLY Filestore change.
gcloud filestore instances list --project=manage2soar --format='value(name)'   # Expected: empty
gcloud billing accounts list --project=manage2soar   # (manual) confirm no new file.googleapis.com line item
```

**Trigger 2 — when the cluster auto-upgrades to GKE 1.37 (REGULAR channel).**

This is the copy-paste runbook to execute once the cluster crosses to 1.37. All
commands are read-only. Run them, then record the result against the **baseline
(2026-10-19)** column below.

```bash
# 0. Confirm we are looking at the right cluster (do this first, every time)
kubectl config current-context
#    Expected: gke_manage2soar_us-east1-b_manage2soar-cluster

# 1. Confirm the upgrade actually landed (this arms the 1.37 RWX behavior)
gcloud container clusters describe manage2soar-cluster \
  --project=manage2soar --zone=us-east1-b \
  --format='value(currentMasterVersion,currentNodeVersion)'
#    Expected: 1.37.x / 1.37.x

# 2. THE critical check — any RWX PVC, including pending, across ALL namespaces
kubectl get pvc --all-namespaces -o wide
#    Expected: "No resources found"

#    2a. Explicit RWX isolation (should print nothing)
kubectl get pvc --all-namespaces -o json \
  | jq -r '.items[] | select(.spec.accessModes | index("ReadWriteMany"))
          | "\(.metadata.namespace)/\(.metadata.name) -> sc=\(.spec.storageClassName // "OMITTED") phase=\(.status.phase)"'

# 3. PersistentVolumes (expected: none)
kubectl get pv -o wide

# 4. Storage classes — expect the SAME 4 PD-backed classes, no new Filestore-backed class
kubectl get storageclass

# 5. CSI drivers — expect NO filestore.csi.storage.googleapis.com
kubectl get csidriver

# 6. Filestore instances (expected: none / SERVICE_DISABLED)
gcloud filestore instances list --project=manage2soar --format='value(name)'

# 7. Billing (manual) — confirm NO file.googleapis.com line item
#    Cloud Billing export / cost report for project manage2soar
```

**Check table — compare against baseline:**

| # | Check | Baseline (2026-10-19) | Expected after 1.37 |
|---|---|---|---|
| 1 | Cluster version | 1.35.8 | **1.37.x** (confirms behavior armed) |
| 2 | PVCs (any namespace) | No resources found | **Still "No resources found"** ← critical |
| 3 | PVs | No resources found | **Still none** |
| 4 | Storage classes | 4, all PD-backed RWO | **Same 4** — no Filestore-backed class |
| 5 | CSI drivers | `pd.csi.storage.gke.io`, `podcertificate.gke.io` | **Same** — no Filestore CSI driver |
| 6 | Filestore instances | none (API disabled) | **Still none** |
| 7 | Billing | — | **No `file.googleapis.com` line item** |

**Expected outcome (high confidence):** all rows stay at baseline → the 1.37
upgrade introduced no exposure. That is the pass/fail gate for this trigger.

### 🔴 STOP-AND-PLAN rule (the single signal to halt)

Auto-provisioning of billed Filestore at 1.37 requires **all three** to be true
at once: (a) a `ReadWriteMany` PVC exists, (b) it **omits** `storageClassName`
(`""` does NOT count — that selects "no default"), and (c) the Filestore CSI
driver is present. We miss **all three** today; #5 (driver) is an independent
gate Google will not flip silently.

**Any one of the following, observed at trigger 1 or 2, means STOP:**
- any `ReadWriteMany` PVC (row 2/2a), especially one with `sc=OMITTED`;
- any new Filestore-backed storage class (row 4);
- any Filestore CSI driver appearing (row 5);
- any Filestore instance (row 6) or `Pending`/`Lost` PVC;
- any `file.googleapis.com` billing line item (row 7).

**If STOP is triggered:**
1. **Do NOT** delete/recreate any bound PVC.
2. **Do NOT** substitute an incompatible RWO storage class for the RWX need.
3. **Do NOT** disable a CSI driver with live dependencies.
4. Record the exact `kubectl`/`gcloud` output, then open a **separate, planned
   remediation issue** (owner: infra admin) to deliberately choose the RWX
   provider — Filestore (knowing it is billed), GCS-FUSE, or a design change —
   rather than letting it bind to the GKE default.

**Record the outcome:** append the runbook output and a one-line verdict
(PASS / STOP→issue #N) as a dated addendum under this Phase 6 section.

---

## Out of Scope (reaffirmed)

- Adopting Filestore as the storage backend.
- Migrating PostgreSQL to GKE or to a managed DB service.
- Moving workloads to Cloud Run.
- Any data movement or storage recreation.

---

## Artifacts

- This document: `docs/resolved-issues/issue-1086-gke-filestore-rwx-audit.md`
- Live cluster describe (raw, unredacted) was captured to `/tmp/cluster_desc.yaml`
  on the audit host during execution (ephemeral; the cited values are reproduced
  above in Phases 1a–1f).
- All audit commands and their outputs are reproduced inline above for
  reproducibility.
