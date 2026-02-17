# OR-Tools Scheduler Deployment Guide

## Overview

This guide covers how to safely deploy and enable the OR-Tools constraint programming scheduler in production. The OR-Tools scheduler is a drop-in replacement for the legacy roster generation algorithm, offering improved schedule quality and fairness.

**Issue Reference:** #642 - Phase 3: OR-Tools Django Integration with Feature Flag

## Prerequisites

- OR-Tools library version 9.11+ installed (check `requirements.txt`)
- Database migrations applied (migration `0029_add_use_ortools_scheduler_flag`)
- Access to Django admin or production Django shell
- Monitoring/logging access to view scheduler selection logs

## Deployment Architecture

The OR-Tools integration uses a **dual-path architecture with automatic fallback**:

```
┌──────────────────────────────────┐
│  roster_generator.generate_roster()  │
└──────────┬───────────────────────┘
           │
           ├──► Check SiteConfiguration.use_ortools_scheduler flag
           │
       ┌───┴──────┐
       │   True   │   False
       │          │
       ▼          ▼
  OR-Tools    Legacy
  Scheduler   Scheduler
     │            │
     │ (on error) │
     └────────────┼──► Automatic fallback to legacy scheduler
                  │
                  ▼
            Generated Roster
```

**Key Safety Features:**
- Feature flag defaults to `False` (legacy scheduler)
- Automatic fallback if OR-Tools fails
- Structured logging for monitoring
- Zero downtime switching
- No schema changes to roster storage

## Step 1: Verify Installation

### 1.1 Check OR-Tools Installation

```bash
# SSH into production pod
kubectl exec -it <pod-name> -- bash

# Activate virtual environment and check OR-Tools
source .venv/bin/activate
python -c "from ortools.sat.python import cp_model; print('OR-Tools installed successfully')"
```

If this fails, reinstall dependencies:

```bash
pip install --upgrade -r requirements.txt
```

### 1.2 Verify Migration Applied

```bash
python manage.py showmigrations siteconfig
```

Look for:
```
[X] 0029_add_use_ortools_scheduler_flag
```

If not applied:

```bash
python manage.py migrate siteconfig
```

## Step 2: Test in Staging Environment

### 2.1 Enable Feature Flag in Staging

**Option A: Django Admin (Recommended)**

1. Log into staging admin: `https://staging.example.com/admin/`
2. Navigate to: **Site Configuration → Site configurations**
3. Click your site configuration
4. Scroll to **Operations & Scheduling Settings**
5. Check the box for **Use OR-Tools scheduler**
6. Save

**Option B: Django Shell**

```bash
kubectl exec -it <staging-pod> -- bash
source .venv/bin/activate
python manage.py shell
```

```python
from siteconfig.models import SiteConfiguration

config = SiteConfiguration.objects.first()
config.use_ortools_scheduler = True
config.save()
print(f"OR-Tools scheduler enabled: {config.use_ortools_scheduler}")
```

### 2.2 Generate Test Roster

1. Log in as rostermeister
2. Navigate to **Duty Roster → Propose Roster** or `/duty_roster/propose-roster/`
3. Select a future month (e.g., next month)
4. Click **"Roll"** button to generate roster
5. Verify:
   - Roster generates successfully
   - Slots are filled appropriately
   - No error messages appear

### 2.3 Monitor Logs

Check application logs for scheduler selection:

```bash
kubectl logs <staging-pod> | grep "generate_roster"
```

Expected log entries:

```json
{
  "level": "info",
  "message": "Generating roster",
  "scheduler_type": "ortools",
  "year": 2026,
  "month": 6,
  "num_days": 8,
  "excluded_dates": 0
}
{
  "level": "info",
  "message": "Roster generation complete",
  "scheduler_type": "ortools",
  "solve_time_ms": 1234,
  "year": 2026,
  "month": 6
}
```

**Key Fields:**
- `scheduler_type`: Should be `"ortools"` when flag is enabled
- `solve_time_ms`: Typical range 500-5000ms depending on problem size
- No `fallback_to_legacy` messages indicate OR-Tools is working correctly

### 2.4 Run Side-by-Side Comparison

Use the management command to compare OR-Tools vs legacy scheduler quality:

```bash
python manage.py test_ortools_vs_legacy \
    --year 2026 \
    --month 6 \
    --json > comparison_results.json
```

**Interpreting Results:**

```json
{
  "metadata": {
    "year": 2026,
    "month": 6,
    "comparison_time": "2026-01-15T10:45:00Z"
  },
  "legacy": {
    "solve_time_ms": 420,
    "fill_rate_percent": 87.5,
    "fairness_variance": 2.34
  },
  "ortools": {
    "solve_time_ms": 1250,
    "fill_rate_percent": 95.0,
    "fairness_variance": 0.87
  },
  "differences": {
    "changed_slots": 12,
    "changed_dates": 5
  }
}
```

**Acceptance Criteria:**
- OR-Tools `fill_rate_percent` ≥ legacy fill rate
- OR-Tools `fairness_variance` ≤ legacy fairness variance
- `solve_time_ms` < 10000ms (10 seconds)
- `changed_slots` variations are normal - schedulers use different algorithms

## Step 3: Production Deployment

### 3.1 Create Backup (Recommended)

Before enabling in production, backup the database:

```bash
# GCP Cloud SQL backup
gcloud sql backups create \
    --instance=<your-instance-name> \
    --description="Pre OR-Tools scheduler deployment"
```

### 3.2 Enable Feature Flag in Production

**Option A: Django Admin (Safest)**

1. Log into production admin: `https://manage2soar.example.com/admin/`
2. Navigate to: **Site Configuration → Site configurations**
3. Click your site configuration
4. Scroll to **Operations & Scheduling Settings**
5. Check the box for **Use OR-Tools scheduler**
6. **Important Notes:**
   - Help text: "Enable advanced OR-Tools constraint programming scheduler for roster generation..."
   - Default is unchecked (legacy scheduler)
   - Changes take effect immediately on next roster generation
7. Click **"Save"**

**Option B: Django Shell**

```bash
kubectl exec -it <production-pod> -- bash
source .venv/bin/activate
python manage.py shell
```

```python
from siteconfig.models import SiteConfiguration

config = SiteConfiguration.objects.first()
print(f"Current setting: {config.use_ortools_scheduler}")  # Should be False

config.use_ortools_scheduler = True
config.save()

print(f"New setting: {config.use_ortools_scheduler}")  # Should be True
```

### 3.3 Verify in Production

1. Generate a test roster for a future month (not current month)
2. Verify roster generates successfully
3. Check logs for `scheduler_type: ortools`
4. Monitor for any errors or fallback messages

### 3.4 Monitor for First Production Use

Watch logs during first real roster generation:

```bash
kubectl logs -f <production-pod> | grep -E "(generate_roster|roster_generator|ortools)"
```

Expected success indicators:
- `scheduler_type: "ortools"`
- `solve_time_ms` within normal range
- No `fallback_to_legacy` warnings
- No exceptions

## Step 4: Gradual Rollout Strategy (Optional)

For extra caution, consider a gradual rollout:

### Week 1: Shadow Mode
- Keep flag **disabled** in production
- Run `test_ortools_vs_legacy` command for each scheduled month
- Compare results manually before publishing rosters
- Build confidence in OR-Tools output quality

### Week 2: Single Month Test
- Enable flag for **one future month only**
- Generate and publish roster using OR-Tools
- Collect feedback from members and duty officers
- Monitor for issues

### Week 3: Full Enablement
- Enable flag for all roster generation
- Continue monitoring logs and feedback

## Step 5: Post-Deployment Monitoring

### 5.1 Key Metrics to Track

**Performance Metrics:**
- `solve_time_ms`: Should be < 10000ms
- `fill_rate_percent`: Should be ≥ 90% for typical clubs
- `fairness_variance`: Lower is better (< 2.0 is good)

**Error Metrics:**
- Fallback events: Should be zero
- Exceptions: Should be zero
- Member complaints: Track via support tickets

### 5.2 Log Monitoring

Set up alerts for:

```bash
# Alert if fallback to legacy occurs
kubectl logs <pod> | grep "fallback_to_legacy"

# Alert if solve time exceeds 10 seconds
kubectl logs <pod> | grep "solve_time_ms" | awk '{print $NF}' | awk -F: '{if($NF > 10000) print}'

# Alert if generation fails
kubectl logs <pod> | grep "roster generation failed"
```

### 5.3 Regular Comparison

Run monthly comparisons to ensure OR-Tools continues to outperform legacy:

```bash
# Add to cron or CronJob
python manage.py test_ortools_vs_legacy --year <year> --month <month> --json | \
    mail -s "OR-Tools Monthly Comparison" ops@example.com
```

## Troubleshooting

### Issue: Roster Generation Times Out

**Symptoms:** Solve time exceeds 30 seconds

**Solutions:**
1. Check problem size (# of members, # of days, # of roles)
2. Review member preferences for conflicts
3. Consider increasing OR-Tools solve timeout in `ortools_scheduler.py`
4. Temporarily disable flag and use legacy scheduler

### Issue: Lower Fill Rate Than Legacy

**Symptoms:** OR-Tools fills fewer slots than legacy

**Investigation:**
1. Run comparison command: `test_ortools_vs_legacy --verbose`
2. Check constraint violations in logs
3. Review member availability and preferences
4. Check for overly restrictive constraints

**Possible Causes:**
- Stricter fairness constraints preventing assignments
- Member blackout periods conflicting
- Insufficient qualified members for role

### Issue: Automatic Fallback Occurring

**Symptoms:** Logs show `fallback_to_legacy`

**Investigation:**
1. Check full exception in logs
2. Verify OR-Tools installation: `python -c "from ortools.sat.python import cp_model"`
3. Check for constraint conflicts
4. Review solve status in logs (INFEASIBLE, UNKNOWN, etc.)

**Actions:**
1. If installation issue: Reinstall OR-Tools
2. If constraint issue: Review and adjust in `ortools_scheduler.py`
3. If persistent: Disable flag and file bug report

### Issue: Different Slots Assigned

**Symptom:** OR-Tools assigns different members than legacy

**This is expected!** OR-Tools uses a different algorithm (constraint programming vs greedy heuristic). Both schedulers produce valid rosters; OR-Tools typically produces more balanced assignments.

**Verification:**
1. Verify all roles are filled
2. Verify fairness variance is lower
3. Verify no constraint violations
4. Collect member feedback on assignment quality

## Rollback Procedure

If issues arise, rollback is immediate and non-destructive. See [OR-Tools Rollback Procedure](ortools-rollback-procedure.md) for detailed steps.

**Quick Rollback:**

1. Django Admin → Site Configuration → **Uncheck "Use OR-Tools scheduler"**
2. Or via shell:
   ```python
   from siteconfig.models import SiteConfiguration
   config = SiteConfiguration.objects.first()
   config.use_ortools_scheduler = False
   config.save()
   ```
3. Verify: Next roster generation uses legacy scheduler (check logs)

## Performance Benchmarks

Typical solve times by problem size:

| Members | Days | Roles | Legacy (ms) | OR-Tools (ms) | Improvement |
|---------|------|-------|-------------|---------------|-------------|
| 20 | 8 | 4 | 350 | 800 | Better fairness |
| 50 | 8 | 4 | 420 | 1500 | Better fairness |
| 100 | 8 | 4 | 500 | 3200 | Better fairness |
| 150 | 8 | 4 | 580 | 5800 | Better fairness |

**Note:** OR-Tools may be slower but produces significantly better assignment fairness and fill rates.

## Support

- **Documentation:** `docs/ortools-rollback-procedure.md`
- **Code:** `duty_roster/ortools_scheduler.py`
- **Tests:** `duty_roster/tests/test_dual_path_routing.py`
- **Issue Tracker:** GitHub Issues #642

## Changelog

- **2026-01-15:** Initial deployment guide created (Phase 3 Week 3)
