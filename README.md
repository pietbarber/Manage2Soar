
# Manage2Soar

Manage2Soar is a Django 5.2.12 platform for soaring club operations and member management.
It combines members, duty roster scheduling, flight logging, instruction workflows, analytics,
notifications, and CMS content in one integrated system.

## Highlights

- Google OAuth2 login with Django fallback authentication
- Role-based access for members, instructors, duty officers, and admins
- Flight operations logging and closeout workflows
- Duty roster scheduling and volunteer preference support
- Read-only analytics and reporting dashboards
- TinyMCE-powered rich content management
- PWA/offline support for key flight logging flows

## Project Structure

Major apps:

- `members` - member profiles, roles, badges, qualifications
- `logsheet` - flight logging and operational records
- `duty_roster` - scheduling, swaps, ad-hoc operations workflows
- `instructors` - training records and syllabus/report flows
- `analytics` - read-only metrics and charts
- `cms` - homepage/content management for public and member audiences
- `knowledgetest` - quiz and written test management
- `notifications` - automated and ad-hoc email workflows
- `siteconfig` - club/site configuration

## Local Development

### Prerequisites

- Python 3.12+
- PostgreSQL 12+
- Git

### Option A: Automated Setup

```bash
git clone https://github.com/pietbarber/Manage2Soar.git
cd Manage2Soar
./infrastructure/scripts/setup-dev.sh
```

### Option B: Manual Setup

1. Clone and enter the repo:

```bash
git clone https://github.com/pietbarber/Manage2Soar.git
cd Manage2Soar
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create local environment file:

```bash
cp .env.example .env
```

At minimum, set values for:

- `DJANGO_SECRET_KEY`
- `DB_PASSWORD`

5. Create local database and user (example):

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE manage2soar;
CREATE USER m2s WITH PASSWORD 'your-password-here' CREATEDB;
ALTER ROLE m2s SET client_encoding TO 'utf8';
ALTER ROLE m2s SET default_transaction_isolation TO 'read committed';
ALTER ROLE m2s SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE manage2soar TO m2s;
ALTER DATABASE manage2soar OWNER TO m2s;
\q
```

6. Apply migrations and create an admin user:

```bash
python manage.py migrate
python manage.py createsuperuser
```

7. Run the dev server on port 8001:

```bash
python manage.py runserver 127.0.0.1:8001
```

Open:

- http://127.0.0.1:8001
- http://127.0.0.1:8001/admin

### Option C: GCP Installation via Ansible (IaC)

If you are installing Manage2Soar directly onto Google Cloud infrastructure,
use the Ansible playbooks rather than manual cloud setup.

```bash
cd infrastructure/ansible
cp inventory/gcp_app.yml.example inventory/gcp_app.yml
cp group_vars/gcp_app.vars.yml.example group_vars/gcp_app/vars.yml
cp group_vars/gcp_app.vault.yml.example group_vars/gcp_app/vault.yml
ansible-vault encrypt group_vars/gcp_app/vault.yml
ansible-playbook -i inventory/gcp_app.yml --vault-password-file ~/.ansible_vault_pass playbooks/gcp-app-deploy.yml
```

Primary instructions:

- [infrastructure/ansible/README.md](infrastructure/ansible/README.md)
- [infrastructure/ansible/docs/gke-deployment-guide.md](infrastructure/ansible/docs/gke-deployment-guide.md)

### Troubleshooting

Database auth errors:

- Ensure `.env` exists and includes `DB_PASSWORD`
- Confirm PostgreSQL is running (`sudo systemctl status postgresql`)

Command not found errors:

- Activate the virtualenv first: `source .venv/bin/activate`

Port issues:

- Use `127.0.0.1:8001` for local development

## Testing and Quality

Run tests with pytest:

```bash
source .venv/bin/activate
pytest
```

Contributor tooling:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

The pre-commit pipeline includes formatting, security checks, and configuration validation.

## Production Deployment

Manage2Soar is deployed using Infrastructure as Code (IaC) with Ansible.

| Feature | Single-Host | GKE (Kubernetes) |
|---------|-------------|------------------|
| Best for | Small clubs | Larger or multi-tenant deployments |
| Infrastructure | Single VM | Google Kubernetes Engine |
| Database | Local PostgreSQL | Cloud SQL (PostgreSQL) |
| Scaling | Vertical | Horizontal |
| Availability | Basic | High (2+ pods) |

Quick start (single-host):

```bash
cd infrastructure/ansible
cp inventory/single_host.yml.example inventory/single_host.yml
ansible-playbook -i inventory/single_host.yml playbooks/single-host.yml
```

Quick start (GKE):

```bash
cd infrastructure/ansible
cp inventory/gcp_app.yml.example inventory/gcp_app.yml
ansible-playbook -i inventory/gcp_app.yml playbooks/gcp-app-deploy.yml
```

Deployment docs:

- [infrastructure/ansible/README.md](infrastructure/ansible/README.md)
- [infrastructure/ansible/docs/gke-deployment-guide.md](infrastructure/ansible/docs/gke-deployment-guide.md)
- [docs/single-host-ansible-deployment.md](docs/single-host-ansible-deployment.md)

## Documentation

- Workflow and business-process docs: [docs/workflows/](docs/workflows/)
- App-level technical docs: each app's `docs/` directory
- Additional operational runbooks and guides: [docs/](docs/)

## Contributing

Contributions are welcome via feature branches and pull requests.

- Do not commit directly to `main`
- Open an issue first for major changes
- Run pre-commit and relevant tests before opening a PR

## Contact

For questions or support, contact [Piet Barber](mailto:pb+GitHub@pietbarber.com).
