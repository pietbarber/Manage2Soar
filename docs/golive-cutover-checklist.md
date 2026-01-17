# Go-Live Cutover Checklist for Skyline Soaring

**Date:** _________________  
**Start Time:** _________________  
**Cutover Lead:** _________________  
**Emergency Contact:** _________________

## Pre-Cutover (T-60 minutes)

- [ ] **Team Assembly** (T-60)
  - [ ] Technical lead present
  - [ ] Database admin on call
  - [ ] Support team ready
  - [ ] Communication lead ready

- [ ] **Final System Check** (T-45)
  - [ ] All pods healthy in GKE cluster
  - [ ] Database connections stable
  - [ ] CronJobs paused/disabled (to prevent conflicts during cutover)
  - [ ] Monitoring dashboards open

- [ ] **Communication** (T-30)
  - [ ] "Maintenance in progress" banner enabled on old site
  - [ ] Support channels notified (email/phone)
  - [ ] Board members notified

- [ ] **Final Backup** (T-30)
  - [ ] Database backup initiated: `timestamp: __________`
  - [ ] Backup verification completed
  - [ ] Backup location recorded: _________________________

## Cutover Window (T-0)

### Phase 1: Disable Old System (T-0 to T+5)

- [ ] **Stop Old System** (T-0)
  - [ ] Put old site in read-only mode (if applicable)
  - [ ] Disable old CronJobs
  - [ ] Stop accepting new data
  - [ ] Take final snapshot/backup
  - [ ] Timestamp: __________

### Phase 2: Data Synchronization (T+5 to T+15)

- [ ] **Final Data Sync** (T+5)
  - [ ] Export any delta data from old system
  - [ ] Import final data to new PostgreSQL database
  - [ ] Run data validation scripts
  - [ ] Verify record counts match expected values
  - [ ] Timestamp: __________

- [ ] **Database Migration** (T+10)
  - [ ] Run final Django migrations: `python manage.py migrate`
  - [ ] Verify migration success
  - [ ] Check for migration errors in logs
  - [ ] Timestamp: __________

### Phase 3: DNS Cutover (T+15 to T+20)

- [ ] **DNS Changes** (T+15)
  - [ ] Update DNS A/AAAA records to point to GKE ingress IP
  - [ ] DNS change timestamp: __________
  - [ ] Old IP: _________________
  - [ ] New IP: 34.13.120.184 (manage2soar-gateway)
  - [ ] Wait for DNS propagation (5-10 minutes with low TTL)

- [ ] **SSL Certificate Provisioning** (T+17)
  - [ ] Run SSL cert playbook: `ansible-playbook -i inventory/gcp_app.yml --vault-password-file ~/.ansible_vault_pass playbooks/update-ssl-cert.yml`
  - [ ] Wait for Google to provision certificates (5-10 minutes)
  - [ ] Monitor status: `gcloud compute ssl-certificates describe manage2soar-ssl-cert-v2 --global --format="yaml(managed.domainStatus)"`
  - [ ] Verify all domains show ACTIVE status
  - [ ] Timestamp: __________

- [ ] **DNS Verification** (T+20)
  - [ ] Verify DNS resolves to new IP: `dig skylinesoaring.org`
  - [ ] Test from multiple locations: https://www.whatsmydns.net
  - [ ] Verify both apex and www subdomain
  - [ ] Test SSL: `curl -I https://skylinesoaring.org`

### Phase 4: Application Activation (T+20 to T+25)

- [ ] **Disable Email Dev Mode** (T+20)
  - [ ] Verify EMAIL_DEV_MODE is set to `false` in production Kubernetes secrets
  - [ ] Check current setting: `kubectl get secret django-secrets -n tenant-ssc -o jsonpath='{.data.EMAIL_DEV_MODE}' | base64 -d`
  - [ ] If enabled, update and restart pods
  - [ ] Verify emails will send to real addresses

- [ ] **Enable Application** (T+21)
  - [ ] Verify pods are running: `kubectl get pods -n tenant-ssc`
  - [ ] Check pod logs for errors: `kubectl logs -n tenant-ssc -l app=manage2soar`
  - [ ] Enable CronJobs: verify distributed locking is working
  - [ ] Timestamp: __________

- [ ] **Static Files** (T+22)
  - [ ] Verify static files serving from GCS
  - [ ] Test image uploads
  - [ ] Test avatar generation
  - [ ] Check CSS/JS loading

- [ ] **SSL/HTTPS** (T+23)
  - [ ] Verify SSL certificate is active
  - [ ] Test HTTPS redirect
  - [ ] Verify HSTS headers
  - [ ] Check SSL Labs rating: https://www.ssllabs.com/ssltest/

### Phase 5: Functional Verification (T+25 to T+40)

- [ ] **Critical Path Testing** (T+25)
  - [ ] **Member Login**
    - [ ] Google OAuth login works
    - [ ] Django fallback login works
    - [ ] Test with 3 different member accounts
  - [ ] **Flight Logging**
    - [ ] Create test flight log entry
    - [ ] Verify flight log saves
    - [ ] Check analytics updates
  - [ ] **Duty Roster**
    - [ ] View duty roster
    - [ ] Test duty swap (if applicable)
    - [ ] Verify pre-op email can be triggered
  - [ ] **CMS Pages**
    - [ ] Test public pages load
    - [ ] Test restricted pages require login
    - [ ] Verify document downloads work
  - [ ] **Instruction**
    - [ ] Create test instruction report
    - [ ] Verify report email sends

- [ ] **Email Functionality** (T+35)
  - [ ] Send test email from application
  - [ ] Verify email delivery
  - [ ] Check email formatting
  - [ ] Test reply-to address

- [ ] **User Role Testing** (T+38)
  - [ ] Test as regular member
  - [ ] Test as instructor
  - [ ] Test as ops officer
  - [ ] Test as admin

### Phase 6: Monitoring & Performance (T+40 to T+50)

- [ ] **Monitoring Checks** (T+40)
  - [ ] Verify GKE monitoring showing metrics
  - [ ] Check Cloud Logging for errors
  - [ ] Verify alert channels receiving alerts
  - [ ] Review application error logs

- [ ] **Performance Verification** (T+42)
  - [ ] Check page load times (< 500ms for most pages)
  - [ ] Verify database query performance
  - [ ] Check pod CPU/memory usage
  - [ ] Monitor for any spikes or anomalies

- [ ] **Security Verification** (T+45)
  - [ ] Verify HTTPS enforced
  - [ ] Check security headers present
  - [ ] Test login brute force protection (rate limiting)
  - [ ] Verify restricted document access

## Post-Cutover (T+50 onwards)

### Phase 7: Member Access (T+50 to T+60)

- [ ] **Soft Launch** (T+50)
  - [ ] Enable access for pilot group (5-10 members)
  - [ ] Monitor their usage
  - [ ] Collect immediate feedback
  - [ ] Watch for errors in logs

- [ ] **Communication** (T+55)
  - [ ] Send "We're live!" email to pilot group
  - [ ] Post announcement on old site (if still accessible)
  - [ ] Update support channels

### Phase 8: Full Launch (T+60 to T+120)

- [ ] **General Availability** (T+60)
  - [ ] Remove maintenance banner
  - [ ] Send launch email to all members
  - [ ] Post announcement on social media (optional)
  - [ ] Enable full access

- [ ] **Continuous Monitoring** (T+60 to T+120)
  - [ ] Monitor error rates every 15 minutes
  - [ ] Check database connection pool
  - [ ] Watch for performance degradation
  - [ ] Monitor user login success rate

### Phase 9: Stabilization (T+120 to T+240)

- [ ] **Extended Monitoring** (First 2 hours)
  - [ ] Review all error logs
  - [ ] Check CronJob execution
  - [ ] Verify scheduled emails send
  - [ ] Monitor database backups

- [ ] **User Support** (First 4 hours)
  - [ ] Respond to user questions/issues
  - [ ] Document any bugs discovered
  - [ ] Create hotfix tickets for critical issues

## Post-Launch (Next 24 hours)

- [ ] **Day 1 Review** (24 hours post-launch)
  - [ ] Review all error logs
  - [ ] Check system performance metrics
  - [ ] Review user feedback
  - [ ] Verify all CronJobs executed successfully

- [ ] **Communication** (24 hours post-launch)
  - [ ] Send status update to board
  - [ ] Thank pilot group participants
  - [ ] Post "launch successful" update

## Rollback Decision Points

**If any of these occur, consider rollback:**
- [ ] Database corruption detected
- [ ] Critical feature completely broken
- [ ] Security vulnerability discovered
- [ ] Performance degradation > 5x expected
- [ ] Widespread user login failures (> 25%)
- [ ] Data loss detected

**Rollback Decision Maker:** _________________  
**Rollback Threshold Time:** T+45 minutes (after this, rollback becomes more complex)

## Rollback Procedure (If Needed)

1. **Immediate Actions**
   - [ ] Stop new data writes in production
   - [ ] Enable maintenance banner
   - [ ] Notify team of rollback decision

2. **DNS Rollback**
   - [ ] Revert DNS to old IP address
   - [ ] Wait 5-10 minutes for propagation
   - [ ] Verify old site is accessible

3. **Communication**
   - [ ] Send "maintenance extended" email
   - [ ] Update status page
   - [ ] Schedule retrospective

4. **Post-Rollback**
   - [ ] Document issues encountered
   - [ ] Create fix plan
   - [ ] Schedule new cutover date

## Success Criteria

**Launch is considered successful when:**
- [ ] All critical features working
- [ ] No critical errors in logs
- [ ] > 90% of test users can login
- [ ] Performance within acceptable range
- [ ] All CronJobs executing successfully
- [ ] No security issues detected

---

## Notes

**Issues Encountered:**
-
-
-

**Lessons Learned:**
-
-
-

**Post-Launch Actions Required:**
-
-
-

---

**Cutover Completed:** _________________  
**Final Status:** [ ] Success  [ ] Partial Success  [ ] Rollback  
**Sign-off:** _________________ (Technical Lead)  
**Date/Time:** _________________
