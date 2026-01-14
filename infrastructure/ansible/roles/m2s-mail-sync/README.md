# M2S Mail Sync Role

This role syncs mailing list membership from the M2S Django API to Postfix virtual aliases and sender whitelists.

## Overview

- **Sync script**: `/opt/m2s-mail-sync/sync-aliases.py` (Python 3)
- **Configuration**: `/opt/m2s-mail-sync/config.yml` (contains API key)
- **Cron job**: Runs every 15 minutes as root
- **Log file**: `/var/log/m2s-sync.log`

## Dependencies

This role installs its own Python dependencies:
- `python3-requests` - For HTTP API calls to Django
- `python3-yaml` - For reading config.yml

**Why explicit dependencies?** This role can be run independently with `--tags sync` without requiring the `common` role to be executed first.

## Files Generated

1. **Postfix virtual aliases** (`/etc/postfix/virtual`)
   - Maps mailing list addresses to recipient emails
   - Format: `members@club.domain.com  alice@gmail.com,bob@yahoo.com,...`

2. **Postfix sender whitelist** (`/etc/postfix/sender_whitelist`)
   - Lists email addresses allowed to send to mailing lists
   - Format: `sender@email.com  OK`

3. **Rspamd per-club whitelists** (`/etc/rspamd/local.d/whitelists/{club}_whitelist.map`)
   - Per-club sender whitelists for spam bypass (requires SPF PASS)
   - Format: One email per line

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

# Development mode (optional)
dev_mode_enabled: false
dev_mode_redirect_to: ""
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
ansible-playbook playbooks/mail-server.yml --tags sync,mail
```

**Note**: The `mail` tag is included to ensure the role runs with proper context.

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

# Check sender whitelist
cat /etc/postfix/sender_whitelist

# Check Rspamd whitelists
ls -l /etc/rspamd/local.d/whitelists/
cat /etc/rspamd/local.d/whitelists/ssc_whitelist.map
```

## Security Notes

- Config file (`config.yml`) has mode `0600` to protect API key
- Sync script validates email addresses to prevent injection attacks
- Script runs as root (required for postmap and file permissions)
- Per-club whitelists provide tenant isolation (one club can't whitelist spammers for another)

## Testing

After deployment, verify:

1. **Script is executable**: `ls -l /opt/m2s-mail-sync/sync-aliases.py`
2. **Config has API key**: `sudo cat /opt/m2s-mail-sync/config.yml | grep auth_token`
3. **Cron job exists**: `sudo crontab -l | grep m2s-sync`
4. **Manual run works**: `sudo /opt/m2s-mail-sync/sync-aliases.py`
5. **Files updated**: `ls -lh /etc/postfix/virtual /etc/postfix/sender_whitelist`

## Integration

This role is part of the complete mail server setup:

1. **common** - Base packages and system setup
2. **postfix** - MTA configuration
3. **opendkim** - DKIM signing
4. **rspamd** - Spam filtering
5. **m2s-mail-sync** - Dynamic list updates (this role)

For the complete mail server deployment guide, see `infrastructure/README.md`.
