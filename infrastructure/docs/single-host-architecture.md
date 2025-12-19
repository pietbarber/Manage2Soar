# Single-Host Manage2Soar Architecture

## Overview

This document describes the architecture for deploying Manage2Soar as a complete single-host solution. This deployment model is designed for soaring clubs that prefer to self-host rather than participate in the Manage2Soar.com multi-tenant GKE deployment.

**Target Use Case:** A single Ubuntu 22.04+ server running all M2S components for one club.

## Architecture Diagram

```mermaid
flowchart TB
    subgraph Internet["Internet"]
        Users[/"Club Members<br/>(Web Browsers)"/]
        ExtMail["External Email<br/>(Incoming)"]
    end

    subgraph SingleHost["Single Host Ubuntu Server"]
        subgraph WebStack["Web Stack"]
            NGINX["NGINX<br/>─────────<br/>• TLS termination (Let's Encrypt)<br/>• Static file serving<br/>• Reverse proxy to Gunicorn<br/>• Rate limiting"]
            Gunicorn["Gunicorn<br/>─────────<br/>• WSGI server<br/>• Process management<br/>• Worker processes"]
            Django["Django 5.2<br/>─────────<br/>• Manage2Soar Application<br/>• All apps: members, logsheet,<br/>  duty_roster, analytics, etc."]
        end

        subgraph DataLayer["Data Layer"]
            PostgreSQL["PostgreSQL 16<br/>─────────<br/>• Primary database<br/>• All M2S data<br/>• Backups via pg_dump"]
            MediaFiles[("Media Files<br/>─────────<br/>/var/www/m2s/media/<br/>• Uploaded images<br/>• Documents")]
            StaticFiles[("Static Files<br/>─────────<br/>/var/www/m2s/static/<br/>• CSS, JS, Images<br/>• collectstatic output")]
        end

        subgraph MailStack["Mail Stack"]
            Postfix["Postfix<br/>─────────<br/>• MTA (send/receive)<br/>• Virtual aliases<br/>• TLS encryption"]
            OpenDKIM["OpenDKIM<br/>─────────<br/>• DKIM signing<br/>• Key management"]
            Rspamd["Rspamd<br/>─────────<br/>• Spam filtering<br/>• Member whitelist"]
        end

        subgraph Services["System Services"]
            Systemd["Systemd<br/>─────────<br/>• gunicorn.service<br/>• m2s-cron.timer<br/>• nginx.service"]
            Cron["M2S Cron Jobs<br/>─────────<br/>• Email reminders<br/>• Data sync<br/>• Maintenance tasks"]
        end
    end

    Users -->|"HTTPS :443"| NGINX
    NGINX -->|"proxy_pass :8000"| Gunicorn
    Gunicorn --> Django
    Django --> PostgreSQL
    Django --> MediaFiles
    NGINX --> StaticFiles
    NGINX --> MediaFiles

    Django -->|"SMTP :587"| Postfix
    ExtMail -->|"SMTP :25"| Postfix
    Postfix --> OpenDKIM
    OpenDKIM --> Rspamd

    Systemd --> Gunicorn
    Systemd --> Cron
```

## Component Details

### 1. NGINX (Reverse Proxy & Static Server)

**Purpose:** TLS termination, static file serving, reverse proxy

**Configuration:**
- Listen on ports 80 (redirect to 443) and 443 (HTTPS)
- TLS certificates via Let's Encrypt (certbot)
- Serve static files directly from `/var/www/m2s/static/`
- Serve media files from `/var/www/m2s/media/`
- Proxy all other requests to Gunicorn on `127.0.0.1:8000`
- Rate limiting for login/API endpoints
- Security headers (HSTS, X-Frame-Options, etc.)

**Key Files:**
```
/etc/nginx/sites-available/m2s.conf
/var/www/m2s/static/
/var/www/m2s/media/
```

### 2. Gunicorn (WSGI Server)

**Purpose:** Run Django application with process management

**Configuration:**
- Bind to `127.0.0.1:8000` (not exposed to internet)
- Worker processes: `(2 * CPU cores) + 1`
- Worker class: `sync` (or `gevent` for async)
- Timeout: 120 seconds
- Managed by systemd for auto-restart

**Key Files:**
```
/etc/systemd/system/gunicorn.service
/opt/m2s/gunicorn.conf.py
```

### 3. Django Application

**Purpose:** Core Manage2Soar application

**Configuration:**
- Deployed to `/opt/m2s/app/`
- Virtual environment at `/opt/m2s/venv/`
- Environment variables in `/opt/m2s/.env`
- Static files collected to `/var/www/m2s/static/`
- Media files stored in `/var/www/m2s/media/`

**Key Environment Variables:**
```bash
DJANGO_SETTINGS_MODULE=manage2soar.settings
SECRET_KEY=<generated-secret>
DATABASE_URL=postgres://m2s:password@localhost:5432/m2s
ALLOWED_HOSTS=your-domain.com
STATIC_URL=/static/
STATIC_ROOT=/var/www/m2s/static/
MEDIA_URL=/media/
MEDIA_ROOT=/var/www/m2s/media/
EMAIL_HOST=localhost
EMAIL_PORT=587
EMAIL_HOST_USER=m2s-app@your-domain.com
EMAIL_HOST_PASSWORD=<smtp-password>
```

### 4. PostgreSQL Database

**Purpose:** Primary data store

**Configuration:**
- PostgreSQL 16 (latest stable)
- Database: `m2s`
- User: `m2s` with strong password
- Listen on `127.0.0.1:5432` (local only)
- Daily pg_dump backups to `/var/backups/m2s/`

**Key Files:**
```
/etc/postgresql/16/main/postgresql.conf
/etc/postgresql/16/main/pg_hba.conf
/var/backups/m2s/
```

### 5. Mail Server Stack

**Purpose:** Send and receive club email

**Components:**
- **Postfix:** MTA for sending/receiving email
- **OpenDKIM:** DKIM signing for deliverability
- **Rspamd:** Spam filtering with member whitelist

**Note:** The mail server roles already exist and will be integrated into the single-host playbook.

### 6. Systemd Services

**Services:**
```
gunicorn.service       - Django/Gunicorn application
m2s-cron.timer         - Scheduled M2S management commands
nginx.service          - Web server (pre-existing)
postgresql.service     - Database (pre-existing)
postfix.service        - Mail server (pre-existing)
```

## Directory Structure

```
/opt/m2s/
├── app/                    # Django application code
│   ├── manage.py
│   ├── manage2soar/
│   ├── members/
│   ├── logsheet/
│   └── ...
├── venv/                   # Python virtual environment
├── .env                    # Environment variables (gitignored)
├── gunicorn.conf.py        # Gunicorn configuration
└── logs/
    ├── gunicorn.log
    ├── django.log
    └── cron.log

/var/www/m2s/
├── static/                 # Django collectstatic output
│   ├── admin/
│   ├── css/
│   ├── js/
│   └── ...
└── media/                  # User uploads
    ├── member_photos/
    └── documents/

/var/backups/m2s/
├── daily/                  # Daily database backups
└── weekly/                 # Weekly full backups

/etc/nginx/sites-available/
└── m2s.conf               # NGINX configuration

/etc/systemd/system/
├── gunicorn.service       # Gunicorn service
└── m2s-cron.timer         # Cron timer
```

## Ansible Role Structure

```
infrastructure/ansible/
├── playbooks/
│   ├── mail-server.yml           # Existing mail server playbook
│   └── single-host.yml           # NEW: Complete single-host deployment
│
├── roles/
│   ├── common/                   # Existing: Base system setup
│   ├── postfix/                  # Existing: Postfix MTA
│   ├── opendkim/                 # Existing: DKIM signing
│   ├── rspamd/                   # Existing: Spam filtering
│   ├── m2s-mail-sync/            # Existing: M2S alias sync
│   │
│   ├── postgresql/               # NEW: PostgreSQL database
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   └── templates/
│   │
│   ├── nginx/                    # NEW: NGINX reverse proxy
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   └── templates/
│   │       ├── m2s.conf.j2
│   │       └── ssl-params.conf.j2
│   │
│   ├── m2s-app/                  # NEW: Django/Gunicorn app
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/
│   │   │   ├── main.yml
│   │   │   ├── deploy.yml
│   │   │   ├── venv.yml
│   │   │   └── systemd.yml
│   │   └── templates/
│   │       ├── env.j2
│   │       ├── gunicorn.conf.py.j2
│   │       └── gunicorn.service.j2
│   │
│   └── m2s-backup/               # NEW: Backup configuration
│       ├── defaults/main.yml
│       ├── tasks/main.yml
│       └── templates/
│           └── backup.sh.j2
│
├── group_vars/
│   ├── all.yml.example           # UPDATE: Add new variables
│   └── single_host.yml.example   # NEW: Single-host specific vars
│
└── inventory/
    ├── hosts.yml.example         # UPDATE: Add single_host group
    └── single_host.yml.example   # NEW: Example single-host inventory
```

## Implementation Plan

### Phase 1: Foundation (Roles: common, postgresql)
1. Update `common` role for single-host prerequisites
2. Create `postgresql` role with secure defaults
3. Test database setup on m2s-sa

### Phase 2: Application Layer (Roles: m2s-app, nginx)
4. Create `m2s-app` role for Django/Gunicorn
5. Create `nginx` role for reverse proxy and static serving
6. Test application deployment and static file serving

### Phase 3: Mail Integration (Existing Roles)
7. Integrate existing mail roles into single-host playbook
8. Configure Django to use local mail server
9. Test email sending and receiving

### Phase 4: Operations (Roles: m2s-backup, cron)
10. Create `m2s-backup` role for automated backups
11. Configure M2S cron jobs via systemd timers
12. Test backup/restore procedures

### Phase 5: Documentation & Polish
13. Create comprehensive deployment documentation
14. Create example configuration files
15. Security hardening and final testing

## Security Considerations

### Network Security
- Only ports 22 (SSH), 80 (HTTP redirect), 443 (HTTPS), 25 (SMTP), 587 (SMTP submission) exposed
- PostgreSQL, Gunicorn listen only on localhost
- UFW firewall configured by Ansible

### Application Security
- Django SECRET_KEY generated per-deployment
- Database password generated per-deployment
- All credentials in gitignored files
- HTTPS enforced with HSTS
- Security headers configured in NGINX

### Backup Security
- Database backups encrypted with GPG (optional)
- Backup files readable only by root
- Retention policy: 7 daily, 4 weekly

## Configuration Files

### Example Variables (group_vars/single_host.yml.example)

```yaml
# Single-Host Deployment Configuration
# Copy to single_host.yml and customize

# Domain Configuration
m2s_domain: "your-club.manage2soar.com"
m2s_club_name: "Your Soaring Club"
m2s_club_prefix: "ysc"

# Database
postgres_db: "m2s"
postgres_user: "m2s"
postgres_password: "CHANGE_ME_STRONG_PASSWORD"

# Django
django_secret_key: "CHANGE_ME_50_RANDOM_CHARS"
django_debug: false
django_allowed_hosts: "{{ m2s_domain }}"

# Email (for club outbound email)
email_from_address: "noreply@{{ m2s_domain }}"

# Let's Encrypt
letsencrypt_email: "admin@{{ m2s_domain }}"

# Backup
backup_retention_days: 7
backup_gpg_recipient: ""  # Set for encrypted backups

# Git deployment (or set deploy_method: 'upload')
deploy_method: "git"
git_repo: "https://github.com/pietbarber/Manage2Soar.git"
git_branch: "main"
```

## Testing Checklist

### Pre-deployment
- [ ] SSH access to target server verified
- [ ] DNS A record points to server IP
- [ ] Required ports open in firewall

### Post-deployment
- [ ] HTTPS works with valid certificate
- [ ] Static files load correctly (CSS, JS, images)
- [ ] Django admin accessible
- [ ] User login works
- [ ] Email sending works
- [ ] Email receiving works (if enabled)
- [ ] Database backups running
- [ ] Cron jobs executing
- [ ] Logs rotating properly

## Rollback Procedure

1. Stop services: `systemctl stop gunicorn nginx`
2. Restore database: `pg_restore -d m2s /var/backups/m2s/latest.dump`
3. Restore application: `git checkout <previous-tag>` or restore from backup
4. Start services: `systemctl start nginx gunicorn`
5. Verify functionality

## Support & Troubleshooting

### Common Issues

**502 Bad Gateway**
- Check Gunicorn: `systemctl status gunicorn`
- Check logs: `journalctl -u gunicorn -f`

**Static files not loading**
- Run collectstatic: `/opt/m2s/venv/bin/python manage.py collectstatic`
- Check NGINX config: `nginx -t`

**Database connection errors**
- Check PostgreSQL: `systemctl status postgresql`
- Verify DATABASE_URL in `.env`

**Email not sending**
- Check Postfix: `systemctl status postfix`
- Check logs: `tail -f /var/log/mail.log`

---

*Document Version: 1.0*
*Last Updated: December 2025*
*Issue Reference: #405*
