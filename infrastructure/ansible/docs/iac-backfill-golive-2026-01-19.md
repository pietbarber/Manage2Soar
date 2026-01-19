# IaC Backfill - Production Go-Live Fixes

## Overview
During the production go-live on 2026-01-19, several manual "hackety hack" fixes were applied to get the system operational. This document tracks those fixes and the corresponding IaC backfill to ensure they're properly codified in Ansible.

## 1. ✅ Debug Logging Removed
**Issue**: Temporary debug file `/tmp/maillist-rewriter-debug.log` created with 666 permissions for troubleshooting header rewriting.

**Security Risk**: World-writable file could be exploited, especially if symlinked.

**IaC Fix**: Removed all debug file logging from `roles/postfix/templates/maillist-rewriter.py.j2`. Script now only logs errors to stderr (captured by Postfix mail.log).

**Status**: ✅ Fixed in commit [TODO]

---

## 2. ✅ Maillist-Rewriter Process Documented
**Issue**: New maillist-rewriter content filter process running on mail server but not documented.

**Risk**: Undocumented processes make troubleshooting and handoffs difficult.

**IaC Fix**: Created comprehensive documentation at `infrastructure/ansible/docs/maillist-rewriter.md` covering:
- Architecture and how it works (pipe content filter, reverse-lookup logic)
- Deployment via Ansible
- Troubleshooting steps
- Security considerations
- Version history

**Status**: ✅ Fixed in commit [TODO]

---

## 3. ✅ Port 25 Firewall Rule
**Issue**: GCP firewall created manually with gcloud command:
```bash
gcloud compute firewall-rules create m2s-mail-allow-smtp \
  --allow tcp:25,tcp:587 \
  --source-ranges 0.0.0.0/0 \
  --target-tags m2s-mail,smtp-relay
```

**Risk**: Manual firewall changes aren't tracked in version control and could be lost during infrastructure rebuild.

**IaC Fix**:
- Firewall rule already exists in `roles/gcp-vm/tasks/main.yml` (creates `m2s-mail-allow-smtp` rule)
- Updated `group_vars/gcp_mail/vars.yml` to include `0.0.0.0/0` in `gcp_smtp_allowed_sources` with comment explaining port 25 is open for inbound mailing list mail while port 587 is restricted to GKE nodes

**Important Notes**:
- GCP firewall rule allows both 25 and 587 from all sources in the list
- UFW on the mail server provides additional layered protection
- Port 25: Open to internet for mailing list inbound mail
- Port 587: Effectively restricted by UFW to GKE cluster nodes only

**Status**: ✅ Fixed in commit [TODO]

**Verification**:
```bash
# Check GCP firewall rule
gcloud compute firewall-rules describe m2s-mail-allow-smtp --format=yaml

# Redeploy to verify Ansible creates correct rule
ansible-playbook -i inventory/gcp_mail.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-mail-server.yml \
  --tags gcp-provision
```

---

## 4. ✅ Postfix Configuration
**Issue**: Multiple modifications to Postfix configuration during troubleshooting:
- main.cf: `always_add_missing_headers = yes` (later found unnecessary due to reverse-lookup approach)
- master.cf: content_filter configuration for maillist-rewriter
- maillist-rewriter.py: Python script for header rewriting

**Risk**: Manual Postfix changes could be overwritten during redeploy.

**IaC Status**: ✅ All Postfix changes are already in Jinja2 templates:
- `roles/postfix/templates/main.cf.j2`
- `roles/postfix/templates/master.cf.j2`
- `roles/postfix/templates/maillist-rewriter.py.j2`

**Verification**: SSH to mail server and diff deployed files against templates:
```bash
ssh mail.manage2soar.com
diff /etc/postfix/main.cf <(ansible-playbook ... --check)
```

**Status**: ✅ Already in IaC (no backfill needed)

---

## 5. ✅ Django ALLOWED_HOSTS
**Issue**: Production domains (skylinesoaring.org, www.skylinesoaring.org) returned 400 Bad Request because `DJANGO_ALLOWED_HOSTS` was empty.

**Root Cause**: Manual kubectl patch was used during troubleshooting:
```bash
kubectl patch secret manage2soar-env-ssc -n tenant-ssc --type merge \
  -p '{"stringData":{"DJANGO_ALLOWED_HOSTS":"ssc.manage2soar.com,skylinesoaring.org,www.skylinesoaring.org"}}'
```

**IaC Status**: ✅ Already handled correctly in `roles/gke-deploy/templates/k8s-secrets.yml.j2`:
- Builds ALLOWED_HOSTS from tenant's `domains` list
- Supports both `domain` (string) and `domains` (array)
- Includes localhost, 127.0.0.1, and optional Gateway IP

**Configuration Location**: `inventory/gcp_app.yml`
```yaml
gke_tenants:
  - prefix: "ssc"
    name: "Skyline Soaring Club"
    domains:
      - "ssc.manage2soar.com"
      - "skylinesoaring.org"
      - "www.skylinesoaring.org"
```

**Proper Deployment**: Always use Ansible instead of manual kubectl patches:
```bash
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/gcp-app-deploy.yml \
  --limit ssc
```

**Why Manual Patch Failed**:
- First patch used wrong variable name: `ALLOWED_HOSTS` instead of `DJANGO_ALLOWED_HOSTS`
- Manual patches bypass version control and aren't reproducible
- Next Ansible deployment would overwrite manual changes

**Status**: ✅ Already in IaC (no backfill needed, but lesson learned: **always use Ansible for deployments**)

---

## 6. ⚠️ Let's Encrypt / Port 80 for Mail Server (Partially Complete)
**Issue**: Mail server (mail.manage2soar.com) was using self-signed TLS certificates for SMTP connections. While SMTP2Go relay worked fine (they handle TLS), proper TLS certificates improve email deliverability and avoid warnings in mail logs.

**Discovery**: Attempting to provision Let's Encrypt certificates required opening port 80 for HTTP-01 challenge validation. This was unexpected - most people think "mail server = port 25/587 only", but Let's Encrypt needs HTTP access to verify domain ownership.

**Manual Fix Attempted**:
```bash
# Create GCP firewall rule for Let's Encrypt
gcloud compute firewall-rules create m2s-mail-allow-http \
  --allow tcp:80 \
  --source-ranges 0.0.0.0/0 \
  --target-tags m2s-mail,smtp-relay \
  --project manage2soar

# Try to provision certificate
ssh mail.manage2soar.com
sudo certbot certonly --standalone \
  --email pb@pietbarber.com \
  --domains mail.manage2soar.com \
  --agree-tos
```

**Current Status**: ⚠️ Partially working
- GCP firewall rule created for port 80 (allows 0.0.0.0/0)
- Port connectivity issues persisted (possibly UFW or service binding conflicts)
- Mail server continues using self-signed certificates
- TLS warnings in logs but **not blocking mail flow** (SMTP2Go relay handles actual TLS for outbound mail)

**IaC Status**:
- ✅ GCP firewall rule manually created but **not yet in Ansible** (needs backfill)
- ⚠️ UFW configuration may need port 80 rule
- ⚠️ Certbot/Let's Encrypt setup not automated in Ansible
- ⚠️ Postfix TLS certificate configuration commented out in templates

**Why This Matters**:
- Self-signed certs cause TLS warnings in mail.log (cosmetic but concerning in audits)
- Some strict SMTP servers may reject connections with invalid certificates
- Let's Encrypt is free and automated, but requires HTTP-01 or DNS-01 challenge

**Possible Solutions**:
1. **HTTP-01 Challenge** (current approach - partially working):
   - Requires port 80 open to internet
   - certbot standalone mode temporarily binds port 80
   - May conflict with nginx/apache if running

2. **DNS-01 Challenge** (alternative - recommended):
   - Uses DNS TXT records instead of HTTP
   - No port 80 required
   - Requires Google Cloud DNS API access or manual TXT record updates
   - certbot-dns-google plugin available

3. **Self-Signed Acceptable** (current workaround):
   - Mail relay to SMTP2Go works fine with self-signed certs
   - SMTP2Go handles actual TLS for outbound delivery
   - Only affects direct SMTP connections to mail.manage2soar.com

**Recommended IaC Backfill**:
- Add GCP firewall rule for port 80 to `roles/gcp-vm/tasks/main.yml`
- Document decision: Use self-signed certs (simple) vs Let's Encrypt (better but complex)
- If Let's Encrypt desired: Add certbot role with DNS-01 challenge (more reliable than HTTP-01)

**Status**: ⚠️ Deferred (mail working with self-signed certs, low priority)

---

## 7. ✅ Multi-Domain Mail Support
**Issue**: Production domain (skylinesoaring.org) and its www subdomain needed to receive mailing list mail, requiring updates to multiple mail infrastructure components.

**Changes Required**:
1. **Postfix virtual_domains**: Accept mail for skylinesoaring.org and www.skylinesoaring.org (not just ssc.manage2soar.com)
2. **M2S sync script**: Handle clubs with multiple domains (domains array, not single domain string)
3. **Django API**: Return mailing list data for all configured domains

**IaC Status**: ✅ Already implemented in roles/templates

**Key Files**:
- `roles/postfix/templates/virtual_domains.j2`:
  ```jinja
  {% for club in club_domains %}
  {# Legacy format: club.prefix.mail_domain #}
  {{ club.prefix }}.{{ mail_domain }}    OK
  {# Additional domains (if configured) #}
  {% if club.domains is defined %}
  {% for domain in club.domains %}
  {{ domain }}    OK
  {% endfor %}
  {% endif %}
  {% endfor %}
  ```

- `roles/m2s-mail-sync/templates/sync-aliases.py.j2`:
  - Supports both `club.domain` (string) and `club.domains` (array) for backward compatibility
  - Line 373: `domains = club.get('domains', [club.get('domain')])`
  - Generates virtual aliases for each domain separately

- `roles/m2s-mail-sync/templates/sync-config.yml.j2`:
  ```yaml
  clubs:
    - prefix: "ssc"
      domains:
        - "ssc.manage2soar.com"
        - "skylinesoaring.org"
        - "www.skylinesoaring.org"
      api_url: "https://skylinesoaring.org/members/api/email-lists/"
  ```

**Configuration Location**: `group_vars/gcp_mail/vars.yml`
```yaml
club_domains:
  - prefix: "ssc"
    domains:
      - "ssc.manage2soar.com"
      - "skylinesoaring.org"
      - "www.skylinesoaring.org"
    api_url: "https://skylinesoaring.org/members/api/email-lists/"
    auth_token: "{{ m2s_api_key }}"
```

**Django API** (`members/api.py`):
- The `/members/api/email-lists/` endpoint returns list data agnostic of domain
- Mail sync script applies same lists to all domains configured for the club
- Example: `members@skylinesoaring.org` and `members@www.skylinesoaring.org` get identical subscriber lists

**Important Notes**:
- Multi-domain support is per-club (one club can have multiple domains)
- Each domain gets its own virtual alias entries
- Whitelist is shared across all domains for a club (not domain-specific)
- Backward compatible with single `domain` string (legacy config)

**Status**: ✅ Already in IaC (no backfill needed)

**Verification**:
```bash
# Check Postfix accepts mail for all domains
ssh mail.manage2soar.com 'sudo postmap -q skylinesoaring.org /etc/postfix/virtual_domains'
ssh mail.manage2soar.com 'sudo postmap -q www.skylinesoaring.org /etc/postfix/virtual_domains'

# Check virtual aliases generated for all domains
ssh mail.manage2soar.com 'sudo grep -A 2 "^members@skylinesoaring.org" /etc/postfix/virtual'

# Test mail delivery to production domain
echo "Test" | mail -s "Multi-domain test" members@skylinesoaring.org
```

---

## 8. ✅ SSL/TLS Policy (Disable TLS 1.0/1.1)
**Issue**: Production site (skylinesoaring.org) received SSL Labs grade B due to supporting insecure TLS 1.0 and TLS 1.1 protocols. Google Cloud Load Balancer (created by GKE Gateway) uses default SSL policy which allows TLS 1.0/1.1 for backward compatibility.

**Security Risk**: TLS 1.0 (1999) and TLS 1.1 (2006) have known vulnerabilities and are deprecated by all major browsers and security standards (PCI-DSS, NIST, etc.). Clients using these old protocols can be subject to downgrade attacks.

**Manual Fix Applied**:
```bash
# Create modern TLS policy (TLS 1.2+ only)
gcloud compute ssl-policies create modern-tls-policy \
  --profile MODERN \
  --min-tls-version 1.2 \
  --project manage2soar \
  --global

# Find Gateway's auto-generated target-https-proxy
gcloud compute target-https-proxies list \
  --filter="name~manage2soar-gateway" \
  --project manage2soar

# Attach SSL policy to target proxy
gcloud compute target-https-proxies update gkegw1-84of-default-manage2soar-gateway-8zychhgoas3u \
  --ssl-policy modern-tls-policy \
  --global \
  --project manage2soar
```

**IaC Fix**:
- Created `roles/gke-deploy/tasks/ssl-policy.yml` - Ansible tasks to:
  1. Create `modern-tls-policy` SSL policy if it doesn't exist
  2. Find the Gateway's auto-generated target-https-proxy name
  3. Attach SSL policy to the proxy (idempotent - only updates if needed)
- Updated `roles/gke-deploy/tasks/main.yml` to include SSL policy tasks after ingress deployment
- Added configuration variables to `inventory/gcp_app.yml`:
  ```yaml
  gke_ssl_policy_enabled: true
  gke_ssl_policy_name: "modern-tls-policy"
  gke_ssl_policy_profile: "MODERN"      # MODERN (TLS 1.2+) or RESTRICTED
  gke_ssl_policy_min_tls: "1.2"         # 1.2 or 1.3
  ```

**Important Notes**:
- Gateway API doesn't directly support SSL policies - they must be applied to the underlying GCP target-https-proxy
- Target proxy name is auto-generated by GKE (e.g., `gkegw1-84of-default-manage2soar-gateway-8zychhgoas3u`)
- Ansible task dynamically finds the proxy name by filtering on Gateway name
- SSL policy is shared across all Gateway listeners (all domains use the same TLS settings)
- **Expected SSL Labs Grade**: A (was B due to TLS 1.0/1.1 support)

**Status**: ✅ Fixed in commit [TODO]

**Verification**:
```bash
# Check SSL policy exists
gcloud compute ssl-policies describe modern-tls-policy --global --project=manage2soar

# Verify attached to target proxy
gcloud compute target-https-proxies describe <proxy-name> \
  --global \
  --project=manage2soar \
  --format="value(sslPolicy)"

# Test with SSL Labs
# https://www.ssllabs.com/ssltest/analyze.html?d=skylinesoaring.org
```

---

## Lessons Learned

### 1. Infrastructure as Code First Philosophy
**Always prefer IaC solutions over manual commands.** Manual fixes are acceptable during emergencies, but must be immediately backfilled into Ansible.

### 2. Two-Phase Approach
During production outages:
1. **Phase 1 (Emergency)**: Manual fix to restore service
2. **Phase 2 (Backfill)**: Codify fix in Ansible within 24 hours

### 3. Verification Checklist
After manual fixes:
- [ ] Document what was changed and why
- [ ] Identify which Ansible role/template needs updating
- [ ] Update the IaC (Jinja2 templates, group_vars, etc.)
- [ ] Test deployment in staging or against existing server
- [ ] Commit changes with detailed explanation
- [ ] Update runbooks/documentation

### 4. Security Review
Manual fixes often bypass security review. Always check:
- File permissions (avoid 666, 777)
- User/group ownership (prefer nobody, postfix over root)
- Firewall rules (least privilege principle)
- Temp files (avoid /tmp with world access)

---

## Next Steps

1. ✅ Remove debug log file from mail server:
   ```bash
   ssh mail.manage2soar.com 'test -f /tmp/maillist-rewriter-debug.log && sudo rm /tmp/maillist-rewriter-debug.log || echo "Already removed"'
   ```

2. ✅ Deploy updated maillist-rewriter.py (without debug logging):
   ```bash
   cd infrastructure/ansible
   ansible-playbook -i inventory/hosts.yml playbooks/mail-server.yml \
     --tags postfix \
     --vault-password-file ~/.ansible_vault_pass
   ```

3. ⚠️ **DO NOT redeploy GCP firewall** (rule is already correct from manual fix, but now codified)

4. ⚠️ **DO NOT redeploy Django secrets** (already correct from manual fix, template is already correct)

5. ✅ Commit all IaC changes to git:
   ```bash
   git add infrastructure/ansible/docs/maillist-rewriter.md
   git add infrastructure/ansible/docs/iac-backfill-golive-2026-01-19.md
   git add infrastructure/ansible/roles/postfix/templates/maillist-rewriter.py.j2
   git add infrastructure/ansible/roles/gke-deploy/tasks/ssl-policy.yml
   git add infrastructure/ansible/roles/gke-deploy/tasks/main.yml
   git add infrastructure/ansible/group_vars/gcp_mail/vars.yml
   git add infrastructure/ansible/inventory/gcp_app.yml
   git commit -m "IaC backfill: Production go-live fixes (maillist-rewriter, firewall, TLS policy, docs)"
   ```

---

## Verification Commands

### Mail Server
```bash
# Check maillist-rewriter script (should have no debug file logging)
ssh mail.manage2soar.com 'grep -c "debug_file" /usr/local/bin/maillist-rewriter.py || echo "0"'

# Check postfix configuration
ssh mail.manage2soar.com 'postconf content_filter'
ssh mail.manage2soar.com 'postconf -M | grep maillist-rewriter'

# Check firewall (GCP)
gcloud compute firewall-rules describe m2s-mail-allow-smtp

# Check firewall (UFW)
ssh mail.manage2soar.com 'sudo ufw status numbered'
```

### GKE Cluster
```bash
# Check DJANGO_ALLOWED_HOSTS
kubectl get secret manage2soar-env-ssc -n tenant-ssc \
  -o jsonpath='{.data.DJANGO_ALLOWED_HOSTS}' | base64 -d && echo

# Verify pods are using correct value
kubectl get pods -n tenant-ssc -l app=django-app-ssc -o name | head -1 | \
  xargs -I {} kubectl exec {} -n tenant-ssc -- printenv DJANGO_ALLOWED_HOSTS

# Check SSL policy
gcloud compute ssl-policies describe modern-tls-policy --global --project=manage2soar

# Find target proxy
gcloud compute target-https-proxies list \
  --filter="name~manage2soar" \
  --project=manage2soar

# Verify SSL policy attached
gcloud compute target-https-proxies describe <proxy-name> \
  --global \
  --project=manage2soar \
  | grep sslPolicy
```

### Test Mailing Lists
```bash
# Send test email to list
echo "Test message" | mail -s "Test from $(date +%Y-%m-%d)" webmaster@skylinesoaring.org

# Check mail.log for header rewriting
ssh mail.manage2soar.com 'sudo tail -20 /var/log/mail.log | grep "delivered via maillist-rewriter"'

# Verify From header in received email
# Should show: "Sender Name via Webmaster" <webmaster-bounces@skylinesoaring.org>
```

---

## Related Documentation
- [Maillist-Rewriter Documentation](maillist-rewriter.md)
- [GKE Post-Deployment Guide](gke-post-deployment.md)
- [GCP Mail Server Setup](../playbooks/gcp-mail-server.yml)
- [Production Go-Live Checklist](../../docs/pre-golive-checklist.md)
