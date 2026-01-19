# Mailman-Style Header Rewriter for Postfix

## Overview
The `maillist-rewriter.py` script is a Postfix content filter that rewrites email headers for mailing list messages in a Mailman-style format. This solves two critical problems:

1. **SMTP Relay Verification**: SMTP2Go and similar relays require verified sender domains. By rewriting the From header to use list-bounces@domain.com (which is verified), outbound emails are accepted.
2. **Bounce Management**: Bounces are routed to list-bounces@ addresses (which go to admins only), preventing bounce storms where bounce notifications would otherwise go back to the entire list.

## How It Works

### Architecture
- **Type**: Postfix pipe content filter
- **Location**: `/usr/local/bin/maillist-rewriter.py`
- **User**: `nobody` (unprivileged)
- **Trigger**: All inbound SMTP (port 25) and authenticated submission (port 587) traffic
- **Reinjection**: Port 10025 (bypasses content_filter to prevent loops)

### Header Rewriting Logic
1. Email arrives at mailing list address (e.g., `webmaster@skylinesoaring.org`)
2. Postfix expands virtual alias to individual recipients
3. Content filter examines recipients and **reverse-lookups** which list they belong to by reading `/etc/postfix/virtual`
4. If recipients match a known list, headers are rewritten:
   - **From**: `"Original Name via List Name" <list-bounces@domain.com>`
   - **Reply-To**: `original-sender@originaldomain.com` (preserved)
5. Email is reinjected to port 10025 for delivery

### Why Reverse Lookup?
Postfix's content_filter runs **after** virtual alias expansion, so the original list address is lost. The script reads `/etc/postfix/virtual` and matches the recipient set to find which list the email was sent to.

## Configuration

### Postfix Integration (master.cf)
```
# Port 25 and 587 use content filter
smtp      inet  n  -  y  -  -  smtpd
  -o content_filter=maillist-rewriter:dummy

submission inet n  -  y  -  -  smtpd
  -o content_filter=maillist-rewriter:dummy

# Pipe transport definition
maillist-rewriter unix  -  n  n  -  10  pipe
  flags=Rq user=nobody argv=/usr/local/bin/maillist-rewriter.py ${nexthop} ${sender} ${recipient}

# Reinjection port (no content filter to avoid loops)
127.0.0.1:10025 inet n  -  y  -  -  smtpd
  -o content_filter=
  -o receive_override_options=no_header_body_checks
```

### Mailing Lists Configured
The script is generated from the Jinja2 template with club domains and list names:
- members@domain
- instructors@domain
- towpilots@domain
- directors@domain
- board@domain
- private-owners@domain
- treasurer@domain
- webmaster@domain

### Bounce Routing
All `-bounces@` addresses route to `admin_email` (defined in `group_vars/all.yml`) to prevent bounce loops:
```
# Example from /etc/postfix/virtual
webmaster-bounces@skylinesoaring.org  pb@pietbarber.com
```

## Deployment

### Via Ansible
```bash
cd infrastructure/ansible
ansible-playbook -i inventory/hosts.yml playbooks/mail-server.yml \
  --tags postfix \
  --vault-password-file ~/.ansible_vault_pass
```

### Template Location
- **Template**: `roles/postfix/templates/maillist-rewriter.py.j2`
- **Deployed to**: `/usr/local/bin/maillist-rewriter.py`
- **Permissions**: 755 (readable/executable by postfix user)

## Troubleshooting

### Test the Script Manually
```bash
# SSH to mail server
ssh mail.manage2soar.com

# Send test email to list
echo "Subject: Test" | mail -s "Test" webmaster@skylinesoaring.org

# Check mail logs
sudo tail -f /var/log/mail.log | grep maillist-rewriter
```

### Check for Errors
```bash
# Look for reinjection failures
sudo grep "Reinject failed" /var/log/mail.log

# Check if filter is executing
sudo grep "delivered via maillist-rewriter service" /var/log/mail.log
```

### Verify Header Rewriting
1. Send email to list from external address
2. Check received email's headers:
   - **From** should be: `"Sender Name via List" <list-bounces@domain.com>`
   - **Reply-To** should be: original sender address

### Common Issues

**Headers not rewritten:**
- Verify `/etc/postfix/virtual` contains correct aliases
- Check recipients match virtual alias definition exactly
- Ensure MAILING_LISTS set in script includes the list address

**SMTP2Go rejections:**
- Verify sender domain is verified in SMTP2Go dashboard
- Check From header is using list-bounces@ address (should be skylinesoaring.org or ssc.manage2soar.com, not external domains)

**Bounce storms:**
- Verify `-bounces@` addresses route to admin only, not to list members
- Check `sync-aliases.py.j2` uses `{{ admin_email }}` for bounces aliases

## Security Considerations

- **User isolation**: Runs as `nobody` user, cannot modify system files
- **No temp files**: All processing in-memory, no 666 permission debug files
- **Injection protection**: Uses email.message parser, not string manipulation
- **Chroot**: Postfix chroot environment limits file access

## Related Documentation
- [Postfix Content Filter Documentation](http://www.postfix.org/FILTER_README.html)
- [Email Infrastructure Guide](../infrastructure/ansible/docs/gcp-mail-server.md)
- [Bounce Management](../docs/workflows/email-bounce-management.md)

## Version History
- **v1.0** (2026-01-19): Initial implementation with reverse-lookup logic
  - Mailman-style From rewriting
  - Reply-To preservation
  - Bounce routing to admins
  - Multi-domain support (ssc.manage2soar.com, skylinesoaring.org)
