# Ansible Infrastructure Changelog

## [Unreleased] - 2026-01-02

### Fixed

#### GKE Cluster Provisioning (`playbooks/gcp-cluster-provision.yml`)
- **BREAKING**: Replaced Ansible `google.cloud.gcp_container_cluster` module with `gcloud` CLI commands for Standard cluster creation
  - Reason: Ansible module doesn't support newer GKE features like spot VMs and workload identity
  - Uses `gcloud container clusters create` with full feature support
  - Added idempotency check to prevent duplicate cluster creation
- Fixed HTTP load balancing configuration - changed from invalid `--enable-cloud-load-balancing` to `--addons=HttpLoadBalancing`
- Fixed variable naming inconsistency: `gke_min_node_count`/`gke_max_node_count` → `gke_min_nodes`/`gke_max_nodes`
- Added workload identity support via `--workload-pool` flag
- Spot VM support now works correctly with `--spot` flag

#### GKE Deployment Role (`roles/gke-deploy`)

**tasks/main.yml**:
- Added namespace creation task before secrets (line 145-158)
  - Issue: Secrets were being created before namespace existed, causing `NotFound` errors
  - Solution: Create namespace first, then secrets, then deployment
  - Tagged with `[namespace, secrets, deploy]` for flexibility

**tasks/secrets.yml**:
- Fixed GCP service account secret conditional logic (line 48-54)
  - Issue: Task ran even when `gke_gcp_sa_key_file=""` (empty string) because empty string is "defined"
  - Solution: Check both `is defined` AND `length > 0`
  - Prevents errors when using Workload Identity (no key file needed)

**templates/k8s-deployment.yml.j2**:
- Made GCP credentials volume mount conditional (lines 58-62, 93-97)
  - Issue: Pods failed with "secret 'gcp-sa-key' not found" when using Workload Identity
  - Solution: Only mount volume when `gke_gcp_sa_key_file` is configured
  - Allows Workload Identity (recommended) without needing service account keys
- Made `GOOGLE_APPLICATION_CREDENTIALS` environment variable conditional (lines 48-52)
  - Issue: Django tried to load non-existent credentials file even when using Workload Identity
  - Solution: Only set env var when key file is configured
  - Application now uses Workload Identity by default in GKE

### Documentation

#### Updated
- `docs/gke-cluster-provisioning-guide.md`:
  - Clarified that `gcp_region` is required for Autopilot clusters
  - Added note about node pool auto-detection timing
  - Updated cost estimates to reference spot VM savings
  - Added billing and kubectl to prerequisites

- `inventory/gcp_cluster.yml.example`:
  - Clarified node pool name comment about post-creation auto-detection
  - Updated region/zone examples to us-east1 (common deployment location)

#### Added
- `.gitignore`: Added `infrastructure/ansible/inventory/gcp_cluster.yml` to prevent committing user-specific configs

### Architecture Changes

**Workload Identity as Default**:
- GCP service account key files are now **optional** (recommended: don't use them)
- Workload Identity is the secure, modern way to grant GKE pods access to GCP services
- Key-based authentication still supported for legacy/development use cases

**Deployment Strategy**:
The new deployment order ensures proper resource creation:
1. Create namespace (if not exists)
2. Create secrets in namespace
3. Deploy application pods
4. Deploy CronJobs
5. Verify deployment

### Breaking Changes

⚠️ **Ansible google.cloud collection upgrade required**:
- Minimum version: 1.3.0+ (for spot VM support)
- Run: `ansible-galaxy collection install google.cloud --upgrade`
- Previous deployments using old collection version will fail

⚠️ **Inventory variable renamed**:
- Old: `gke_min_node_count`, `gke_max_node_count`
- New: `gke_min_nodes`, `gke_max_nodes`
- Update your `inventory/gcp_cluster.yml` if you have custom values

### Migration Guide

If you have an existing cluster provisioned with the old playbook:

1. **No action required for running clusters** - these changes only affect new provisioning
2. **For new deployments**: Update your inventory file variable names (see Breaking Changes)
3. **For redeployments**: Run `ansible-galaxy collection install google.cloud --upgrade` first

### Technical Details

**Why gcloud instead of Ansible module?**
- Ansible's `gcp_container_cluster` module lags behind GKE feature releases
- Missing support for: spot VMs, newer workload identity syntax, advanced networking
- `gcloud` CLI is Google's primary supported interface with immediate feature availability
- Maintains idempotency through explicit cluster existence checks

**Workload Identity vs Service Account Keys**:
- **Workload Identity** (recommended): No key files, automatic credential rotation, principle of least privilege
- **Service Account Keys**: Legacy approach, requires key management, security risk if leaked
- Our templates now support both but default to Workload Identity

### Testing Performed

- ✅ Fresh cluster provisioning in us-east1-b
- ✅ Standard cluster with spot VMs (2 e2-medium nodes)
- ✅ Workload Identity enabled and functional
- ✅ Multi-tenant Django deployment (2 tenants: ssc, masa)
- ✅ Pods running without GCP service account key files
- ✅ CronJobs created successfully
- ✅ Cross-region cost/latency verification (us-central1 → us-east1 migration)

### Credits

These fixes were implemented during a GKE cluster provisioning and deployment session on 2026-01-02, addressing runtime issues encountered during initial deployment attempts.
