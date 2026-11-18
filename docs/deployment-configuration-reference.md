# Deployment Configuration Reference

This is the configuration reference for the current Manage2Soar deployment
paths. It covers the variables supplied to Ansible, the environment variables
rendered into the application, and the settings module that consumes each
value.

The reference is split into two layers:

1. **Ansible variables** configure infrastructure and render application
   configuration.
2. **Runtime environment variables** are consumed by Django and its libraries.

Do not edit generated files on a server. Change the appropriate inventory,
`group_vars`, or Ansible Vault file and re-run the deployment.

## Deployment paths and source of truth

| Path | Configuration entry point | Runtime settings | Generated runtime config |
|---|---|---|---|
| GKE application | `infrastructure/ansible/group_vars/gcp_app/vars.yml` and `vault.yml` | `manage2soar.settings` | Kubernetes Secret from `roles/gke-deploy/templates/k8s-secrets.yml.j2` |
| Single host | `infrastructure/ansible/group_vars/single_host/vars.yml` and `vault.yml` | `manage2soar.settings_single_host` | `/opt/m2s/app/.env` from `roles/m2s-app/templates/env.j2` |
| GKE cluster | `group_vars/gcp_cluster/` | N/A | GKE cluster resources |
| Dedicated database VM | `group_vars/gcp_database_servers/` | N/A | PostgreSQL configuration |
| Dedicated mail VM | `group_vars/gcp_mail/` and shared `group_vars/all.yml` | N/A | Postfix/OpenDKIM/Rspamd configuration |

The checked-in `*.example` files are starting points, not live configuration.
The real `group_vars/<target>/` directories are gitignored. Secrets belong in
Ansible Vault, never in ordinary vars files or generated manifests.

### Precedence

For a deployed value, the effective precedence is generally:

1. `-e` extra vars passed to Ansible
2. host/group vars
3. role defaults
4. Django's environment-variable default

For GKE, the tenant entry in `gke_tenants` can override selected global values
such as `email_dev_mode`, `email_dev_mode_redirect_to`, and
`default_from_email`.

## Runtime environment variables

These are the application-facing variables. Values marked **required** must be
present for a production deployment even if Django has a development fallback.
Comma-separated values are shown without shell quoting; quote values containing
spaces or shell metacharacters in hand-written `.env` files.

### Django and security

| Variable | GKE | Single host | Default / required value | Purpose |
|---|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | yes | yes | `manage2soar.settings` / `manage2soar.settings_single_host` | Selects the settings module. |
| `DJANGO_SECRET_KEY` | Vault | Vault | **Required** | Django signing and cryptographic secret. Generate a unique value per deployment. |
| `DJANGO_DEBUG` | `gke_django_debug` | `m2s_django_debug` | `false` in deployment examples | Must remain false in production. The base settings module defaults to true for local development, so do not rely on that fallback. |
| `DJANGO_ALLOWED_HOSTS` | `gke_django_allowed_hosts` or ingress-derived | emitted for compatibility | `localhost,127.0.0.1` | Used by `manage2soar.settings`. Never use `*` in production. |
| `ALLOWED_HOSTS` | emitted only for compatibility | `m2s_django_allowed_hosts` | `localhost,127.0.0.1` | Used by `manage2soar.settings_single_host`. |
| `SITE_URL` | derived from tenant/domain | `m2s_site_url` | **Required when `DEBUG=false`** | Public canonical origin used for absolute URLs and links. Include scheme, normally `https://`. |
| `CSRF_TRUSTED_ORIGINS` | derived from tenant domains | `m2s_csrf_trusted_origins` | **Required by base settings when `DEBUG=false`** | Comma-separated origins including scheme, for example `https://club.example`. |
| `SSL_ENABLED` | emitted by the single-host env template only | `nginx_ssl_enabled`/proxy mode | `false` | Used by single-host settings to enable HTTPS redirects and secure cookies. The base GKE settings use their production policy variables instead. |
| `SECURE_SSL_REDIRECT` | supported by base settings | **not consumed by single-host settings** | `true` in base production settings | Redirect HTTP to HTTPS. Single-host behavior is controlled by `SSL_ENABLED`. |
| `SECURE_HSTS_SECONDS` | optional extra env | optional extra env | `31536000` when production security is active | HSTS duration. Set to `0` until HTTPS is correctly serving; HSTS is difficult to undo. |
| `SESSION_COOKIE_SECURE` | supported by base settings | **not consumed by single-host settings**; derived from `SSL_ENABLED` | true in base production settings | Send session cookies only over HTTPS. |
| `CSRF_COOKIE_SECURE` | supported by base settings | **not consumed by single-host settings**; derived from `SSL_ENABLED` | true in base production settings | Send CSRF cookies only over HTTPS. |
| `SESSION_COOKIE_SAMESITE` | `gke_session_cookie_samesite` | `m2s_session_cookie_samesite` | `Lax` | Session cookie SameSite policy. `None` requires secure cookies. |
| `CSRF_COOKIE_SAMESITE` | `gke_csrf_cookie_samesite` | `m2s_csrf_cookie_samesite` | `Lax` | CSRF cookie SameSite policy. |
| `KIOSK_COOKIE_SECURE` | optional extra env | optional extra env | true in non-debug single-host production | Protects kiosk authentication cookies. |
| `DJANGO_TESTING` | no | no | unset | Explicitly marks a test run; do not set in a deployed workload. |
| `DJANGO_TIMEZONE` | not consumed; base settings hard-code `America/New_York` | supported | `America/New_York` | Single-host timezone override. |

### Database

| Variable | GKE | Single host | Default / required value | Purpose |
|---|---|---|---|---|
| `DB_NAME` | `gke_db_name` or `m2s_<tenant>` | `m2s_db_name` | **Required** | PostgreSQL database name. |
| `DB_USER` | `gke_db_user` or `m2s_<tenant>` | `m2s_db_user` | **Required** | PostgreSQL login role. |
| `DB_PASSWORD` | Vault | Vault | **Required** | PostgreSQL password. Use a unique value per tenant. |
| `DB_HOST` | `gke_db_host` | `m2s_db_host` | `localhost` in settings; must be overridden for remote DB | PostgreSQL host or address. |
| `DB_PORT` | `gke_db_port` | `m2s_db_port` | `5432` | PostgreSQL port. |
| `DB_SSLMODE` | `gke_db_sslmode` | not consumed | `require` in base settings | libpq SSL mode. GKE role defaults to `prefer` unless PostgreSQL SSL is enabled. |
| `DB_CONN_MAX_AGE` | `gke_db_conn_max_age` | not consumed | `300` seconds in base settings | Django persistent connection lifetime. |
| `LEGACY_DB_NAME` | optional | not consumed | unset | Legacy database alias, base settings only. |
| `LEGACY_DB_USER` | optional | not consumed | unset | Legacy database alias, base settings only. |
| `LEGACY_DB_PASSWORD` | optional | not consumed | unset | Legacy database alias, base settings only. |
| `LEGACY_DB_HOST` | optional | not consumed | `localhost` | Legacy database alias, base settings only. |
| `LEGACY_DB_PORT` | optional | not consumed | `5555` | Legacy database alias, base settings only. |

### Google Cloud Storage and files

The GKE settings module uses GCS when `GS_BUCKET_NAME` is non-empty. Without it,
the base settings module falls back to local storage. Single-host deployments
use local filesystem storage regardless of these GCS variables.

| Variable | GKE | Single host | Default / required value | Purpose |
|---|---|---|---|---|
| `GS_BUCKET_NAME` | `gke_gcs_bucket` | not used | empty means local storage in base settings | Main bucket for static and media files. |
| `GS_IMPORT_EXPORT_BUCKET_NAME` | `gke_gcs_import_export_bucket` | not used | unset | Private bucket for temporary member import/export files. |
| `GS_PROJECT_ID` | `gke_gcs_project_id` | not used | unset | Optional GCP project identifier for storage. |
| `GOOGLE_APPLICATION_CREDENTIALS` | set when `gke_gcp_sa_key_file` is configured | not used | unset | Path to mounted service-account JSON credentials. Prefer workload identity where available. |
| `GS_DEFAULT_ACL` | `gke_gcs_default_acl` | not used | `private` in GKE role; `publicRead` in base settings fallback | Keep user-uploaded media private. The role default is safer than the application fallback. |
| `CLUB_PREFIX` | `gke_club_prefix` | `club_prefix` | tenant prefix / `ssc` in settings | Tenant isolation and GCS path prefix. Only letters, numbers, and hyphens are accepted. |
| `GS_MEDIA_LOCATION` | `gke_gcs_media_location` | not used | `<CLUB_PREFIX>/media` | Media object prefix. |
| `GS_STATIC_LOCATION` | `gke_gcs_static_location` | not used | `<CLUB_PREFIX>/static` | Static object prefix. |
| `MEDIA_URL` | `gke_media_url` | not used | derived GCS URL in production | Public media URL. |
| `STATIC_URL` | `gke_static_url` | not used | derived GCS URL in production | Public static URL. |
| `STATIC_ROOT` | not emitted by GKE | `m2s_django_static_root` | `/var/www/m2s/static` | Local collectstatic destination. |
| `MEDIA_ROOT` | not emitted by GKE | `m2s_django_media_root` | `/var/www/m2s/media` | Local media filesystem root. |
| `IMPORT_EXPORT_TMP_DIR` | optional extra env | `m2s_import_export_tmp_dir` | `/tmp/m2s-import-export-tmp` in dev; role path in production | Private temporary storage for member import/export files. Keep it outside public media. |
| `TINYMCE_JS_URL` | optional extra env | optional extra env | derived from `STATIC_URL` | TinyMCE JavaScript URL override. |

### Email and external services

| Variable | GKE | Single host | Default / required value | Purpose |
|---|---|---|---|---|
| `EMAIL_BACKEND` | `gke_email_backend` | `m2s_email_backend` | SMTP in deployment examples; console in single-host settings fallback | Django email backend. |
| `EMAIL_HOST` | `gke_email_host` | `m2s_email_host` | `localhost` in role defaults | SMTP host. |
| `EMAIL_PORT` | `gke_email_port` | `m2s_email_port` | `587` GKE / `25` single-host role default | SMTP port. |
| `EMAIL_USE_TLS` | `gke_email_use_tls` | `m2s_email_use_tls` | true GKE / false single-host role default | Enable SMTP TLS. |
| `EMAIL_TIMEOUT` | `gke_email_timeout` (template default `20`) | **not supported by current single-host settings/template** | `30` in base settings | SMTP connection timeout in seconds. A single-host `m2s_extra_env_vars` entry is currently ignored because the settings module does not read it. |
| `EMAIL_HOST_USER` | Vault | Vault or empty | unset/empty | Authenticated SMTP username. |
| `EMAIL_HOST_PASSWORD` | Vault | Vault or empty | unset/empty | Authenticated SMTP password. |
| `DEFAULT_FROM_EMAIL` | `gke_default_from_email` or tenant override | `m2s_default_from_email` | `noreply@<mail_domain>` or `noreply@example.com` | Sender used by Django. |
| `EMAIL_DEV_MODE` | `gke_email_dev_mode` or tenant override | `email_dev_mode` | false in GKE role; template fallback is true for single host | Redirect all Django email when enabled. **Never leave this enabled for production delivery.** |
| `EMAIL_DEV_MODE_REDIRECT_TO` | `gke_email_dev_mode_redirect_to` or tenant override | `email_dev_mode_redirect_to` | empty | Comma-separated safe recipient(s) used by email dev mode. |
| `M2S_MAIL_API_KEY` | `m2s_api_key` | **not consumed by current single-host settings** | empty | API key used by `/api/email-lists/`. Without it, the endpoint returns HTTP 500. |
| `SOCIAL_AUTH_GOOGLE_OAUTH2_KEY` | Vault, global or per tenant | Vault | unset disables Google OAuth credentials | Google OAuth client ID. |
| `SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET` | Vault, global or per tenant | Vault | unset disables Google OAuth credentials | Google OAuth client secret. |

### CMS, logging, and build metadata

| Variable | GKE | Single host | Default / required value | Purpose |
|---|---|---|---|---|
| `TINYMCE_PDF_TRUSTED_URL_PREFIXES` | `gke_extra_env` | `m2s_extra_env_vars` | empty in production | Comma-separated trusted prefixes for uploaded/proxied PDF embeds. Use exact prefixes, never a wildcard. |
| `CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS` | `gke_extra_env` | `m2s_extra_env_vars` | empty (feature disabled) | Explicit external host allowlist for the same-origin PDF proxy. |
| `CMS_EXTERNAL_PDF_PROXY_CACHE_TTL_SECONDS` | `gke_extra_env` | `m2s_extra_env_vars` | `86400` | External PDF proxy cache lifetime. |
| `DJANGO_LOG_FILE` | **not consumed by base settings** | `m2s_django_log_file` | `/var/log/m2s/django.log` | Single-host Django file log path. GKE normally relies on container logs. |
| `BUILD_HASH` | Docker build argument / optional env | optional env | empty; falls back to file mtime | PWA cache-busting identifier. |

## GKE Ansible variables

The application deployment entry point is
`infrastructure/ansible/group_vars/gcp_app/vars.yml`. The complete role defaults are in
[`roles/gke-deploy/defaults/main.yml`](../infrastructure/ansible/roles/gke-deploy/defaults/main.yml).

### Required or normally overridden

| Variable | Meaning | Notes |
|---|---|---|
| `gcp_project` | GCP project ID | Required; also drives default image and GCS names. |
| `gcp_region`, `gcp_zone` | GCP location | Must match the cluster and supporting resources. |
| `gke_cluster_name`, `gke_cluster_zone` | Target GKE cluster | Cluster must already exist unless using the cluster provisioning workflow. |
| `gke_base_domain`, `gke_app_domain` | Public DNS names | Used for URLs, host allowlists, and routes. |
| `gke_django_settings_module` | Django settings module | Use `manage2soar.settings` for GKE. |
| `gke_django_debug` | Django debug mode | Must be `false` in production. |
| `gke_django_allowed_hosts` | Fallback host allowlist | Ingress mode derives hosts from tenant/domain config. |
| `gke_replicas` | Django pod count | Increase for availability and peak load. |
| `gke_cpu_request`, `gke_cpu_limit` | Pod CPU resources | Kubernetes resource requests/limits. |
| `gke_memory_request`, `gke_memory_limit` | Pod memory resources | PDF and import workloads may need more than defaults. |
| `postgresql_host` / `gke_db_host` | Database address | The role's documentation IP default intentionally forces an explicit value. |
| `gke_db_port`, `gke_db_name`, `gke_db_user` | Database connection | Tenant mode derives database name/user from the prefix. |
| `gke_db_sslmode`, `gke_db_conn_max_age` | Database behavior | Match the PostgreSQL server's SSL and connection policy. |
| `gke_gcs_bucket`, `gke_gcs_import_export_bucket` | Storage buckets | Keep the import/export bucket private. |
| `club_prefix` / `gke_club_prefix` | Tenant storage/database prefix | Must match tenant and per-tenant secret naming. |
| `mail_host`, `mail_port`, `mail_domain` | SMTP and sender domain | `mail_domain` is also used to derive the default sender. |
| `gke_image_tag_type`, `gke_image_tag` | Image version | A manually supplied `gke_image_tag` takes precedence. |
| `gke_gcp_sa_key_file` | Local service-account key path | If set, the key is copied into a Kubernetes Secret and mounted in pods. Protect and delete generated manifests. |

### Deployment behavior

| Variable | Default | Meaning |
|---|---:|---|
| `gke_build_image` | true | Build the Docker image locally. |
| `gke_push_image` | true | Push the image to the configured registry. |
| `gke_apply_config` | true | Apply generated Kubernetes resources. |
| `gke_wait_for_rollout` | true | Wait for deployment readiness. |
| `gke_run_verify` | true | Run post-deployment checks. |
| `gke_rollout_timeout` | 900 | Rollout and migration timeout in seconds. |
| `gke_run_migrations` | false | Run migrations in the pre-rollout Job. Enable deliberately for releases requiring schema changes. |
| `gke_collect_static` | true | Run `collectstatic` after deployment. Disabling can leave the site without new CSS/JS. |
| `gke_normalize_pdf_iframes` | true | Normalize legacy CMS PDF embeds. |
| `gke_management_command_retries`, `gke_management_command_retry_delay` | 3, 10 | Retry count and delay for management commands. |
| `gke_keep_manifests` | false | Keep generated manifests for debugging. They may contain secrets. |
| `gke_run_backfill_document_sizes` | false | Run the optional CMS document-size backfill. Related controls are `gke_backfill_document_sizes_only_missing`, `gke_backfill_document_sizes_batch_size`, and `gke_backfill_document_sizes_dry_run`. |
| `gke_docker_context` | `.` | Docker build context. |

### Multi-tenant, ingress, and scheduled jobs

| Variable | Meaning |
|---|---|
| `gke_multi_tenant` | Deploy one namespace, database, secret, and workload per tenant. |
| `gke_tenants` | Tenant list; each item normally has `prefix`, `name`, and `domain` or `domains`. Optional fields include `namespace`, `replicas`, `email_dev_mode`, `email_dev_mode_redirect_to`, `default_from_email`, and `cronjobs_enabled`. |
| `gke_enable_ingress` | Enable Gateway API resources. Host allowlists and site URLs are derived from tenant domains when enabled. |
| `gke_static_ip_name` | Reserved IPv4 address name for the Gateway. |
| `gke_fail_on_unbound_static_ipv4` | Fail if the reserved address is not attached after reconciliation. |
| `gke_cleanup_unbound_static_ipv4`, `gke_cleanup_unbound_static_ipv4_execute` | Opt-in cleanup of an unbound reserved IPv4 address. Both must be true to delete. |
| `gke_cleanup_unbound_static_ipv4_grace_seconds` | Delay before rechecking an unbound address. |
| `gke_enable_ipv6`, `gke_static_ipv6_name` | Reserve and use an IPv6 Gateway address; requires an IPv6-enabled cluster. |
| `gke_enable_tls`, `gke_ssl_cert_name` | Enable Google-managed HTTPS and select its certificate resource. |
| `gke_deploy_cronjobs` | Create the scheduled Django management jobs. |
| `gke_cronjobs_suspended` | Suspend jobs without deleting them. |
| `gke_cronjob_image` | Image used by jobs; normally follows the application image. |
| `gke_create_superuser` | Create the initial Django superuser. Credentials are `django_superuser_username`, optional `django_superuser_email`, and Vault-only `vault_django_superuser_password_<prefix>`. |
| `gke_validate_email_config`, `gke_validate_security` | Enable pre-deployment safety checks. Keep enabled. |
| `gke_environment` | Validation environment: `production`, `staging`, or `development`. |
| `gke_extra_env` | Explicit map of additional runtime environment variables. Review every entry because it bypasses the typed settings catalog. |

## Single-host Ansible variables

The application entry point is `group_vars/single_host/vars.yml`. The complete
application defaults are in
[`roles/m2s-app/defaults/main.yml`](../infrastructure/ansible/roles/m2s-app/defaults/main.yml).

| Group | Variables |
|---|---|
| Club and URL | `club_name`, `club_prefix`, `m2s_domain`, `m2s_site_url`, `m2s_csrf_trusted_origins` |
| PostgreSQL | `postgresql_database`, `postgresql_user`, `postgresql_password`, `postgresql_version`, `postgresql_shared_buffers`, `postgresql_effective_cache_size`, `postgresql_work_mem`, `postgresql_maintenance_work_mem`, `postgresql_backup_enabled`, `postgresql_backup_retention_days`, `m2s_db_host`, `m2s_db_port`, `m2s_db_name`, `m2s_db_user` |
| Application | `m2s_app_user`, `m2s_app_group`, `m2s_app_home`, `m2s_git_repo`, `m2s_git_branch`, `m2s_git_force_update`, `m2s_python_version`, `m2s_venv_path`, `m2s_django_settings_module`, `m2s_django_debug`, `m2s_django_allowed_hosts`, `m2s_django_static_root`, `m2s_django_media_root`, `m2s_import_export_tmp_dir`, `m2s_import_export_retention_days`, `m2s_extra_env_vars` |
| Gunicorn and logs | `m2s_gunicorn_bind`, `m2s_gunicorn_workers`, `m2s_gunicorn_worker_class`, `m2s_gunicorn_timeout`, `m2s_gunicorn_max_requests`, `m2s_gunicorn_max_requests_jitter`, `m2s_log_dir`, `m2s_gunicorn_access_log`, `m2s_gunicorn_error_log`, `m2s_django_log_file` |
| Email and OAuth | `m2s_email_backend`, `m2s_email_host`, `m2s_email_port`, `m2s_email_use_tls`, `m2s_default_from_email`, `m2s_google_oauth_enabled`, `email_dev_mode`, `email_dev_mode_redirect_to` |
| Mail server | `mail_server_enabled`, `mail_hostname`, `mail_domain`, `mail_server_receive_enabled`, `smtp_relay_host`, `smtp_relay_port`, `club_domains`, `dkim_selector` |
| NGINX and proxy | `nginx_ssl_enabled`, `letsencrypt_email`, `nginx_http_port`, `nginx_https_port`, `nginx_public_proxy_mode`, `nginx_proxy_listen_address`, `nginx_proxy_http_port`, `nginx_external_scheme`, `nginx_external_port`, `nginx_public_proxy_real_ip_from`, `nginx_public_proxy_allow_private_bind`, `nginx_http2_enabled`, `nginx_rate_limit_enabled` |
| Host security and backups | `firewall_enabled`, `ssh_port`, `fail2ban_enabled`, `backup_enabled`, `backup_retention_days`, `backup_dir` |

## Dedicated infrastructure variables

These variables configure supporting servers rather than the Django process.
Use the role defaults as the exhaustive schema and override only what the
deployment needs.

| Component | Main variable groups | Defaults |
|---|---|---|
| GKE cluster provisioning | `gke_cluster_type`, `gke_machine_type`, node count/autoscaling, spot VMs, VPC/subnet/CIDRs, private nodes/endpoints, Cloud NAT, IPv6, labels | [`gcp_cluster.vars.yml.example`](../infrastructure/ansible/group_vars/gcp_cluster.vars.yml.example) and [cluster provisioning guide](../infrastructure/ansible/docs/gke-cluster-provisioning-guide.md) |
| PostgreSQL | `postgresql_version`, database/user/tenant lists, `postgresql_listen_addresses`, `postgresql_port`, `postgresql_max_connections`, remote CIDRs, SSL, memory/WAL, local/GCS backup, additional databases/users | [`postgresql/defaults/main.yml`](../infrastructure/ansible/roles/postgresql/defaults/main.yml) |
| GCP VM | project/location, `gcp_vm_provision`, VM/disk/image, network/IP, firewall sources, SSH keys, labels, service account, auth | [`gcp-vm/defaults/main.yml`](../infrastructure/ansible/roles/gcp-vm/defaults/main.yml) |
| NGINX | domain/certificates, listener/proxy mode, upstream, static/media, logs, rate limits, body size, headers, workers, gzip, cache | [`nginx/defaults/main.yml`](../infrastructure/ansible/roles/nginx/defaults/main.yml) |
| UFW | `ufw_default_incoming_policy`, `ufw_default_outgoing_policy`, SSH, allowed ports, `ufw_enabled`, `ufw_reset` | [`ufw/defaults/main.yml`](../infrastructure/ansible/roles/ufw/defaults/main.yml) |
| Postfix | config path, hostname, trusted relays, SMTP auth users, relay host/port/credentials, TLS, `single_host_mode` | [`postfix/defaults/main.yml`](../infrastructure/ansible/roles/postfix/defaults/main.yml) |
| OpenDKIM | config/key paths, `dkim_selector`, `dkim_key_size`, club domains | [`opendkim/defaults/main.yml`](../infrastructure/ansible/roles/opendkim/defaults/main.yml) |
| Rspamd | reject/header/rewrite scores, Redis host/port, receive-mode prerequisites | [`rspamd/defaults/main.yml`](../infrastructure/ansible/roles/rspamd/defaults/main.yml) |
| GCS backups | project/location, bucket/storage class, KMS keyring/key/rotation, VM service account, lifecycle, auth | [`gcs-backup/defaults/main.yml`](../infrastructure/ansible/roles/gcs-backup/defaults/main.yml) |

## Vault variables

At minimum, define these in the target encrypted Vault file:

| Variable | Used by | Required when |
|---|---|---|
| `vault_django_secret_key` | Django | Always |
| `vault_django_secret_key_<prefix>` | Tenant Django | Multi-tenant mode when per-tenant signing isolation is enabled; falls back to the shared key if absent |
| `vault_postgresql_password` | Single-tenant Django/PostgreSQL | Single-tenant mode |
| `vault_postgresql_password_<prefix>` | Tenant Django/PostgreSQL | Multi-tenant mode, once per tenant |
| `vault_email_host_user`, `vault_email_host_password` | Django SMTP | SMTP authentication is enabled |
| `vault_google_oauth_client_id`, `vault_google_oauth_client_secret` | Single-tenant OAuth | Google OAuth is enabled |
| `vault_google_oauth_client_id_<prefix>`, `vault_google_oauth_client_secret_<prefix>` | Tenant OAuth | Per-tenant Google OAuth is enabled |
| `vault_smtp_password` | Postfix | Local SMTP auth is enabled |
| `vault_smtp_relay_username`, `vault_smtp_relay_password` | Postfix/mail role | External SMTP relay auth is enabled |
| `vault_m2s_api_key` | Mail synchronization | Mail sync is enabled |
| `vault_django_superuser_password_<prefix>` | GKE deployment | `gke_create_superuser: true`, once per tenant |
| `vault_postgresql_backup_passphrase` | PostgreSQL backup role | Encrypted GCS backups are enabled |

See the [GKE Vault example](../infrastructure/ansible/group_vars/gcp_app.vault.yml.example)
and [single-host Vault example](../infrastructure/ansible/group_vars/single_host.vault.yml.example)
for generation guidance.

## Review findings and known traps

These points are part of the configuration contract and should be checked when
changing deployment variables:

1. **Use `DB_*`, not `DATABASE_URL`.** The application settings do not parse
   `DATABASE_URL`; older multi-tenant examples using it are stale.
2. **Use the correct host allowlist name.** GKE settings read
   `DJANGO_ALLOWED_HOSTS`; single-host settings read `ALLOWED_HOSTS`. The
   single-host template emits both for compatibility.
3. **Production URL validation happens at import time.** Base settings require
   both `SITE_URL` and `CSRF_TRUSTED_ORIGINS` when debug is false. Single-host
   requires `SITE_URL` and derives CSRF origins from it if necessary.
4. **Email dev mode is a safety boundary.** GKE defaults it off, but the
   single-host env template defaults it to on when `email_dev_mode` is absent.
   Set it explicitly to `false` only after safe mail tests, and set a redirect
   address while testing.
5. **Keep import/export storage private.** `IMPORT_EXPORT_TMP_DIR` must be
   outside the public media root and must match the directory provisioned by
   the single-host role.
6. **Do not expose user media.** Keep `GS_DEFAULT_ACL=private`; public static
   assets should be separated from private uploads rather than making the
   shared bucket public.
7. **Generated `CLUB_NAME` and `MAIL_DOMAIN` are metadata today.** The GKE
   Secret template emits them, but the current Django settings modules do not
   read either variable. Treat them as reserved compatibility values, not as a
   substitute for `club_name`, `mail_domain`, or database-backed site config.
8. **Secret changes need a rollout.** Kubernetes secrets are consumed through
   `envFrom`; update the Secret and restart/roll out the workloads so all pods
   receive the new values.
9. **Single-host mail-list integration is incomplete.** The single-host
   settings module does not define `M2S_MAIL_API_KEY`, and `single-host.yml`
   does not deploy the `m2s-mail-sync` role. Enabling the optional Postfix mail
   roles therefore does not provide working M2S mailing-list synchronization.
10. **Single-host SMTP defaults are internally inconsistent.** The Ansible
    role emits `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and
    `EMAIL_HOST=localhost` even when `mail_server_enabled` is false. Unless an
    external SMTP host is configured, outbound mail attempts will fail against
    an absent localhost:25 service.
11. **Single-host SMTP timeout is not configurable.** GKE emits `EMAIL_TIMEOUT`
    and the base settings consume it; the single-host module does neither.
12. **Single-host HTTPS override variables are misleading.** The single-host
    module ignores `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, and
    `CSRF_COOKIE_SECURE` from `m2s_extra_env_vars`; use `SSL_ENABLED`/the NGINX
    proxy settings instead, or add explicit support before documenting those
    overrides.
13. **Generated single-host `.env` values are unquoted.** The template writes
    secrets directly and `manage.sh` sources the file as shell. Secret values
    containing shell metacharacters can be altered or cause command failures;
    use a shell-safe writer/quoting strategy before relying on generated
    secrets with arbitrary characters.
14. **Single-host database connection controls are incomplete.** The base/GKE
    settings support `DB_SSLMODE` and `DB_CONN_MAX_AGE`, but the single-host
    settings ignore both. This is harmless for the default local PostgreSQL
    topology, but prevents configuring TLS or persistent-connection lifetime
    when the database is moved to another host.

## Validation checklist

Before deploying a configuration change:

```bash
# From the repository root
.venv/bin/python manage.py check --settings=manage2soar.settings_single_host
.venv/bin/python manage.py makemigrations --check --settings=manage2soar.settings_single_host

# If a GKE-compatible environment is available, also validate the base module
.venv/bin/python manage.py check --settings=manage2soar.settings
.venv/bin/python manage.py makemigrations --check --settings=manage2soar.settings
```

Then run the Ansible preflight/check mode for the selected deployment and
inspect the rendered environment without publishing it. Never commit rendered
Kubernetes Secrets, `.env` files, service-account keys, or decrypted Vault
files.
