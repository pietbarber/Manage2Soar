# CronJob Framework Architecture

## Overview
This document outlines the distributed CronJob framework for Manage2Soar, designed to prevent race conditions when multiple Kubernetes pods attempt to execute the same scheduled task simultaneously.

## Problem Statement
In a Kubernetes environment with multiple Django pods (currently 2 replicas), scheduled tasks could execute multiple times if each pod runs the same CronJob. This creates:
- Duplicate notifications sent to users
- Race conditions in data modification
- Resource waste and potential system instability

## Solution: Database-Level Distributed Locking

### Core Components

#### 1. CronJob Lock Model
```python
# utils/models.py
class CronJobLock(models.Model):
    job_name = models.CharField(max_length=100, unique=True)
    locked_by = models.CharField(max_length=100)  # Pod identifier
    locked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        db_table = 'cronjob_locks'
```

#### 2. Base CronJob Command Class
```python
# utils/management/commands/base_cronjob.py
class BaseCronJobCommand(BaseCommand):
    # Abstract base with distributed locking
    job_name = None  # Must be overridden
    max_execution_time = timedelta(hours=1)  # Default timeout
    
    def handle(self, *args, **options):
        if not self.acquire_lock():
            self.stdout.write(f"❌ Could not acquire lock for {self.job_name}")
            return
            
        try:
            self.execute_job(*args, **options)
        finally:
            self.release_lock()
    
    def execute_job(self, *args, **options):
        raise NotImplementedError("Subclasses must implement execute_job()")
```

#### 3. Locking Mechanism
Uses PostgreSQL's atomic operations:
- `SELECT FOR UPDATE NOWAIT` for immediate lock acquisition
- UUID-based pod identification
- Automatic lock expiration for failed pods
- Graceful lock release on completion

## Distributed Locking Algorithm

### Lock Acquisition Process
1. Generate unique pod identifier (hostname + process ID)
2. Attempt atomic lock creation with expiration time
3. If lock exists and hasn't expired, exit gracefully
4. If lock is expired, clean up and retry acquisition
5. Execute job only after successful lock acquisition

### Lock Release Process
1. Delete lock record atomically
2. Log completion status
3. Handle cleanup even if job fails

### Failure Handling
- **Pod crash**: Lock expires automatically (max_execution_time)
- **Database unavailable**: Fail fast, don't execute job
- **Job failure**: Still release lock to prevent deadlock

## Implementation Strategy

### Phase 1: Core Infrastructure
1. Create `CronJobLock` model with migration
2. Implement `BaseCronJobCommand` abstract class
3. Add utility functions for lock management
4. Write comprehensive tests for locking mechanism

### Phase 2: Command Conversion
1. Convert existing commands to use base class:
   - `send_duty_preop_emails.py`
   - `send_maintenance_digest.py` 
   - `expire_ad_hoc_days.py`
2. Create new notification commands:
   - `notify_aging_logsheets.py`
   - `notify_late_sprs.py`
   - `report_duty_delinquents.py`

### Phase 3: Kubernetes Integration
1. Create CronJob YAML manifests
2. Configure appropriate schedules
3. Set resource limits and failure policies
4. Deploy and monitor

## Scheduling Strategy

### Proposed Schedule
- **Daily 6:00 AM UTC**: Pre-op duty emails (for next day)
- **Daily 8:00 AM UTC**: Aging logsheet notifications
- **Weekly Sunday 9:00 AM UTC**: Maintenance digest
- **Weekly Monday 10:00 AM UTC**: Late SPR notifications  
- **Monthly 1st @ 7:00 AM UTC**: Duty delinquent reports
- **Daily 6:00 PM UTC**: Expire ad-hoc days (for tomorrow)

### Time Zone Considerations
- All schedules in UTC for consistency
- Notifications will be sent in UTC time but can reference local times in content
- Consider club's operational time zone for optimal delivery times

## Monitoring & Observability

### Logging Strategy
- Structured logging for all CronJob executions
- Lock acquisition/release events
- Job execution duration metrics
- Failure rate tracking

### Health Checks
- Monitor lock table for stuck locks
- Alert on repeated lock acquisition failures
- Track job execution success rates

### Database Impact
- Minimal overhead: single row per active job
- Automatic cleanup of expired locks
- Index on job_name for fast lookups

## Security Considerations

### Database Access
- CronJobs use same database credentials as main application
- No additional permissions required
- Lock table is application-managed, not system-level

### Pod Identification
- Use Kubernetes-provided hostname for pod identity
- Include process ID for uniqueness within pod restarts
- No sensitive information in pod identifiers

## Testing Strategy

### Unit Tests
- Lock acquisition/release cycles
- Timeout and expiration handling
- Concurrent access simulation
- Database transaction rollback scenarios

### Integration Tests
- Multi-pod simulation in test environment
- Race condition detection
- End-to-end CronJob execution
- Failure recovery validation

## Migration Path

### Backward Compatibility
- Existing management commands continue to work
- New base class is opt-in for conversion
- Gradual migration to distributed locking

### Deployment Strategy
1. Deploy lock infrastructure with feature flag
2. Convert one command at a time for testing
3. Monitor and validate each conversion
4. Full rollout once proven stable

---

## Next Steps
1. Create the `CronJobLock` model and migration
2. Implement `BaseCronJobCommand` abstract base class
3. Write comprehensive test suite for locking mechanism
4. Convert first existing command as proof of concept