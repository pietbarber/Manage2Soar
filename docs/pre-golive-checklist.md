# Pre-Go-Live Checklist for Skyline Soaring

This checklist should be completed **before** the actual go-live cutover.

## Infrastructure & Deployment

- [ ] **GKE Cluster Health**
  - [ ] Verify 2-pod deployment is stable
  - [ ] Check pod resource limits and requests
  - [ ] Confirm distributed CronJob system is operational
  - [ ] Verify PostgreSQL connection pooling is configured

- [ ] **Database**
  - [ ] Production PostgreSQL database provisioned and tested
  - [ ] Database backups configured and tested
  - [ ] Backup retention policy configured (30 days minimum)
  - [ ] Point-in-time recovery tested
  - [ ] Database credentials stored in Ansible Vault
  - [ ] Connection pooling configured (pgbouncer)

- [ ] **DNS & Domain**
  - [ ] DNS records prepared for skylinesoaring.org
  - [ ] A/AAAA records pointing to GKE ingress
  - [ ] MX records configured for email
  - [ ] TXT records for SPF/DKIM/DMARC
  - [ ] DNS TTL lowered to 300s (5 minutes) for quick cutover

- [ ] **SSL/TLS Certificates**
  - [ ] Google-managed SSL certificate provisioned
  - [ ] Certificate status: ACTIVE
  - [ ] Verify certificate covers www and apex domain
  - [ ] Test HTTPS redirects

- [ ] **Static Files & Media**
  - [ ] GCS bucket for media files configured
  - [ ] Static files collected to GCS: `manage.py collectstatic`
  - [ ] CDN/Cloud Storage permissions verified
  - [ ] Test image uploads and avatar generation

## Application Configuration

- [ ] **Django Settings**
  - [ ] `DEBUG = False` in production
  - [ ] `ALLOWED_HOSTS` includes skylinesoaring.org
  - [ ] Secret key rotated and stored in K8s secrets
  - [ ] Session security settings enabled (SECURE_SSL_REDIRECT, etc.)
  - [ ] HSTS configured appropriately

- [ ] **Email Configuration**
  - [ ] SMTP settings configured (SendGrid/Gmail/etc.)
  - [ ] Email templates tested
  - [ ] Test all automated emails:
    - [ ] Duty roster pre-op reminders
    - [ ] Instruction reports
    - [ ] Password resets
    - [ ] Member notifications
  - [ ] Verify sender domain authentication (SPF/DKIM)

- [ ] **OAuth & Authentication**
  - [ ] Google OAuth2 configured for skylinesoaring.org domain
  - [ ] OAuth consent screen configured
  - [ ] Test Google login flow
  - [ ] Fallback Django authentication working

- [ ] **CronJobs & Scheduled Tasks**
  - [ ] All CronJobs deployed and scheduled
  - [ ] Distributed locking working across pods
  - [ ] Test duty roster email CronJob
  - [ ] Test analytics aggregation jobs
  - [ ] Verify CronJob logs are accessible

## Data Migration & Content

- [ ] **Member Data**
  - [ ] Import member roster from legacy system
  - [ ] Verify member statuses (Full Member, Associate, etc.)
  - [ ] Import profile photos and avatars
  - [ ] Test member login for 5-10 sample members

- [ ] **Operational Data**
  - [ ] Import glider fleet data
  - [ ] Import historical flight logs (if applicable)
  - [ ] Import duty roster assignments
  - [ ] Import instructor qualifications
  - [ ] Import badge/achievement data

- [ ] **CMS Content**
  - [ ] Import/recreate all CMS pages
  - [ ] Upload restricted documents to correct locations
  - [ ] Test document access permissions (public vs. restricted)
  - [ ] Verify TinyMCE rendering (tables, images, YouTube embeds)
  - [ ] Test membership terms and footer content

## Security & Compliance

- [ ] **Security Scanning**
  - [ ] All CodeQL alerts resolved
  - [ ] All dependabot alerts resolved
  - [ ] Bandit security scan passes
  - [ ] No HIGH or CRITICAL vulnerabilities

- [ ] **Code Quality**
  - [ ] Test coverage > 80%
  - [ ] All E2E tests passing
  - [ ] Performance tests completed
  - [ ] Load testing results acceptable

- [ ] **Access Control**
  - [ ] Verify role-based permissions (CFI, DCFI, Ops Officer, etc.)
  - [ ] Test restricted document access
  - [ ] Test duty roster swap permissions
  - [ ] Verify admin panel access controls

- [ ] **Compliance**
  - [ ] Privacy policy updated and published
  - [ ] Terms of service published
  - [ ] Cookie consent mechanism in place (if needed)
  - [ ] Data retention policies documented

## Monitoring & Alerting

- [ ] **Application Monitoring**
  - [ ] GKE monitoring enabled
  - [ ] Application logs aggregated (Cloud Logging)
  - [ ] Error tracking configured (Sentry/Cloud Error Reporting)
  - [ ] Performance monitoring enabled

- [ ] **Alerts Configured**
  - [ ] Pod restart alerts
  - [ ] High CPU/memory usage alerts
  - [ ] Database connection pool exhaustion alerts
  - [ ] Failed CronJob alerts
  - [ ] 5xx error rate alerts

- [ ] **Health Checks**
  - [ ] Kubernetes liveness probes configured
  - [ ] Kubernetes readiness probes configured
  - [ ] Test pod restart recovery

## Performance & Capacity

- [ ] **Load Testing**
  - [ ] Simulate 50 concurrent users
  - [ ] Test critical paths (login, flight logging, duty roster)
  - [ ] Verify response times < 500ms for most pages
  - [ ] Database query performance acceptable

- [ ] **Optimization**
  - [ ] Database indexes on frequently queried fields
  - [ ] Query performance reviewed (no N+1 queries)
  - [ ] Static file caching configured
  - [ ] Browser caching headers set

## Documentation & Training

- [ ] **User Documentation**
  - [ ] User guide published (if applicable)
  - [ ] FAQ updated
  - [ ] Video tutorials created (optional)
  - [ ] Help links working

- [ ] **Admin Documentation**
  - [ ] Deployment guide updated
  - [ ] Runbook for common issues
  - [ ] Database backup/restore procedures
  - [ ] Rollback procedures documented

- [ ] **Training**
  - [ ] Key staff trained on new system
  - [ ] CFIs trained on instruction logging
  - [ ] Ops officers trained on duty roster
  - [ ] Admin trained on CMS

## Rollback Plan

- [ ] **Rollback Readiness**
  - [ ] Previous production environment still accessible
  - [ ] Rollback playbook documented and tested
  - [ ] Database rollback procedure prepared
  - [ ] DNS rollback steps documented
  - [ ] Estimated rollback time: _______ minutes

## Communication Plan

- [ ] **Stakeholder Communication**
  - [ ] Board notification scheduled
  - [ ] Member communication drafted
  - [ ] Maintenance window announced (if applicable)
  - [ ] Support contact information published

- [ ] **Launch Announcement**
  - [ ] Email to all members prepared
  - [ ] Website banner/announcement prepared
  - [ ] Social media posts drafted (optional)

## Final Verification

- [ ] **Pre-Launch Testing**
  - [ ] Complete end-to-end user flow test
  - [ ] Test all critical features as different user roles
  - [ ] Verify mobile responsiveness
  - [ ] Cross-browser testing (Chrome, Firefox, Safari, Edge)

- [ ] **Sign-Offs**
  - [ ] Technical lead approval: _______________________
  - [ ] Product owner approval: _______________________
  - [ ] Board approval (if required): _______________________

---

**Notes:**
- Complete this checklist at least 48 hours before go-live
- Any unchecked items should have documented exceptions/waivers
- Keep a copy of this checklist with completion dates for audit trail
