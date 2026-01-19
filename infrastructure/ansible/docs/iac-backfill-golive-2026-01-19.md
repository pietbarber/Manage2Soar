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
   git add infrastructure/ansible/group_vars/gcp_mail/vars.yml
   git commit -m "IaC backfill: Production go-live fixes (maillist-rewriter, firewall, docs)"
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
