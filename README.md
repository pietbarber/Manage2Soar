
# Manage2Soar – Soaring Club Management Platform

Manage2Soar is a modern Django 5.2.11 web application for comprehensive soaring club management. It supports members, gliders, badges, operations, analytics, instruction, notifications, and site configuration—all in one integrated platform.

## Quick Start for Local Development

### Prerequisites
- Python 3.12+
- PostgreSQL 12+ (running locally or accessible via network)
- Git

### Setup Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/pietbarber/Manage2Soar.git
   cd Manage2Soar
   ```

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up PostgreSQL database:**
   ```bash
   # Create database and user (adjust as needed for your PostgreSQL setup)
   sudo -u postgres psql
   ```
   ```sql
   CREATE DATABASE manage2soar;
   CREATE USER m2s WITH PASSWORD 'your-password-here' CREATEDB;
   ALTER ROLE m2s SET client_encoding TO 'utf8';
   ALTER ROLE m2s SET default_transaction_isolation TO 'read committed';
   ALTER ROLE m2s SET timezone TO 'UTC';
   GRANT ALL PRIVILEGES ON DATABASE manage2soar TO m2s;
   \q
   ```
   ```bash
   # Grant schema-level permissions (required for PostgreSQL 15+)
   sudo -u postgres psql -d manage2soar
   ```
   ```sql
   GRANT ALL PRIVILEGES ON SCHEMA public TO m2s;
   GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO m2s;
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO m2s;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO m2s;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO m2s;
   \q
   ```

5. **Configure environment variables:**
   ```bash
   # Copy the example .env file
   cp .env.example .env

   # Edit .env and set your values (minimum required):
   # - DJANGO_SECRET_KEY (generate a new one)
   # - DB_PASSWORD (match the PostgreSQL password you created)
   ```

6. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

7. **Create a superuser:**
   ```bash
   python manage.py createsuperuser
   ```

8. **Run the development server:**
   ```bash
   # IMPORTANT: Use port 8001 to avoid HSTS caching issues on port 8000
   python manage.py runserver 127.0.0.1:8001
   ```

9. **Access the application:**
   - Open http://127.0.0.1:8001 in your browser
   - Log in with your superuser credentials
   - Visit http://127.0.0.1:8001/admin to configure site settings

### Troubleshooting

**"no password supplied" database error:**
- Make sure you created the `.env` file from `.env.example`
- Verify `DB_PASSWORD` in `.env` matches your PostgreSQL user password
- Check that PostgreSQL is running: `sudo systemctl status postgresql`

**"command not found" errors:**
- Always activate the virtual environment first: `source .venv/bin/activate`

**Port 8000 vs 8001:**
- Always use port 8001 for local development
- Port 8000 has HSTS caching that can interfere with HTTP development

## Major Apps
- `members`: Membership management, profiles, roles, and permissions
- `logsheet`: Flight logging, glider operations, and analytics data source
- `duty_roster`: Scheduling for duty officers, instructors, and tow pilots
- `instructors`: Training, lesson tracking, and instructor tools
- `analytics`: Read-only charts and club statistics
- `cms`: Dynamic homepage and content management (public/member views)
- `knowledgetest`: Knowledge test and quiz system
- `notifications`: Automated and ad-hoc email notifications
- `siteconfig`: Club/site configuration (admin-only)

## Key Features
- Secure Google OAuth2 login (with Django fallback)
- Role-based access for all club roles (admin, instructor, member, etc.)
- **Progressive Web App (PWA) with offline support** - Duty officers can log flights even without internet connectivity (Issue #315)
- **Configurable membership statuses** - Clubs can customize their membership types (Issue #169)
- **Configurable test presets** - Knowledge test presets managed via Django admin (Issue #135)
- Member profiles with bios, photos, badges, and qualifications
- SSA badge management and badge board
- Glider fleet and rental management
- QR-coded vCard contact cards
- Rich HTML content and image uploads (tinymce)
- Flight log integration with analytics and duty roster
- Automated and manual notifications
- Custom error pages and responsive UI (Bootstrap 5)
- Per-app documentation and extensible architecture

## Project Conventions
- All apps have `models.py`, `views.py`, `admin.py`, `urls.py`, and `tests.py`
- Tests use `pytest` and `pytest-django` with coverage reporting
- Homepage (`/`) serves public or member content based on user status (no redirect)
- Use slugs like `"home"` (public) and `"member-home"` (member) in CMS
- Site configuration is admin-only (via Django admin)
- Data flows between apps via Django ORM and signals
- See per-app `docs/` and main `README.md` for details

## Tech Stack

### Backend
- **Python 3.12**
- **Django 5.2.11**
- **PostgreSQL** (with `psycopg2-binary`)

### Frontend
- **Bootstrap 5** (via CDN) - Modern responsive UI framework
- **django-tinymce** (WYSIWYG editor)
- **Native Bootstrap form rendering** - Professional form styling without third-party dependencies

### Core Python/Django Packages
- **Pillow** (image processing)
- **qrcode** (QR code generation)
- **vobject** (vCard/iCalendar support)
- **python-dotenv** (environment variable management)
- **django-reversion** (object versioning)
- **django-htmx** (progressive enhancement)
- **pydenticon** (avatar generation)
- **requests** (HTTP requests)
- **pytz** (timezone support)
- **social-auth-app-django** (social authentication)

### Testing & Dev Tools
- **pytest-django**
- **pytest**

### System Requirements
- No additional system packages required - all dependencies are Python packages


### Deployment & Cloud
- **Ansible Automation:** Fully automated deployment via Ansible playbooks for both single-host and GKE environments
- **Kubernetes-ready:** Production-tested on Google Kubernetes Engine (GKE) with 2-pod deployments
- **GCP Support:** Integrated with Cloud SQL, GCR, Cloud Storage, and Secret Manager
- **Multi-Tenant:** Supports deploying multiple club instances on shared infrastructure
- See [Production Deployment](#-production-deployment) below for details

### Notes
- All Python dependencies are listed in `requirements.txt`.
- Database schemas are documented using Mermaid diagrams in each app's documentation.

# Manage2Soar – Duty Roster & Operations Management

Welcome to the Manage2Soar duty roster and operations management system. This Django-based application streamlines the scheduling and coordination of club operations, including both scheduled and ad-hoc flying days.

## Source-of-truth Membership Management
 - All membership types, contact information
 - Membership profile photo,
 - Flight ratings, club qualifications, SSA badges earned
 - Member Biographies including inline images and rich text formatting.

## Full-Featured Flight Operations Logs
 - All operations are logged by a duty officer with a nice web interface
 -- include takeoff time, landing time, release height, glider, pilot, instructor.
 -- Any errors or missing data are announced to the duty officer.
 - **Offline-capable PWA**: Add, copy, launch, land, and delete flights even without internet
 -- Changes sync automatically when connectivity returns
 -- Reference data (members, gliders) cached locally for offline form rendering
 - Closeout including finances, who paid, who is on account, etc.
 - Closeout including Tow Plane information, safety issues, Operation Essay.
 -- Log maintenance issues, indicate a glider is grounded.
 - Email sent to the duty crew the night before the operations reminding them of
 -- offline equipment
 -- duty crew participants
 -- upcoming maintenance deadlines (transponder, parachutes, etc).
 - Review of past flight operations by any club member.

## Instruction Syllabus
 - Managed by any instructor in the club.
 - Syllabus contains broad sections for phases of flight training
 - Each syllabus item has
 -- a rich HTML editor text field describing what is expected
 -- relevant sections of 14 CFR highlighted as required for solo or ratings

## Instruction Reports Based on Student Flying
 - Instructors are given opportunity to log flight instruction
 - Instructors can give members qualifications based on training
 - Instructors report on recent flight instruction sessions with:
 -- performance grading for all items in the training syllabus
 -- opportunity for writing an essay to describe the lessons learned.

## Duty Roster and Operations Calendar Management
 - Roster manager manages the operations calendar.
 - Duty_roster allows members to state their volunteer preferences.
 -- Blackout dates (i have a conference, vaccation, etc)
 -- Members can mark themselves unavailable for any duty indefinitely.
 - Operations Calendar is populated with random selection of capable members
 -- based on their blackout preferences
 -- based on the operational need
 -- does not schedule members more than a certain number of times per month.

## Operations Calendar
 - Any member can summon members for an ad-hoc operations date
 -- Email sent to club indicating ad-hoc operations on a certain date.
 -- tow pilots can sign up to tow.
 -- duty officers can sign up to be the operations officer.
 -- if those two conditions are met, email is sent to members indicating operations are a go.

## Charts and Analytics
 - Several varieties of charts and graphs can be displayed for your club's statistics
 -- Flights to date this year
 -- Compare this year to previous years
 -- Show usage of each glider in the club
 -- Show how many flights each user is getting

## Knowledge Tests
 - Maintain a test bank of your written test questions
 -- Useful for pre-solo written test
 -- also useful for training wing runners or duty officers

# 🛠️ Installation & Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/pietbarber/manage2soar.git
   cd manage2soar
   ```

### Option A: Automated Setup (Recommended)
2. **Run the setup script**:
   ```bash
   ./setup-dev.sh
   ```
   This automatically sets up virtual environment, dependencies, security tools, and database.

### Option B: Manual Setup
2. **Create a Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Development Tools** (Required for contributors):
   ```bash
   # Install pre-commit hooks for security scanning
   pip install pre-commit
   pre-commit install

   # Verify security tools are working
   bandit --version
   pre-commit run --all-files  # Optional: run all checks once
   ```

5. **Apply Migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create a Superuser**:
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the Development Server**:
   ```bash
   python manage.py runserver
   ```

# 🚀 Production Deployment

Manage2Soar offers **fully automated deployment** via Ansible playbooks. Choose the deployment option that fits your club:

| Feature | Single-Host | GKE (Kubernetes) |
|---------|-------------|------------------|
| **Best For** | Small clubs, simple setup | Large clubs, multi-tenant |
| **Infrastructure** | Single VM (Gunicorn/systemd) | Google Kubernetes Engine |
| **Database** | Local PostgreSQL | Cloud SQL (PostgreSQL) |
| **Scaling** | Vertical only | Horizontal pod scaling |
| **High Availability** | No | Yes (2+ pods) |
| **Setup Complexity** | Low | Medium |

### Quick Start: Single-Host Deployment
```bash
cd infrastructure/ansible
cp inventory/single_host.yml.example inventory/single_host.yml
# Edit inventory/single_host.yml with your server details
ansible-playbook -i inventory/single_host.yml playbooks/single-host.yml
```

### Quick Start: GKE Deployment
```bash
cd infrastructure/ansible
cp inventory/gcp_app.yml.example inventory/gcp_app.yml
# Edit inventory/gcp_app.yml and related group_vars/vault files with your GCP project and cluster details
ansible-playbook -i inventory/gcp_app.yml playbooks/gcp-app-deploy.yml
```

### 📚 Deployment Documentation
- **[infrastructure/ansible/README.md](infrastructure/ansible/README.md)** – Deployment overview and comparison
- **[GKE Deployment Guide](infrastructure/ansible/docs/gke-deployment-guide.md)** – Comprehensive GKE deployment guide
- **[Single-Host Guide](docs/single-host-ansible-deployment.md)** – Single VM deployment details

## 🔒 **Security & Code Quality**

This project includes comprehensive security scanning and code quality tools:

- **Pre-commit Hooks**: Automatic security scans before every commit
- **GitHub Actions**: CI/CD pipeline with security gates  
- **Bandit**: Python security vulnerability scanning
- **Safety & pip-audit**: Dependency vulnerability checking
- **Code Formatting**: Black, isort, django-upgrade for consistent code style

### **For Contributors**
Pre-commit hooks are **required** for development. After cloning:
```bash
pip install pre-commit
pre-commit install
```

The hooks will automatically:
- Scan for security vulnerabilities
- Check for secrets in code
- Format Python code consistently
- Validate configuration files

### **For Forkers**
All security workflows are included and will work automatically:
- ✅ GitHub Actions workflows enabled by default
- ✅ No external services or secrets required  
- ✅ All tools install from public PyPI packages
- ⚠️ **Important**: Run `pre-commit install` after cloning to enable local security checks

## 📄 Documentation

### **📋 Workflow Documentation**
**NEW!** Comprehensive workflow documentation with visual process flows is available at **[docs/workflows/](docs/workflows/)** - perfect for new users and system understanding.

### **🔧 Technical Documentation**
Extensive technical documentation is available in each app's `docs/` folder (e.g., `members/docs/README.md`, `logsheet/docs/README.md`, etc.) and in this main `README.md`. For details on models, workflows, and integration, see the per-app docs and the project root documentation.

## 🤝 Contributing

We welcome contributions! Please fork the repository and submit a pull request. For major changes, open an issue first to discuss proposed modifications. This code is being written with the possibility that other clubs can take the code and run with it.

## 📧 Contact

For questions or support, please contact [Piet Barber](mailto:pb+GitHub@pietbarber.com)

---

Feel free to customize the contact information and any other sections to better fit your needs. Let me know if you'd like assistance with anything else!
