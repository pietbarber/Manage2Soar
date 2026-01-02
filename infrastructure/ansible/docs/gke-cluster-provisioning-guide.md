# GKE Cluster Provisioning Guide

This guide covers provisioning Google Kubernetes Engine (GKE) clusters using Ansible for Manage2Soar deployments.

## Overview

The `gcp-cluster-provision.yml` playbook creates and configures GKE clusters with:
- Standard or Autopilot cluster modes
- Configurable node pools with autoscaling
- Optional VPC networking
- Workload Identity for secure GCP access
- Cost optimization options (spot VMs)

## Quick Start

### Step 1: Install Prerequisites

```bash
# Install Ansible collections
ansible-galaxy collection install google.cloud community.general

# Authenticate with GCP
gcloud auth application-default login

# Verify gcloud is configured
gcloud config get-value project
```

### Step 2: Configure Inventory

```bash
cd infrastructure/ansible

# Copy the example inventory
cp inventory/gcp_cluster.yml.example inventory/gcp_cluster.yml

# Edit with your settings
vim inventory/gcp_cluster.yml
```

**Minimum required changes:**
```yaml
# Set your GCP project
gcp_project: "your-actual-project-id"

# Set your preferred zone/region
gcp_zone: "us-east1-b"
gcp_region: "us-east1"

# Name your cluster
gke_cluster_name: "manage2soar-cluster"
```

### Step 3: Provision the Cluster

```bash
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml
```

The playbook will:
1. Enable required GCP APIs
2. Create VPC/subnet (if configured)
3. Create the GKE cluster
4. Configure autoscaling
5. Get kubectl credentials
6. Verify cluster access

## Cluster Types

### Standard Cluster (Default)

Full control over nodes, node pools, and scaling. You pay for the VMs.

```yaml
gke_cluster_type: "standard"
gke_machine_type: "e2-medium"
gke_initial_node_count: 2
gke_enable_autoscaling: true
gke_min_nodes: 1
gke_max_nodes: 5
```

**Pros:**
- Full control over node configuration
- Predictable costs
- Can use spot/preemptible VMs

**Cons:**
- You manage node pools and scaling
- Pay for idle capacity

### Autopilot Cluster

Google manages the nodes. You pay per pod resource usage.

```yaml
gke_cluster_type: "autopilot"
```

**Pros:**
- No node management
- Pay only for pod resources
- Automatic security patching

**Cons:**
- Less control over node configuration
- Some workloads may not fit Autopilot constraints
- Slightly higher per-resource cost

## Cost Optimization

### Use Spot VMs (Standard clusters)

Spot VMs are up to 91% cheaper but can be preempted.

```yaml
gke_use_spot_vms: true
```

**Best for:**
- Development/staging clusters
- Stateless workloads
- Workloads that can handle interruptions

**Not recommended for:**
- Production with strict uptime requirements
- Stateful workloads without proper handling

### Right-size Your Cluster

| Use Case | Recommended Config |
|----------|-------------------|
| Development | `e2-small`, 1-2 nodes, spot VMs |
| Staging | `e2-medium`, 2-3 nodes |
| Small Production | `e2-medium`, 2-5 nodes |
| Large Production | `e2-standard-4`, 3-10 nodes |

## Networking Options

### Default VPC (Simple)

Uses GCP's default VPC. Good for most use cases.

```yaml
gke_create_vpc: false
```

### Custom VPC (Isolated)

Creates a dedicated VPC for the cluster. Better for:
- Multi-environment isolation
- Specific IP range requirements
- Private clusters

```yaml
gke_create_vpc: true
gke_vpc_name: "manage2soar-vpc"
gke_subnet_name: "manage2soar-subnet"
gke_subnet_cidr: "10.0.0.0/20"
gke_pods_cidr: "10.4.0.0/14"
gke_services_cidr: "10.8.0.0/20"
```

## Configuration Reference

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `gcp_project` | GCP project ID | `"manage2soar"` |
| `gke_cluster_name` | Cluster name | `"manage2soar-cluster"` |
| `gcp_zone` | GCP zone | `"us-east1-b"` |

### Cluster Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `gke_cluster_type` | `"standard"` | Cluster type: `standard` or `autopilot` |
| `gke_kubernetes_version` | `""` | K8s version (empty = latest stable) |
| `gke_initial_node_count` | `2` | Initial nodes (Standard only) |
| `gke_machine_type` | `"e2-medium"` | Node machine type |
| `gke_disk_size_gb` | `50` | Node disk size |
| `gke_disk_type` | `"pd-standard"` | Disk type |

### Autoscaling (Standard only)

| Variable | Default | Description |
|----------|---------|-------------|
| `gke_enable_autoscaling` | `true` | Enable node autoscaling |
| `gke_min_nodes` | `1` | Minimum nodes |
| `gke_max_nodes` | `5` | Maximum nodes |
| `gke_use_spot_vms` | `false` | Use spot/preemptible VMs |

### Networking

| Variable | Default | Description |
|----------|---------|-------------|
| `gke_create_vpc` | `false` | Create dedicated VPC |
| `gke_vpc_name` | `"manage2soar-vpc"` | VPC name |
| `gke_subnet_cidr` | `"10.0.0.0/20"` | Subnet CIDR |
| `gke_private_cluster` | `false` | Private cluster (no public IPs) |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `gke_enable_workload_identity` | `true` | Enable Workload Identity |
| `gke_master_authorized_networks` | `[]` | CIDRs that can access API |

## Playbook Tags

Run specific parts of the playbook:

```bash
# Only enable APIs
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml --tags apis

# Only create network
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml --tags network

# Only create cluster
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml --tags cluster

# Only verify
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml --tags verify
```

## Troubleshooting

### API Not Enabled

```
ERROR: Kubernetes Engine API has not been used in project...
```

**Fix:** The playbook enables APIs automatically. If you still see this, wait 1-2 minutes and retry.

```bash
gcloud services enable container.googleapis.com --project=YOUR_PROJECT
```

### Quota Exceeded

```
ERROR: Quota 'CPUS' exceeded. Limit: 8.0 in region us-central1.
```

**Fix:** Request a quota increase or use a smaller machine type.

```bash
# Check current quotas
gcloud compute regions describe us-central1 --project=YOUR_PROJECT

# Use smaller machines
ansible-playbook ... -e gke_machine_type=e2-small
```

### Cluster Already Exists

```
ERROR: Resource already exists
```

**Fix:** The cluster already exists. The playbook is idempotent but won't change existing clusters. Delete first if you need to recreate:

```bash
gcloud container clusters delete CLUSTER_NAME --zone=ZONE --project=PROJECT
```

### Authentication Failed

```
ERROR: Could not automatically determine credentials
```

**Fix:** Re-authenticate with gcloud:

```bash
gcloud auth application-default login
gcloud auth login
```

## Integration with App Deployment

After provisioning the cluster, deploy your application:

```bash
# 1. Provision cluster (this playbook)
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml

# 2. Deploy application
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml
```

## Cluster Destruction

**⚠️ Warning:** Cluster destruction is intentionally manual to prevent accidental deletion.

```bash
# Delete cluster (DESTRUCTIVE!)
gcloud container clusters delete CLUSTER_NAME \
  --zone=ZONE \
  --project=PROJECT

# If you created a VPC
gcloud compute networks subnets delete SUBNET_NAME --region=REGION
gcloud compute networks delete VPC_NAME
```

## Cost Estimates

Approximate monthly costs (as of 2025):

| Configuration | Monthly Cost |
|---------------|--------------|
| 2x e2-small (spot) | ~$15 |
| 2x e2-medium | ~$50 |
| 2x e2-medium (spot) | ~$20 |
| 3x e2-standard-4 | ~$200 |
| Autopilot (light usage) | ~$30-50 |

*Note: Costs vary by region and usage. Use the [GCP Pricing Calculator](https://cloud.google.com/products/calculator) for accurate estimates.*
