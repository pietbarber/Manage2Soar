# OR-Tools Scheduler Rollback Procedure

## Overview

This document provides step-by-step procedures for rolling back from the OR-Tools scheduler to the legacy roster generation algorithm. Rollback is **safe, immediate, and non-destructive** - no data loss occurs.

**Issue Reference:** #642 - Phase 3: OR-Tools Django Integration with Feature Flag

## Rollback Characteristics

✅ **Safe:** Feature flag toggle, no database changes  
✅ **Immediate:** Takes effect on next roster generation (< 1 second)  
✅ **Non-Destructive:** No data loss, no schema changes  
✅ **Reversible:** Can re-enable OR-Tools at any time  
✅ **Zero Downtime:** Application stays online throughout rollback  

## When to Rollback

Consider rollback if you encounter:

1. **Performance Issues:**
   - Roster generation times exceed 30 seconds
   - Timeouts in production
   - Excessive memory usage

2. **Quality Issues:**
   - Fill rates significantly lower than legacy
   - Member complaints about unfair assignments
   - Constraint violations

3. **Technical Issues:**
   - OR-Tools import errors
   - Repeated automatic fallbacks
   - Crashes or exceptions

4. **Operational Issues:**
   - Rostermeister reports usability problems
   - Unexpected behavior in UI
   - Integration issues with other systems

## Rollback Methods

### Method 1: Django Admin (Recommended)

**Best for:** Planned rollbacks, non-emergency situations

**Steps:**

1. **Access Admin Interface:**
   ```
   https://manage2soar.example.com/admin/
   ```

2. **Navigate to Configuration:**
   - Click **"Site Configuration"** in left sidebar
   - Click **"Site configurations"**
   - Click your site configuration (usually only one entry)

3. **Disable OR-Tools:**
   - Scroll to **"Operations & Scheduling Settings"** section
   - **Uncheck** the box for **"Use OR-Tools scheduler"**
   - Optionally add a note in change log

4. **Save Changes:**
   - Click **"Save"** button at bottom of page
   - Verify success message appears

5. **Verify Rollback:**
   - Navigate to **Duty Roster → Propose Roster**
   - Generate a test roster for a future month
   - Check logs to confirm `scheduler_type: "legacy"`

**Time Required:** < 2 minutes

### Method 2: Django Shell

**Best for:** Programmatic rollback, scripting, emergency situations

**Steps:**

1. **Access Production Shell:**
   ```bash
   # Kubernetes
   kubectl exec -it <pod-name> -- bash

   # Or SSH if using single-host deployment
   ssh user@production-server
   cd /path/to/Manage2Soar
   ```

2. **Activate Virtual Environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Open Django Shell:**
   ```bash
   python manage.py shell
   ```

4. **Disable Flag:**
   ```python
   from siteconfig.models import SiteConfiguration

   # Get configuration
   config = SiteConfiguration.objects.first()

   # Verify current state
   print(f"Current setting: {config.use_ortools_scheduler}")
   # Should print: Current setting: True

   # Disable OR-Tools scheduler
   config.use_ortools_scheduler = False
   config.save()

   # Confirm change
   print(f"New setting: {config.use_ortools_scheduler}")
   # Should print: New setting: False

   # Exit shell
   exit()
   ```

5. **Verify Rollback:**
   ```bash
   # Check logs for next roster generation
   kubectl logs -f <pod-name> | grep "generate_roster"
   ```

   Expected log entry:
   ```json
   {
     "level": "info",
     "message": "Generating roster",
     "scheduler_type": "legacy",
     "year": 2026,
     "month": 6
   }
   ```

**Time Required:** < 5 minutes

### Method 3: Database Direct Update (Emergency Only)

**⚠️ WARNING:** Only use if admin and shell access are unavailable

**Best for:** Critical emergency when other methods fail

**Steps:**

1. **Access Database:**
   ```bash
   # GCP Cloud SQL
   gcloud sql connect <instance-name> --user=postgres

   # Or direct postgres client
   psql -h <host> -U <user> -d <database>
   ```

2. **Update Configuration:**
   ```sql
   -- View current setting
   SELECT id, use_ortools_scheduler FROM siteconfig_siteconfiguration;

   -- Disable OR-Tools scheduler
   UPDATE siteconfig_siteconfiguration
   SET use_ortools_scheduler = FALSE;

   -- Verify change
   SELECT id, use_ortools_scheduler FROM siteconfig_siteconfiguration;
   -- Should show use_ortools_scheduler = f (false)
   ```

3. **No restart required** - Django reads config on each request

**Time Required:** < 3 minutes

## Emergency Rollback Procedure

If production is experiencing critical issues:

### 🚨 Emergency Checklist

```bash
# 1. Quick status check (30 seconds)
kubectl logs <pod> --tail=20 | grep -E "error|exception|fallback"

# 2. Disable flag via shell (2 minutes)
kubectl exec -it <pod> -- bash -c "
source .venv/bin/activate && python manage.py shell <<EOF
from siteconfig.models import SiteConfiguration
config = SiteConfiguration.objects.first()
config.use_ortools_scheduler = False
config.save()
print('OR-Tools scheduler DISABLED')
EOF
"

# 3. Verify rollback (1 minute)
kubectl logs <pod> | tail -5

# 4. Test roster generation (2 minutes)
# Via UI: Navigate to /duty_roster/propose-roster/ and click "Roll"
```

**Total Emergency Rollback Time:** < 5 minutes

## Post-Rollback Actions

### Immediate (Within 1 Hour)

1. **Verify Legacy Scheduler Working:**
   - Generate test roster via UI
   - Verify successful completion
   - Check fill rates are acceptable

2. **Notify Stakeholders:**
   - Inform rostermeister of rollback
   - Notify tech team/on-call
   - Update status page if applicable

3. **Collect Diagnostics:**
   ```bash
   # Save recent logs for analysis
   kubectl logs <pod> --since=1h > rollback_logs_$(date +%Y%m%d_%H%M%S).log

   # Save configuration state
   python manage.py shell <<EOF
   from siteconfig.models import SiteConfiguration
   config = SiteConfiguration.objects.first()
   print(f"use_ortools_scheduler: {config.use_ortools_scheduler}")
   print(f"schedule_instructors: {config.schedule_instructors}")
   print(f"schedule_duty_officers: {config.schedule_duty_officers}")
   EOF
   ```

### Within 24 Hours

1. **Root Cause Analysis:**
   - Review collected logs
   - Identify failure pattern
   - Run `test_ortools_vs_legacy` in staging to reproduce
   - Document findings in issue tracker

2. **Bug Report:**
   - Create GitHub issue with:
     - Rollback reason
     - Log excerpts
     - Reproduction steps
     - Impact assessment
   - Tag as `priority: high` and `bug`

3. **Fix and Re-Test:**
   - Develop fix based on root cause
   - Test in staging environment
   - Run full E2E test suite
   - Document fix in PR

### Within 1 Week

1. **Retry OR-Tools Deployment:**
   - After fix is merged and deployed
   - Follow deployment guide carefully
   - Monitor closely during first use

2. **Update Runbook:**
   - Document specific issue encountered
   - Add to "Known Issues" section
   - Improve monitoring or alerts if needed

## Verification Checklist

After rollback, verify each item:

- [ ] `use_ortools_scheduler` flag is `False` in database
- [ ] Admin UI shows checkbox is **unchecked**
- [ ] Logs show `scheduler_type: "legacy"` on new roster generation
- [ ] Test roster generation succeeds
- [ ] No `ortools` import errors in logs
- [ ] Fill rates are acceptable (typically 80-95%)
- [ ] Rostermeister can generate rosters normally
- [ ] No user-facing errors

## Known Issues and Solutions

### Issue 1: Flag Shows Disabled But OR-Tools Still Used

**Symptom:** Logs show `scheduler_type: "ortools"` but flag is `False`

**Cause:** Django cache or stale config

**Solution:**
```bash
# Clear Django cache
python manage.py shell <<EOF
from django.core.cache import cache
cache.clear()
print('Cache cleared')
EOF

# Restart application (if load-balanced, rolling restart)
kubectl rollout restart deployment/manage2soar-django
```

### Issue 2: Rollback Doesn't Take Effect

**Symptom:** Flag changes but behavior unchanged

**Cause:** Multiple SiteConfiguration objects in database

**Solution:**
```python
from siteconfig.models import SiteConfiguration

# Check for multiple configs
configs = SiteConfiguration.objects.all()
print(f"Found {configs.count()} configurations")

# Disable OR-Tools on all configs
for config in configs:
    config.use_ortools_scheduler = False
    config.save()
    print(f"Disabled on config ID {config.id}")
```

### Issue 3: Can't Access Admin or Shell

**Symptom:** Admin UI unreachable, shell access fails

**Cause:** Application crash, network issue

**Solution:**
Use database direct update (Method 3):
```sql
UPDATE siteconfig_siteconfiguration
SET use_ortools_scheduler = FALSE;
```

## Re-Enabling OR-Tools After Rollback

When ready to re-enable after fixes:

1. **Verify Fix Deployed:**
   - Check that bug fix is merged and in production
   - Review deployment logs for successful rollout

2. **Test in Staging:**
   - Enable flag in staging
   - Run full E2E tests
   - Run `test_ortools_vs_legacy` comparison
   - Verify performance and quality

3. **Gradual Re-Enable:**
   - Start with single test month
   - Monitor closely for 24 hours
   - Fully enable if stable

4. **Monitor:**
   - Watch logs for first week
   - Track performance metrics
   - Collect user feedback

## Rollback History Log

Maintain a log of rollbacks to track patterns:

| Date | Time | By | Reason | Duration | Re-Enabled |
|------|------|--|----|----------|------------|
| 2026-01-20 | 14:30 UTC | ops-team | Timeout issues | 3 days | 2026-01-23 |
| ... | ... | ... | ... | ... | ... |

Example entry format:
```markdown
### Rollback 2026-01-20

**Initiated By:** ops-team  
**Reason:** Roster generation timing out after 30s for 100+ member clubs  
**Method Used:** Django Admin (Method 1)  
**Duration:** Flag disabled for 3 days while fix developed  
**Root Cause:** OR-Tools solver timeout too low (5s → 30s)  
**Fix:** PR #650 increased timeout and added progress logging  
**Re-Enabled:** 2026-01-23 after successful staging tests  
**Outcome:** Successful, no further issues  
```

## Automated Rollback (Future Enhancement)

Consider implementing automated rollback triggers:

```python
# Pseudo-code for future monitoring integration
def check_ortools_health():
    recent_failures = count_fallbacks(last_24_hours)
    avg_solve_time = get_avg_solve_time(last_100_rosters)

    if recent_failures > 5 or avg_solve_time > 30000:
        # Automatic rollback
        config = SiteConfiguration.objects.first()
        config.use_ortools_scheduler = False
        config.save()

        # Alert ops team
        send_alert("OR-Tools auto-rollback triggered", severity="high")
```

## Testing This Procedure

Periodically test rollback procedure in staging:

```bash
# Staging rollback drill (quarterly)
# 1. Enable OR-Tools in staging
# 2. Perform rollback using each method
# 3. Verify functionality
# 4. Document any issues
# 5. Update this procedure if needed
```

## Support and Escalation

- **L1 Support:** Use Method 1 (Django Admin)
- **L2 Support:** Use Method 2 (Django Shell)
- **L3 Support/DBA:** Use Method 3 (Database Direct)
- **Escalation:** GitHub Issue Tracker, tag `@ops-team`

## Related Documentation

- [OR-Tools Deployment Guide](ortools-deployment-guide.md)
- [CronJob Architecture](cronjob-architecture.md)
- [Dual-Path Routing Tests](../duty_roster/tests/test_dual_path_routing.py)

## Changelog

- **2026-01-15:** Initial rollback procedure created (Phase 3 Week 3)
