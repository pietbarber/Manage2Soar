
# Manage2Soar – Soaring Club Management Platform

Manage2Soar is a modern Django 5.2 web application for comprehensive soaring club management. It supports members, gliders, badges, operations, analytics, instruction, notifications, and site configuration—all in one integrated platform.

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
- **Django 5.2**
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
- **Kubernetes-ready:** This project includes manifests and configuration for Kubernetes deployment.
- **GCP Support:** Out-of-the-box configuration for Google Cloud Platform (GCP) is provided; see `k8s-deployment.yaml` and related files for details.

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

2. **Create a Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Apply Migrations**:
   ```bash
   python manage.py migrate
   ```

5. **Create a Superuser**:
   ```bash
   python manage.py createsuperuser
   ```

6. **Run the Development Server**:
   ```bash
   python manage.py runserver
   ```

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