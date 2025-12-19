# Manage2Soar Single-Host Ansible Deployment

This directory contains Ansible playbooks and roles for deploying a complete Manage2Soar instance on a single server. This is ideal for small to medium-sized soaring clubs that want a self-hosted solution.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Single Host Server                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐   │
│   │   NGINX     │───▶│  Gunicorn    │───▶│   PostgreSQL    │   │
│   │  (Port 80)  │    │ (Port 8000)  │    │   (Port 5432)   │   │
│   │  (Port 443) │    │              │    │                 │   │
│   └─────────────┘    └──────────────┘    └─────────────────┘   │
│         │                   │                    │              │
│         ▼                   ▼                    ▼              │
│   ┌───────────┐      ┌───────────┐        ┌───────────┐        │
│   │  Static   │      │  Django   │        │  Database │        │
│   │  Files    │      │  App      │        │   Data    │        │
│   └───────────┘      └───────────┘        └───────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

1. **Target Server**: Ubuntu 22.04 or 24.04 LTS with SSH access
2. **Control Machine**: Any machine with Ansible 2.10+ installed
3. **Domain Name**: A domain pointing to your server (for SSL)

### Step 1: Install Ansible

```bash
# On Ubuntu/Debian
pip install ansible

# Or using pipx (recommended)
pipx install ansible
```

### Step 2: Clone the Repository

```bash
git clone https://github.com/pietbarber/Manage2Soar.git
cd Manage2Soar/infrastructure/ansible
```

### Step 3: Configure Inventory

```bash
cp inventory/single_host.yml.example inventory/single_host.yml
```

Edit `inventory/single_host.yml`:

```yaml
all:
  hosts:
    m2s-server:
      ansible_host: your-server-ip-or-hostname
      ansible_user: your-ssh-user
```

### Step 4: Configure Variables

Create the variables directory:

```bash
mkdir -p group_vars/single_host
```

Copy and customize the variable files:

```bash
cp group_vars/single_host.vars.yml.example group_vars/single_host/vars.yml
# Edit vars.yml with your club's configuration
```

### Step 5: Set Up Encrypted Secrets (Vault)

Create a vault password file:

```bash
# Generate a strong password
openssl rand -base64 32 > ~/.ansible_vault_pass
chmod 600 ~/.ansible_vault_pass
```

Create the encrypted vault file:

```bash
ansible-vault create group_vars/single_host/vault.yml \
  --vault-password-file ~/.ansible_vault_pass
```

Add your secrets (the editor will open):

```yaml
---
ansible_become_password: "your-sudo-password"
vault_postgresql_password: "generate-strong-password"
vault_django_secret_key: "generate-50-char-secret"
```

Generate secure values:

```bash
# PostgreSQL password
openssl rand -base64 32

# Django secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Step 6: Test Connection

```bash
ansible -i inventory/single_host.yml all -m ping \
  --vault-password-file ~/.ansible_vault_pass \
  -e "@group_vars/single_host/vault.yml"
```

### Step 7: Deploy

```bash
ansible-playbook -i inventory/single_host.yml \
  --vault-password-file ~/.ansible_vault_pass \
  -e "@group_vars/single_host/vault.yml" \
  -e "@group_vars/single_host/vars.yml" \
  playbooks/single-host.yml
```

## Directory Structure

```
infrastructure/ansible/
├── inventory/
│   └── single_host.yml.example     # Inventory template
├── group_vars/
│   ├── single_host/                # Your configuration (gitignored)
│   │   ├── vars.yml               # Non-secret variables
│   │   └── vault.yml              # Encrypted secrets
│   ├── single_host.vars.yml.example
│   └── single_host.vault.yml.example
├── playbooks/
│   ├── single-host.yml            # Main deployment playbook
│   ├── test-postgresql.yml        # PostgreSQL testing
│   ├── test-nginx.yml             # NGINX testing
│   └── test-m2s-app.yml           # Application testing
└── roles/
    ├── postgresql/                # Database role
    ├── nginx/                     # Web server role
    └── m2s-app/                   # Django application role
```

## Roles

### postgresql

Installs and configures PostgreSQL 17:
- Creates M2S database and user
- Configures performance settings
- Sets up automated daily backups
- Enables logrotate

### nginx

Configures NGINX as reverse proxy:
- Optional Let's Encrypt SSL (certbot)
- Rate limiting and security headers
- Gzip compression
- Static and media file serving

### m2s-app

Deploys the Django application:
- Git-based deployment from repository
- Python virtual environment
- Gunicorn WSGI server with systemd
- Automated migrations and collectstatic
- Environment file configuration

## Configuration Reference

### Essential Variables (vars.yml)

| Variable | Description | Example |
|----------|-------------|---------|
| `club_name` | Your club's name | `"Mountain Soaring Club"` |
| `club_prefix` | Short prefix | `"msc"` |
| `m2s_domain` | Domain name | `"m2s.mountainsoaring.org"` |
| `postgresql_database` | Database name | `"m2s"` |
| `postgresql_user` | Database user | `"m2s"` |
| `nginx_ssl_enabled` | Enable HTTPS | `true` |
| `letsencrypt_email` | Email for certs | `"admin@club.org"` |

### Secret Variables (vault.yml)

| Variable | Description |
|----------|-------------|
| `ansible_become_password` | Sudo password |
| `vault_postgresql_password` | Database password |
| `vault_django_secret_key` | Django secret key |
| `vault_google_oauth_client_id` | Google OAuth (optional) |
| `vault_google_oauth_client_secret` | Google OAuth (optional) |

## Post-Deployment

### Create Django Superuser

```bash
ssh your-server
sudo -u m2s /opt/m2s/venv/bin/python /opt/m2s/app/manage.py createsuperuser
```

### View Logs

```bash
# Gunicorn/Django
journalctl -u gunicorn -f

# NGINX
tail -f /var/log/nginx/access.log

# Application
tail -f /var/log/m2s/django.log
```

### Service Management

```bash
# Restart application
sudo systemctl restart gunicorn

# Restart web server
sudo systemctl restart nginx

# Check status
sudo systemctl status gunicorn nginx postgresql
```

## Updating the Application

To update to the latest version:

```bash
ansible-playbook -i inventory/single_host.yml \
  --vault-password-file ~/.ansible_vault_pass \
  -e "@group_vars/single_host/vault.yml" \
  -e "@group_vars/single_host/vars.yml" \
  -e "m2s_force_migrate=true" \
  -e "m2s_force_collectstatic=true" \
  playbooks/single-host.yml
```

## Troubleshooting

### Connection Refused

Check if services are running:

```bash
sudo systemctl status postgresql nginx gunicorn
```

### 502 Bad Gateway

Gunicorn is not running. Check logs:

```bash
journalctl -u gunicorn -n 50
```

### 500 Internal Server Error

Django application error. Check:

```bash
tail -f /var/log/m2s/django.log
```

### SSL Certificate Issues

Manually request certificate:

```bash
sudo certbot --nginx -d your-domain.com
```

## Security Recommendations

1. **Firewall**: Enable UFW and only allow ports 22, 80, 443
2. **SSH**: Disable password auth, use key-based only
3. **fail2ban**: Installed and configured automatically
4. **Updates**: Keep the server updated with `apt upgrade`
5. **Backups**: PostgreSQL backups are automatic; also backup `/var/www/m2s/media`

## License

Same as Manage2Soar - see main repository LICENSE.
