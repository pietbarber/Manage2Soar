# IPv6 Dual-Stack Configuration Guide

This guide covers enabling IPv6 dual-stack networking for the Manage2Soar GKE infrastructure.

## Overview

IPv6 dual-stack enables both IPv4 and IPv6 connectivity for:
- **GKE Gateway/Ingress**: Accept traffic over both IPv4 and IPv6
- **VPC Network**: Custom VPC with dual-stack subnet
- **GKE Cluster**: Pods and services with IPv6 support
- **VMs**: Mail server and database with IPv6 addresses

## Prerequisites

### GCP Requirements

1. **Custom VPC**: Auto-mode VPCs don't support IPv6. You must create a custom VPC.
2. **Dataplane V2**: IPv6 requires GKE Dataplane V2 (Cilium). This is automatically enabled when `gke_enable_ipv6: true`.
3. **Project Quotas**: Ensure IPv6 quota is available in your region.
4. **API Access**: Compute Engine API must be enabled.

### Important gcloud Notes

- gcloud accepts both lowercase (`ipv4-ipv6`) and uppercase (`IPV4_IPV6`) for `--stack-type`
- The playbooks use **lowercase for clusters/VMs** (`ipv4-ipv6`) and **uppercase for subnets** (`IPV4_IPV6`) based on gcloud examples
- The `--ipv6-access-type` flag is only needed when creating a new subnet with `--create-subnetwork`
- When using an existing dual-stack subnet, the IPv6 access type is inherited from the subnet

### DNS Requirements

Once IPv6 is enabled, you'll need to add AAAA records for all domains:
- `m2s.manage2soar.com` (or your domain)
- `mail.manage2soar.com`
- Each tenant domain

## Configuration Variables

### Cluster Provisioning (`inventory/gcp_cluster.yml`)

```yaml
# Required: Custom VPC for IPv6 support
gke_create_vpc: true

# Enable IPv6 dual-stack
gke_enable_ipv6: true

# VPC/subnet names (used when gke_create_vpc: true)
gke_vpc_name: "manage2soar-vpc"
gke_subnet_name: "manage2soar-subnet"
gke_subnet_cidr: "10.0.0.0/20"
```

### Application Deployment (`group_vars/gcp_app/vars.yml`)

```yaml
# Enable IPv6 for ingress/gateway
gke_enable_ipv6: true
```

### Role Defaults (automatically set)

The `gke-deploy` role automatically sets default values:

```yaml
# IPv6 static IP name (defaults to cluster-name-ingress-ipv6)
gke_static_ipv6_name: "{{ gke_cluster_name }}-ingress-ipv6"
```

## Implementation Steps

### Step 1: Configure Inventory

1. Edit `inventory/gcp_cluster.yml`:
   ```yaml
   gke_create_vpc: true
   gke_enable_ipv6: true
   ```

2. Edit `group_vars/gcp_app/vars.yml`:
   ```yaml
   gke_enable_ipv6: true
   ```

### Step 2: Provision/Reprovision Infrastructure

**IMPORTANT**: Existing infrastructure must be torn down and reprovisioned. You cannot enable IPv6 on an existing auto-mode VPC or cluster.

```bash
# Option A: Fresh provisioning (new project)
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml

# Option B: Reprovision (existing project)
# WARNING: This deletes and recreates infrastructure!
# 1. Delete existing cluster
gcloud container clusters delete manage2soar-cluster \
  --zone=us-east1-b --project=manage2soar

# 2. Delete existing VMs (if in default network)
gcloud compute instances delete m2s-database \
  --zone=us-east1-b --project=manage2soar

gcloud compute instances delete m2s-mail \
  --zone=us-east1-b --project=manage2soar

# 3. Run provisioning playbook
ansible-playbook -i inventory/gcp_cluster.yml \
  playbooks/gcp-cluster-provision.yml
```

### Step 3: Deploy Application

```bash
ansible-playbook -i inventory/gcp_app.yml \
  -e @group_vars/gcp_app/vars.yml \
  -e @group_vars/gcp_app/vault.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-gke-deploy.yml
```

The deployment will:
1. Reserve a global IPv6 static IP
2. Configure the Gateway to use both IPv4 and IPv6 addresses
3. Display both IP addresses for DNS configuration

### Step 4: Configure DNS

After deployment, you'll see output like:

```
========================================
IP ADDRESSES FOR DNS CONFIGURATION
========================================
IPv4 (A record): 34.117.xxx.xxx
IPv6 (AAAA record): 2600:1901:xxxx::xxxx
========================================
```

Add both A and AAAA records to your DNS:

```
manage2soar.com.        A     34.117.xxx.xxx
manage2soar.com.        AAAA  2600:1901:xxxx::xxxx
m2s.manage2soar.com.    A     34.117.xxx.xxx
m2s.manage2soar.com.    AAAA  2600:1901:xxxx::xxxx
```

## Verification

### Check Static IPs

```bash
# List all reserved addresses
gcloud compute addresses list --project=manage2soar --global

# Verify IPv4
gcloud compute addresses describe manage2soar-cluster-ingress-ip \
  --global --project=manage2soar

# Verify IPv6
gcloud compute addresses describe manage2soar-cluster-ingress-ipv6 \
  --global --project=manage2soar
```

### Check Gateway Configuration

```bash
kubectl get gateway -n default -o yaml
```

Look for the `networking.gke.io/addresses` annotation containing both IP names.

### Test Connectivity

```bash
# Test IPv4
curl -4 https://m2s.manage2soar.com/health/

# Test IPv6 (requires IPv6 connectivity)
curl -6 https://m2s.manage2soar.com/health/
```

## VPC and Subnet Details

When `gke_create_vpc: true` and `gke_enable_ipv6: true`, the playbook creates:

### VPC Network

- **Name**: `{{ gke_vpc_name }}` (e.g., `manage2soar-vpc`)
- **Mode**: Custom (not auto-mode)
- **IPv6**: External IPv6 access enabled

### Subnet

- **Name**: `{{ gke_subnet_name }}` (e.g., `manage2soar-subnet`)
- **Stack Type**: `IPV4_IPV6`
- **IPv4 CIDR**: `{{ gke_subnet_cidr }}` (e.g., `10.0.0.0/20`)
- **IPv6**: Automatically allocated by Google
- **IPv6 Access Type**: `EXTERNAL`

### Firewall Rules

The playbook creates basic firewall rules:
- **SSH**: Port 22 from IAP (Identity-Aware Proxy)
- **Internal**: All ports between VPC resources
- **Health Checks**: Google health check ranges

## VM Configuration

VMs created with `gcp_enable_ipv6: true` (in `gcp-vm` role) will have:
- **Stack Type**: `IPV4_IPV6`
- **IPv6 Network Tier**: `PREMIUM`
- **External IPv6**: Enabled

## Mail Server IPv6

For the mail server to send/receive over IPv6:

1. Configure Postfix to bind to IPv6:
   ```
   inet_protocols = all
   ```

2. Add reverse DNS (PTR record) for the IPv6 address
3. Update SPF record to include IPv6:
   ```
   v=spf1 ip4:34.xxx.xxx.xxx ip6:2600:1901:xxxx::xxxx -all
   ```

## Troubleshooting

### "IPv6 not supported on auto-mode VPC"

IPv6 requires a custom VPC. Set `gke_create_vpc: true` and reprovision.

### "Subnet already exists"

Delete the existing subnet or use a different name:
```bash
gcloud compute networks subnets delete manage2soar-subnet \
  --region=us-east1 --project=manage2soar
```

### "Quota exceeded for IPv6"

Check your project quotas:
```bash
gcloud compute project-info describe --project=manage2soar
```

Request a quota increase if needed.

### "Gateway not accepting IPv6 traffic"

1. Verify the static IPv6 address exists
2. Check the Gateway annotation includes both IP names
3. Ensure DNS AAAA records are propagated

## Rollback

To disable IPv6 and revert to IPv4-only:

1. Update configuration:
   ```yaml
   gke_enable_ipv6: false
   ```

2. Redeploy:
   ```bash
   ansible-playbook -i inventory/gcp_app.yml \
     playbooks/gcp-gke-deploy.yml
   ```

3. Optionally release the IPv6 address:
   ```bash
   gcloud compute addresses delete manage2soar-cluster-ingress-ipv6 \
     --global --project=manage2soar
   ```

## Related Documentation

- [GKE Cluster Provisioning Guide](gke-cluster-provisioning-guide.md)
- [GKE Gateway/Ingress Guide](gke-gateway-ingress-guide.md)
- [GKE Deployment Guide](gke-deployment-guide.md)
- [Google Cloud IPv6 Documentation](https://cloud.google.com/vpc/docs/ipv6)
