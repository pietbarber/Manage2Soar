# IaC Backfill - Production Go-Live Fixes

## Overview
During the production go-live on 2026-01-19, several manual "hackety hack" fixes were applied to get the system operational. This document tracks those fixes and the corresponding IaC backfill to ensure they're properly codified in Ansible.

## Summary of Issues Documented

| # | Issue | Status | Priority |
|---|-------|--------|----------|
| 1 | Debug log file (666 permissions) | ✅ Fixed | Security |
| 2 | Maillist-rewriter undocumented | ✅ Fixed | Documentation |
| 3 | Port 25 firewall manual rule | ✅ Fixed | IaC completeness |
| 4 | Postfix configuration | ✅ Already in IaC | Verification |
| 5 | Django ALLOWED_HOSTS | ✅ Already in IaC | Lessons learned |
| 6 | Let's Encrypt/port 80 | ✅ Fixed | Low priority |
| 7 | Multi-domain mail support | ✅ Already in IaC | Verification |
| 8 | SSL/TLS policy (TLS 1.0/1.1) | ✅ Fixed | Security |
| 9 | EMAIL_DEV_MODE config | ✅ Fixed | **CRITICAL** |
| 10 | **Postfix TLS cert paths (BROKE MAIL)** | ✅ Fixed | **CRITICAL** |
| 11 | **Envelope sender not rewritten (BROKE LISTS)** | ✅ Fixed | **CRITICAL** |

**KEY TAKEAWAY**: Always use IaC first. Manual fixes create technical debt and risk. All manual changes should be immediately followed by IaC backfill and documentation.

---

## 1. ✅ Debug Logging Removed
**Issue**: Temporary debug file `/tmp/maillist-rewriter-debug.log` created with 666 permissions for troubleshooting header rewriting.

**Security Risk**: World-writable file could be exploited, especially if symlinked.

**IaC Fix**: Removed all debug file logging from `roles/postfix/templates/maillist-rewriter.py.j2`. Script now only logs errors to stderr (captured by Postfix mail.log).

**Status**: ✅ Fixed and applied via IaC

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

**Status**: ✅ Fixed and applied via IaC

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

**Status**: ✅ Fixed and applied via IaC

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

## 6. ✅ Let's Encrypt / Port 80 for Mail Server (IaC Complete)
**Issue**: Mail server (mail.manage2soar.com) was using self-signed TLS certificates for SMTP connections. While SMTP2Go relay worked fine (they handle TLS), proper TLS certificates improve email deliverability and avoid warnings in mail logs.

**Discovery**: Attempting to provision Let's Encrypt certificates required opening port 80 for HTTP-01 challenge validation. This was unexpected - most people think "mail server = port 25/587 only", but Let's Encrypt needs HTTP access to verify domain ownership.

**Manual Fix Applied (2026-01-19)**:
```bash
# Create GCP firewall rule for Let's Encrypt
gcloud compute firewall-rules create m2s-mail-allow-http \
  --allow tcp:80 \
  --source-ranges 0.0.0.0/0 \
  --target-tags m2s-mail,smtp-relay \
  --project manage2soar
```

**IaC Backfill (Issue #529, 2026-01-25)**:
- ✅ Added `gcp_enable_http_firewall` variable to `roles/gcp-vm/defaults/main.yml`
- ✅ Added HTTP firewall rule task to `roles/gcp-vm/tasks/main.yml`
- ✅ Enabled HTTP firewall for mail server in `group_vars/gcp_mail/vars.yml`

The HTTP firewall rule is now controlled by `gcp_enable_http_firewall: true` (default: false).
Mail servers with Let's Encrypt should enable this, other servers can leave it disabled.

**Current Status**: ✅ Fixed
- GCP firewall rule now in Ansible IaC
- Can be selectively enabled per-server via variable
- Mail server currently using self-signed certs (Let's Encrypt optional enhancement)

**Why Self-Signed Still OK**:
- SMTP2Go relay handles actual TLS for outbound delivery
- Inbound mail works fine with self-signed (most MTAs accept it)
- Only affects direct SMTP connections to mail.manage2soar.com

**Status**: ✅ Fixed - Port 80 firewall rule now in IaC

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

**Status**: ✅ Fixed and applied via IaC

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

## 9. ✅ CRITICAL: Email Dev Mode Configuration (Fixed)
**Issue**: EMAIL_DEV_MODE setting must be carefully managed to prevent accidental email redirection in production.

**Risk**: If `email_dev_mode: true` is deployed to production pods, ALL emails (including real member notifications) will be redirected to dev addresses, breaking production functionality.

**Resolution (Issue #529, 2026-01-25)**:

1. **Configuration Aligned**: Both `inventory/gcp_app.yml` and `group_vars/gcp_app/vars.yml` now have consistent settings:
   - SSC (production): `email_dev_mode: false`
   - MASA (testing): `email_dev_mode: true`

2. **Pre-Deployment Validation Added**: New Ansible task file `roles/gke-deploy/tasks/validate-config.yml` runs before any deployment and:
   - Validates `email_dev_mode: false` for production tenants
   - Validates `gke_django_debug: false` for production
   - Validates `ALLOWED_HOSTS` is properly configured
   - Provides clear error messages with remediation steps if validation fails

3. **New Default Variables**:
   - `gke_validate_email_config: true` - Enable/disable email validation
   - `gke_validate_security: true` - Enable/disable security validations
   - `gke_environment: "production"` - Environment type for validation rules

**How It Works**:
The validation runs at the START of the gke-deploy role, before any Docker builds or Kubernetes deployments.
If a production tenant has `email_dev_mode: true` (or undefined), deployment fails immediately with a clear error message.

**Current Configuration (Verified Correct)**:

```yaml
# inventory/gcp_app.yml
gke_tenants:
  - prefix: "ssc"
    email_dev_mode: false              # ✅ PRODUCTION: Send real emails
    email_dev_mode_redirect_to: ""

  - prefix: "masa"
    email_dev_mode: true               # ✅ DEV: Testing mode
    email_dev_mode_redirect_to: "masa-test@manage2soar.com"
```

**Verification Commands**:
```bash
# Check inventory configuration
grep -A 10 "prefix: \"ssc\"" infrastructure/ansible/inventory/gcp_app.yml | grep email_dev_mode
# Expected: email_dev_mode: false

# Check deployed pod environment variable
kubectl get secret manage2soar-env-ssc -n tenant-ssc -o jsonpath='{.data.EMAIL_DEV_MODE}' | base64 -d
# Expected: false
```

**Status**: ✅ Fixed - Configuration aligned + pre-deployment validation added

---

## 10. ✅ CRITICAL: Postfix TLS Certificate Paths (Broke Inbound Mail)
**Issue**: Postfix was configured to use non-existent Let's Encrypt certificates at `/etc/letsencrypt/live/mail.manage2soar.com/fullchain.pem`, causing TLS to fail and **blocking ALL inbound mail from Gmail and other major providers**.

**Discovery**: 2026-01-19 16:19 - User sent email to members@skylinesoaring.org from Gmail, never received. Mail logs showed:
```
postfix/smtpd[112504]: warning: cannot get RSA certificate from file "/etc/letsencrypt/live/mail.manage2soar.com/fullchain.pem": disabling TLS support
postfix/smtpd[112504]: connect from mail-lf1-f50.google.com[209.85.167.50]
postfix/smtpd[112504]: lost connection after STARTTLS from mail-lf1-f50.google.com[209.85.167.50]
```

**Root Cause**:
- Ansible template `roles/postfix/templates/main.cf.j2` had hardcoded Let's Encrypt paths
- Let's Encrypt setup was deferred (see issue #6), but template wasn't updated
- Self-signed certificates exist at `/etc/ssl/certs/ssl-cert-snakeoil.pem` but Postfix wasn't using them
- Gmail requires STARTTLS for delivery - when TLS fails, connection drops, mail rejected

**Impact**: 🔴 **CRITICAL** - Mailing lists completely broken, no inbound mail from Gmail, Outlook, or any provider requiring TLS

**Manual Fix Applied** (2026-01-19 16:45):
```bash
ssh mail.manage2soar.com 'sudo postconf -e "smtpd_tls_cert_file = /etc/ssl/certs/ssl-cert-snakeoil.pem" && \
  sudo postconf -e "smtpd_tls_key_file = /etc/ssl/private/ssl-cert-snakeoil.key" && \
  sudo postfix reload'
```

**IaC Fix**: Updated `roles/postfix/templates/main.cf.j2` to use self-signed certificates:
```jinja
# TLS SETTINGS - Uses self-signed certificates (Let's Encrypt deferred)
smtpd_tls_cert_file = /etc/ssl/certs/ssl-cert-snakeoil.pem
smtpd_tls_key_file = /etc/ssl/private/ssl-cert-snakeoil.key
smtpd_tls_security_level = may
```

**Related Issues**:
- Issue #6 documented Let's Encrypt deferral but didn't update Postfix template
- This created a "time bomb" - template referenced non-existent certificates
- Self-signed certs are acceptable for inbound SMTP (SMTP2Go handles outbound TLS)

**Important Notes**:
- Self-signed certs work fine for inbound SMTP with `security_level = may`
- Major mail providers (Gmail, Outlook) still accept connections with self-signed certs
- TLS warnings in mail.log are cosmetic - mail flow works correctly
- When Let's Encrypt is implemented via IaC, update paths back to `/etc/letsencrypt/live/...`

**Status**: ✅ Fixed and applied via IaC

**Verification**:
```bash
# Check Postfix is using correct cert paths
ssh mail.manage2soar.com 'sudo postconf | grep "^smtpd_tls_cert_file\|^smtpd_tls_key_file"'
# Expected output:
# smtpd_tls_cert_file = /etc/ssl/certs/ssl-cert-snakeoil.pem
# smtpd_tls_key_file = /etc/ssl/private/ssl-cert-snakeoil.key

# Test inbound mail delivery
echo "Test from $(date)" | mail -s "TLS test" members@skylinesoaring.org

# Check mail.log for successful TLS connection (should NOT see "lost connection after STARTTLS")
ssh mail.manage2soar.com 'sudo tail -20 /var/log/mail.log | grep -i starttls'
```

---

## 11. ✅ CRITICAL: Maillist-Rewriter Envelope Sender Not Rewritten
**Issue**: The maillist-rewriter script was rewriting the From **header** to `webmaster-bounces@skylinesoaring.org`, but **NOT** rewriting the envelope sender (MAIL FROM), which remained as the original sender (e.g., `pb@pietbarber.com`). SMTP2Go checks **both** the envelope sender AND the From header domain for verification, causing all mailing list emails to be rejected.

**Discovery**: 2026-01-19 17:01 - Email to members@skylinesoaring.org was accepted by mail server and processed by maillist-rewriter, but SMTP2Go rejected ALL 101 recipients:
```
postfix/smtp[113291]: 4A669425AD: to=<imran.akram@gmail.com>, relay=mail.smtp2go.com[45.79.71.155]:587,
  delay=123, dsn=5.0.0, status=bounced (host mail.smtp2go.com[45.79.71.155] said:
  550-From header sender domain not verified (pietbarber.com)
  550-On your Sending > Verified Senders page
  550 verify the sender domain or email to be allowed to send. (in reply to end of DATA command))
```

**Root Cause**:
- Script was calling `smtp.sendmail(sender, recipients, msg.as_bytes())` where `sender` was the original envelope sender
- From **header** was correctly rewritten to `Piet Barber via Members <members-bounces@skylinesoaring.org>`
- But envelope sender (MAIL FROM) was still `pb@pietbarber.com`
- SMTP2Go verified senders checks envelope sender domain, not just From header
- Since `pietbarber.com` wasn't verified in SMTP2Go, all emails were rejected

**Impact**: 🔴 **CRITICAL** - ALL mailing list emails rejected by SMTP2Go, completely breaking list functionality

**Manual Fix Applied** (2026-01-19 17:14):
```bash
ssh mail.manage2soar.com "sudo sed -i.bak 's/smtp.sendmail(sender, recipients, msg.as_bytes())/# Use rewritten From header as envelope sender\n        from_header = msg.get(\"From\", \"\")\n        _, envelope_sender = parseaddr(from_header)\n        smtp.sendmail(envelope_sender, recipients, msg.as_bytes())/' /usr/local/bin/maillist-rewriter.py"
```

**IaC Fix**: Updated `roles/postfix/templates/maillist-rewriter.py.j2`:
```python
# Reinject to port 10025 (bypasses content_filter)
# CRITICAL: Use rewritten From header as envelope sender for SMTP2Go verification
# SMTP2Go checks both envelope sender AND From header domain
try:
    smtp = smtplib.SMTP('127.0.0.1', 10025)
    # Extract envelope sender from rewritten From header
    from_header = msg.get("From", "")
    _, envelope_sender = parseaddr(from_header)
    smtp.sendmail(envelope_sender, recipients, msg.as_bytes())
    smtp.quit()
    sys.exit(0)
```

**Important Notes**:
- The envelope sender (MAIL FROM) is different from the From header
- SMTP relay services like SMTP2Go, SendGrid, Mailgun check **envelope sender domain** for verification
- The fix extracts the email address from the rewritten From header (`members-bounces@skylinesoaring.org`) and uses it as the envelope sender
- This ensures both the header From and envelope MAIL FROM match the verified domain

**Status**: ✅ Fixed and applied via IaC

**Verification** (2026-01-19 17:15):
```bash
# Sent test email to webmaster@skylinesoaring.org
# Logs show successful reinjection with rewritten envelope sender:
postfix/qmgr[113244]: 52005425AC: from=<webmaster-bounces@ssc.manage2soar.com>, size=5809, nrcpt=4 (queue active)
postfix/smtp[114034]: 52005425AC: to=<bclarkfairfax@gmail.com>, relay=mail.smtp2go.com[45.79.170.99]:587,
  delay=0.81, dsn=2.0.0, status=sent (250 OK id=1vhsr7-FnQW0hPugdQ-KFqD)

# ✅ SMTP2Go accepted! All 4 recipients delivered successfully.
```

**Testing**:
```bash
# Send test email from external address (not gmail/same domain to avoid suppression)
echo "Test message from $(date)" | mail -s "Envelope sender test" webmaster@skylinesoaring.org

# Check mail.log for envelope sender
ssh mail.manage2soar.com 'sudo tail -30 /var/log/mail.log | grep "from=<webmaster-bounces"'

# Verify SMTP2Go accepted
ssh mail.manage2soar.com 'sudo tail -30 /var/log/mail.log | grep "status=sent"'
```

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
   git add infrastructure/ansible/roles/postfix/templates/main.cf.j2
   git add infrastructure/ansible/roles/gke-deploy/tasks/ssl-policy.yml
   git add infrastructure/ansible/roles/gke-deploy/tasks/main.yml
   git add infrastructure/ansible/group_vars/gcp_mail/vars.yml
   git add infrastructure/ansible/inventory/gcp_app.yml
   git commit -m "IaC backfill: Production go-live fixes (11 issues documented)

- Removes insecure debug logging from maillist-rewriter (666 permissions)
- Documents maillist-rewriter architecture and troubleshooting
- Adds port 25 firewall documentation for inbound mailing lists
- Verifies multi-domain mail support (virtual_domains, sync script, API)
- Creates SSL policy automation (modern-tls-policy, TLS 1.2+ only)
- Documents Let's Encrypt/port 80 challenge experience (deferred)
- **CRITICAL**: Documents EMAIL_DEV_MODE configuration conflicts and validation needs
- **CRITICAL**: Fixes Postfix TLS cert paths (was blocking ALL inbound mail from Gmail)
- **CRITICAL**: Fixes maillist-rewriter envelope sender (was blocking ALL list emails via SMTP2Go)
- Complete IaC backfill notes with 11 sections and lessons learned

See infrastructure/ansible/docs/iac-backfill-golive-2026-01-19.md for details."
   ```

6. ⚠️ **CRITICAL: Verify EMAIL_DEV_MODE before next deployment**:
   ```bash
   # Check production tenant configuration
   grep -A 10 "prefix: \"ssc\"" infrastructure/ansible/inventory/gcp_app.yml | grep email_dev_mode
   # MUST show: email_dev_mode: false

   # After deployment, verify pod environment
   kubectl get secret manage2soar-env-ssc -n tenant-ssc -o jsonpath='{.data.EMAIL_DEV_MODE}' | base64 -d
   # MUST show: false
   ```

---

## 12. ✅ CRITICAL: From Header Domain Preservation (Cosmetic but Confusing)
**Issue**: Maillist-rewriter was using wrong domain in rewritten From headers. Emails sent to `webmaster@skylinesoaring.org` were rewritten to `webmaster-bounces@ssc.manage2soar.com` instead of preserving the `@skylinesoaring.org` domain. This confused recipients seeing the staging domain in production emails.

**Discovery**: 2026-01-19 17:33 - User sent test email to `webmaster@skylinesoaring.org`, received with From: "Piet Barber via Webmaster <webmaster-bounces@ssc.manage2soar.com>" but expected `@skylinesoaring.org`.

**Root Cause**:
- Content filters don't receive `X-Original-To` header (added later in mail flow)
- Script fell back to reverse-lookup in `/etc/postfix/virtual`
- Virtual file had `webmaster@ssc.manage2soar.com` listed BEFORE `webmaster@skylinesoaring.org`
- Reverse-lookup found first match (ssc.manage2soar.com) and used that domain

**Manual Fix Applied** (2026-01-19 17:38):
1. Verified content filter doesn't receive `X-Original-To` with debug logging
   ```bash
   # Added debug logging to see headers
   sudo sed -i '/original_to = msg.get/a\    sys.stderr.write(f"DEBUG Headers: To={msg.get(\"To\")}, X-Original-To={msg.get(\"X-Original-To\")}, Delivered-To={msg.get(\"Delivered-To\")}\\n")' /usr/local/bin/maillist-rewriter.py

   # Sent test email, confirmed: X-Original-To=None
   ```

2. Discovered `To` header IS available: `To=Skyline Soaring Webmaster <webmaster@skylinesoaring.org>`

**IaC Fix** (2026-01-19 17:38):
Updated `infrastructure/ansible/roles/postfix/templates/maillist-rewriter.py.j2`:

```python
# Before: Only checked X-Original-To (which content filters don't receive)
original_to = msg.get('X-Original-To') or msg.get('Delivered-To')
if not original_to:
    original_to = find_list_from_recipients(recipients)

# After: Check To header first (reliable for content filters)
original_to = None

# Try To header first (most reliable for content filters)
to_header = msg.get('To')
if to_header:
    _, to_addr = parseaddr(to_header)
    if to_addr and to_addr.lower() in MAILING_LISTS:
        original_to = to_addr.lower()

# Extract preferred domain from To header for fallback
preferred_domain = None
if to_header:
    _, to_addr = parseaddr(to_header)
    if to_addr and '@' in to_addr:
        preferred_domain = to_addr.split('@')[1]

if not original_to:
    # Fallback with domain preference
    original_to = find_list_from_recipients(recipients, preferred_domain)
```

Updated `find_list_from_recipients()` to accept and prioritize `preferred_domain`:
```python
def find_list_from_recipients(recipients, preferred_domain=None):
    # ... find all matches ...
    matches = []
    for list_addr in MAILING_LISTS:
        # ... check if recipients match ...
        if set(recipients) == set(alias_recipients):
            matches.append(list_addr)

    # Prefer matches with preferred_domain
    if preferred_domain and matches:
        for match in matches:
            if match.endswith('@' + preferred_domain):
                return match

    return matches[0] if matches else None
```

**Verification** (2026-01-19 17:38):
```bash
# Deploy updated script
cd infrastructure/ansible
ansible-playbook -i inventory/hosts.yml \
  --vault-password-file ~/.ansible_vault_pass \
  playbooks/mail-server.yml --tags postfix

# Test email sent to webmaster@skylinesoaring.org
# Mail log shows:
from=<webmaster-bounces@skylinesoaring.org>  # ✅ Correct domain!

# Previously showed:
from=<webmaster-bounces@ssc.manage2soar.com>  # ❌ Wrong domain
```

**Impact**:
- **Before**: Production emails showed staging domain (@ssc.manage2soar.com) - confusing for recipients
- **After**: Emails preserve the original domain (@skylinesoaring.org) - clear and professional
- **Technical**: Envelope sender and From header now match the original To address domain

**Files Modified**:
- `infrastructure/ansible/roles/postfix/templates/maillist-rewriter.py.j2` (IaC fix)

**Status**: ✅ Fixed in IaC, deployed, tested and verified working

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
