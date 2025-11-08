# Notification Backlog - The "Never Going to Check" List

This document contains notification and scheduled task ideas that were considered but are not currently prioritized. They're documented here for completeness but should not be actively pursued.

## Rejected/Deferred Notification Ideas

### 6. Membership Status Expiration Reminders
**Status:** ❌ Rejected  
**Reason:** No current need identified  
**Description:** Would send reminders to members when their membership status is approaching expiration.

### 7. Badge Progress Staleness / Flight Activity Nudges  
**Status:** ❌ Rejected  
**Reason:** "They pay their dues, no need to kick them to showing up. Sometimes people get busy!"  
**Description:** Would notify members who haven't had flight activity for extended periods to encourage engagement.

### 9. Training Progress Nudges for Stuck Students
**Status:** ❌ Rejected  
**Reason:** "This is a sensitive subject. There are some students who are quite stuck, and I don't know if we have the capacity to handle people all getting nudged to show up, and then we don't have the resources to use them!"  
**Description:** Would send gentle reminders to students who haven't had instruction reports in X weeks to encourage continued training progress.

---

## Notes
- These ideas were generated during the analysis phase of issue #178 (Kubernetes CronJobs implementation)
- They remain documented for historical context but should not be implemented
- Focus should remain on the approved sub-issues within #178

## Approved Implementation List (for reference)
The following notifications ARE being implemented as part of #178:
- Issue #157: Upcoming Duty Day Notifications (7 days advance)  
- Issue #159: Aging Unfinalized Logsheet (7+ days overdue)
- Issue #160: Instructor Late SPR Filing (7/14/21/25/30 day intervals)
- Issue #100: Duty Delinquent Members Report (monthly)
- Issue #10: Equipment Annual Inspection Alerts (maintenance deadlines)
