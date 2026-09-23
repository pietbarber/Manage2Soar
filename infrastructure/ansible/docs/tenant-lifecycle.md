# Tenant Lifecycle Controls

This runbook controls application lifecycle independently from data retention.
It never deletes PostgreSQL databases, Cloud Storage media, backups, Vault
secrets, or mail-server configuration.

## Tenant Configuration

In `group_vars/gcp_app/vars.yml`, define lifecycle fields for each entry in
`gke_tenants`:

```yaml
- prefix: "example"
  name: "Example Soaring Club"
  status: "active"
  cronjobs_enabled: true
```

`status` defaults to `active` for compatibility with existing tenant entries.

- `active`: included in normal namespaces, app deployments, routes, health
  checks, and TLS certificate domains.
- `suspended`: excluded from normal deployment and routing. Use
  `suspend-tenant.yml` to stop the existing workload.
- `retired`: excluded from normal deployment and routing. The namespace can be
  deleted only with `retire-tenant-namespace.yml`.

`cronjobs_enabled` controls `spec.suspend` for every managed CronJob when the
tenant is deployed. It does not delete CronJobs.

In the matching `postgresql_tenants` entry, use `login_enabled: false` to apply
`NOLOGIN` to the tenant database role while preserving its database and owner.
Rerun the PostgreSQL playbook after changing this value.

## Suspend a Tenant

1. Preserve and independently verify the tenant database and media archive.
2. Set `status: "suspended"` and `cronjobs_enabled: false` in the app tenant
   inventory.
3. Set `login_enabled: false` for the matching PostgreSQL tenant, then rerun
   the PostgreSQL playbook to apply `NOLOGIN`.
4. Run the guarded suspension playbook:

```bash
cd infrastructure/ansible
source ../../.venv/bin/activate
ansible-playbook -i inventory/gcp_app.yml \
  playbooks/suspend-tenant.yml \
  -e suspend_tenant_prefix=svs \
  -e suspend_confirmation=SUSPEND_TENANT_WORKLOAD
```

The suspension playbook scales `django-app-<prefix>` to zero, suspends its
existing CronJobs, and removes its HTTP and HTTPS routes. Its only mutations are
inside `tenant-<prefix>`.

## Retire a Tenant Namespace

After the approved rollback window, set `status: "retired"` and run:

```bash
cd infrastructure/ansible
source ../../.venv/bin/activate
ansible-playbook -i inventory/gcp_app.yml \
  playbooks/retire-tenant-namespace.yml \
  -e retire_tenant_prefix=svs \
  -e retire_confirmation=DELETE_KUBERNETES_NAMESPACE
```

The retirement playbook requires the tenant to be explicitly marked `retired`
and deletes only `tenant-<prefix>`. It does not invoke PostgreSQL, GCS, DNS,
mail, or Vault modules.

## NFSS Onboarding

Use `nfss.manage2soar.com` as the tenant hostname. Add NFSS initially with
`status: "active"`, `cronjobs_enabled: false`, and outbound email development
mode enabled only in a staging/development deployment with a safe redirect
mailbox. Production defaults to `gke_environment: "production"` and rejects
per-tenant `email_dev_mode: true`. Add its Vault secrets and PostgreSQL tenant
separately, then enable production mail and CronJobs only after acceptance
testing.
