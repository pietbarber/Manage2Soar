# GCP VM Role

This role handles GCP VM provisioning for Manage2Soar database servers.

## Features

- **Idempotent**: Creates VM only if it doesn't exist
- **Configurable**: Use existing VM or provision new one
- **Firewall management**: Creates necessary firewall rules for PostgreSQL
- **Static IP support**: Optional static external IP address

## Requirements

- Ansible 2.12+
- `google.cloud` collection (install via `ansible-galaxy collection install google.cloud`)
- GCP service account with Compute Admin permissions

## Role Variables

See `defaults/main.yml` for all available variables. Key ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `gcp_project` | (required) | GCP project ID |
| `gcp_vm_provision` | `true` | Whether to create VM if it doesn't exist |
| `gcp_vm_name` | `m2s-database` | Name of the VM instance |
| `gcp_machine_type` | `e2-small` | GCP machine type |
| `gcp_zone` | `us-east1-b` | GCP zone |

## Usage

```yaml
- hosts: localhost
  roles:
    - role: gcp-vm
      vars:
        gcp_project: "my-gcp-project"
        gcp_vm_name: "m2s-database-prod"
        gcp_postgresql_allowed_sources:
          - "10.0.0.0/8"
```

## Authentication

Set one of these authentication methods:

1. **Application Default Credentials** (recommended for GCP environments):
   ```bash
   gcloud auth application-default login
   ```

2. **Service Account Key**:
   ```yaml
   gcp_auth_kind: "serviceaccount"
   gcp_service_account_file: "/path/to/key.json"
   ```
