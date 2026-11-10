# M2S Mail Sync Role

This role syncs mailing list membership from the M2S Django API to Postfix virtual aliases and tenant-scoped sender whitelists.

Administrators with Webmaster access can also create **Email Aliases** in
Django Admin (`Site Configuration → Email Aliases`).
Each enabled alias forwards an individual address such as `admin@club.org`
to one external mailbox without adding it to a mailing list or the sender
whitelist. External senders can use these aliases; regular mail/spam checks
still apply. A destination on the club's domain is rejected to prevent loops.
The API exposes these under `forwarding_aliases`; the sync writes them to the
virtual map after list addresses. In dev mode, both list and direct aliases
redirect to the configured test inbox instead of their real targets.
Disabling or deleting an alias removes it at the next sync (within about one minute).

## Overview

- **Sync script**: `/opt/m2s-mail-sync/sync-aliases.py` (Python 3)
- **Configuration**: `/opt/m2s-mail-sync/config.yml` (contains API key)
- **Cron job**: Runs every minute as root
- **Log file**: `/var/log/m2s-sync.log`

## Dependencies

This role installs its own Python dependencies:
- `python3-requests` - For HTTP API calls to Django
- `python3-yaml` - For reading config.yml

**Why explicit dependencies?** This role is tagged as both `sync` and `mail`, and can be run independently of the `common` role. Using `--tags sync` will run only this sync role, while `--tags sync,mail` will also execute other mail server roles such as Postfix, OpenDKIM, and Rspamd.

## Files Generated

1. **Postfix virtual aliases** (`/etc/postfix/virtual`)
   - Maps mailing list addresses to recipient emails
   - Format: `members@club.domain.com  alice@gmail.com,bob@yahoo.com,...`

2. **Postfix tenant sender whitelists** (`/etc/postfix/tenant-whitelists/{club}_whitelist`)
   - Lists email addresses allowed to send to that tenant's mailing lists
   - Format: `sender@email.com  OK`

3. **Rspamd per-club whitelists** (`/etc/rspamd/local.d/whitelists/{club}_whitelist.map`)
   - Per-club sender whitelists for spam bypass (requires SPF PASS)
   - Format: One email per line

4. **Protected-list SPF map** (`/etc/rspamd/local.d/whitelists/protected_lists.map`)
   - Requires SPF PASS for public mail to every mailing list, including bypass lists
   - Authenticated submission is exempt

## Configuration Variables

Required variables (set in `group_vars/all.yml`):

```yaml
# M2S API authentication
m2s_api_key: "your-secret-api-key"

# Mail server settings
mail_hostname: "mail.manage2soar.com"
mail_domain: "manage2soar.com"
postfix_config_dir: "/etc/postfix"
m2s_sync_dir: "/opt/m2s-mail-sync"

# Club domains (array)
club_domains:
  - prefix: "ssc"
    name: "Skyline Soaring Club"
    api_url: "https://ssc.manage2soar.com/api/email-lists/"
    auth_token: "{{ m2s_api_key }}"  # Optional: per-club token

# Development mode (optional; comma-separated addresses are supported)
dev_mode_enabled: false
dev_mode_redirect_to: "developer@example.com"
```

## Development Mode

To prevent accidentally emailing real members during testing, enable dev mode:

```yaml
dev_mode_enabled: true
dev_mode_redirect_to: "developer@example.com"
```

All mailing list recipients will be redirected to the specified address.

## Running Independently

To update only the sync configuration without touching Postfix/OpenDKIM/Rspamd:

```bash
ansible-playbook playbooks/mail-server.yml --tags sync
```

This runs only the m2s-mail-sync role tasks without modifying Postfix, OpenDKIM, or Rspamd configurations.

## Troubleshooting

### Sync script failing

Check the log:
```bash
tail -f /var/log/m2s-sync.log
```

Common issues:
- **ModuleNotFoundError**: Python packages not installed (this role should handle it)
- **401 Unauthorized**: API key mismatch between config.yml and Django settings
- **Connection timeout**: Django API not reachable from mail server
- **Empty lists**: No active members in database

### Manual sync

Run the script manually to see output:
```bash
/opt/m2s-mail-sync/sync-aliases.py
```

### Verify generated files

```bash
# Check virtual aliases
cat /etc/postfix/virtual

# Check the tenant sender whitelist
cat /etc/postfix/tenant-whitelists/ssc_whitelist

# Check Rspamd whitelists
ls -l /etc/rspamd/local.d/whitelists/
cat /etc/rspamd/local.d/whitelists/ssc_whitelist.map
```

## Security Notes

- Config file (`config.yml`) has mode `0600` to protect API key
- Sync script validates email addresses to prevent injection attacks
- Script runs as root (required for postmap and file permissions)
- Postfix authorization maps are tenant-scoped (one club cannot authorize senders for another club's lists)
- API URLs must use HTTPS; only localhost HTTP endpoints are allowed for development
- Generated member-address maps are readable only by the mail service accounts

## Testing

After deployment, verify:

1. **Script is executable**: `ls -l /opt/m2s-mail-sync/sync-aliases.py`
2. **Config has API key**: `sudo cat /opt/m2s-mail-sync/config.yml | grep auth_token`
3. **Cron job exists**: `sudo crontab -l | grep m2s-sync`
4. **Manual run works**: `sudo /opt/m2s-mail-sync/sync-aliases.py`
5. **Files updated**: `ls -lh /etc/postfix/virtual /etc/postfix/tenant-whitelists/`

## Integration

This role is part of the complete mail server setup:

1. **common** - Base packages and system setup
2. **postfix** - MTA configuration
3. **opendkim** - DKIM signing
4. **rspamd** - Spam filtering
5. **m2s-mail-sync** - Dynamic list updates (this role)

For the complete mail server deployment guide, see `infrastructure/README.md`.
