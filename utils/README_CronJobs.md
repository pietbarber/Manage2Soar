# Kubernetes CronJob System for Manage2Soar

## Overview
This directory contains a distributed CronJob system that runs scheduled tasks across multiple Kubernetes pods with database-level locking to prevent race conditions and duplicate execution.

## Architecture

### Distributed Locking
- **CronJobLock Model**: PostgreSQL-based locking using unique constraints
- **Pod Identification**: Each pod identified by hostname for debugging
- **Lock Expiration**: Automatic cleanup of stale locks (24-hour expiration)
- **Graceful Failures**: Commands handle database connectivity issues gracefully

### Base Command Framework
All CronJob commands inherit from `BaseCronJobCommand` which provides:
- ✅ Distributed locking mechanism
- ✅ Structured logging with emojis
- ✅ Dry-run support for testing
- ✅ Database failure handling
- ✅ Performance timing
- ✅ Graceful shutdown handling

## Scheduled Commands

### Daily Commands

#### `notify_aging_logsheets` (8:00 AM UTC)
- **Purpose**: Notify duty officers about logsheets 7+ days old and not finalized
- **Recipients**: Current duty officer
- **Frequency**: Daily
- **Timeout**: 15 minutes
- **Testing**: Found 1 aging logsheet in production data

#### `send_duty_preop_emails` (6:00 AM UTC)
- **Purpose**: Send pre-operation emails to duty officers for next day
- **Recipients**: Tomorrow's duty officers
- **Frequency**: Daily
- **Timeout**: 10 minutes
- **Note**: Existing command, converted to use new framework

#### `expire_ad_hoc_days` (6:00 PM UTC)
- **Purpose**: Expire temporary duty assignments for tomorrow
- **Target**: Ad-hoc duty slots
- **Frequency**: Daily
- **Timeout**: 5 minutes
- **Note**: Existing command, converted to use new framework

### Weekly Commands

#### `notify_late_sprs` (Monday 10:00 AM UTC)
- **Purpose**: Escalating notifications for overdue Student Progress Reports
- **Escalation Levels**:
  - 7 days: Friendly reminder
  - 14 days: Gentle nudge with supervisor CC
  - 21 days: Firm reminder with chief instructor CC
  - 25 days: Urgent notice with board CC
  - 30+ days: FINAL notice with all leadership CC
- **Recipients**: Flight instructors, escalates to leadership
- **Frequency**: Weekly
- **Timeout**: 20 minutes
- **Testing**: Found 1 FINAL level overdue SPR in production data

#### `send_maintenance_digest` (Sunday 9:00 AM UTC)
- **Purpose**: Weekly maintenance status digest
- **Recipients**: Maintenance team
- **Frequency**: Weekly (Sunday)
- **Timeout**: 10 minutes
- **Note**: Existing command, uses new framework

### Monthly Commands

#### `report_duty_delinquents` (1st of month 7:00 AM UTC)
- **Purpose**: Report actively flying members not performing duty obligations
- **Analysis**: Cross-correlates flight activity with duty participation
- **Recipients**: Board and duty officers
- **Frequency**: Monthly (1st of month)
- **Timeout**: 30 minutes
- **Testing**: Found 19 delinquent members in production data
- **Parameters**:
  - `--lookback-months=12`: Flight activity window (default: 12)
  - `--min-flights=1`: Minimum flights to be considered active (default: 1)

## Deployment

### Apply CronJobs
```bash
kubectl apply -f k8s-cronjobs.yaml
```

### View CronJobs
```bash
kubectl get cronjobs
kubectl describe cronjob notify-aging-logsheets
```

### View Job History
```bash
kubectl get jobs
kubectl logs job/notify-aging-logsheets-1234567890
```

### Manual Execution
```bash
kubectl create job --from=cronjob/notify-aging-logsheets manual-test-$(date +%s)
```

## Configuration

### Environment Variables
All CronJobs use the `manage2soar-env` secret which should contain:
- `DATABASE_URL`: PostgreSQL connection string
- `EMAIL_HOST_USER`: SMTP username
- `EMAIL_HOST_PASSWORD`: SMTP password
- `SECRET_KEY`: Django secret key
- `GOOGLE_APPLICATION_CREDENTIALS`: Set to `/app/skyline-soaring-storage.json`

### Resources
- **Light Commands** (notifications, emails): 64Mi RAM, 50m CPU
- **Heavy Commands** (analysis, reports): 128-256Mi RAM, 100-200m CPU

### Security
- Uses Google Cloud service account for storage access
- Secrets mounted as volumes (not environment variables)
- No privileged containers
- Resource limits enforced

## Testing

### Local Testing
```bash
# Test with dry-run to avoid side effects
python manage.py notify_aging_logsheets --dry-run --verbosity=2
python manage.py notify_late_sprs --dry-run --verbosity=2
python manage.py report_duty_delinquents --dry-run --verbosity=2

# Test with actual execution (be careful!)
python manage.py notify_aging_logsheets --verbosity=2
```

### Production Validation
All commands have been tested with production data:
- ✅ Database connectivity working (34.66.12.127)
- ✅ Real data queries returning expected results
- ✅ Email/notification creation functioning
- ✅ Distributed locking preventing race conditions
- ✅ Error handling for database failures

## Monitoring

### Health Checks
- Monitor CronJob success/failure history
- Check for stuck jobs (activeDeadlineSeconds)
- Watch for lock contention in database
- Monitor resource usage

### Logging
All commands use structured logging:
```
🔒 [notify_aging_logsheets] Acquired lock for pod: skylinesoaring-deployment-abc123
📊 [notify_aging_logsheets] Found 1 aging logsheets requiring notification
📧 [notify_aging_logsheets] Sent notification to duty officer: John Doe
✅ [notify_aging_logsheets] Command completed successfully in 2.34s
🔓 [notify_aging_logsheets] Released lock
```

### Alerts
Set up monitoring for:
- Failed CronJob executions
- Long-running jobs approaching timeout
- Database lock contention
- Email delivery failures

## Troubleshooting

### Common Issues

#### CronJob Not Starting
```bash
kubectl describe cronjob <name>
kubectl get events --field-selector involvedObject.name=<cronjob-name>
```

#### Job Failing
```bash
kubectl logs job/<job-name>
kubectl describe job <job-name>
```

#### Database Lock Issues
```bash
# Check for stale locks
python manage.py shell
>>> from utils.models import CronJobLock
>>> CronJobLock.objects.all()
```

#### Email Not Sending
- Check SMTP credentials in secret
- Verify email settings in Django settings
- Test with `--dry-run` to see what would be sent

### Performance
- **Aging Logsheets**: ~2-5s execution time
- **Late SPRs**: ~5-15s execution time  
- **Duty Delinquents**: ~10-30s execution time (complex analysis)

## Security Considerations
- All commands run with minimal privileges
- Secrets managed through Kubernetes secrets
- No sensitive data in logs
- Resource limits prevent resource exhaustion
- Database connections properly closed

## Future Enhancements
- Add Prometheus metrics for monitoring
- Implement Slack notifications alongside email
- Add retry policies for transient failures
- Consider using Redis for faster locking mechanism
- Add more sophisticated scheduling (e.g., skip holidays)