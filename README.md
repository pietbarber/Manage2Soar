# Manage2Soar Soaring Club Member Portal

This is a Django-based web application for managing the members, gliders, badges, and operations of any soaring club.

## Features

- Secure Google OAuth2 login system (with support for traditional login)
- Role-based access for administrators, instructors, duty officers, etc.
- Member profiles with bios, contact info, and profile photos
- SSA Badge management with badge board display
- Rich HTML biographies with image upload support
- Glider fleet database (with pictures and rental info)
- QR-coded contact cards (vCard)
- Custom error pages and responsive UI with Bootstrap
- Clean roadmap and continuous development

## Tech Stack

### Backend
- **Python 3.12**
- **Django 5.1**
- **PostgreSQL** (with `psycopg2-binary`)

### Frontend
- **Bootstrap 5** (via CDN)
- **django-crispy-forms**
- **crispy-bootstrap4**
- **django-tinymce** (WYSIWYG editor)

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
- **graphviz** (required for ERD generation via `generate_erds.py`)

### Notes
- All Python dependencies are listed in `requirements.txt`.
- System package `graphviz` must be installed separately (e.g., `sudo apt install graphviz`).

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
   python3 -m venv env
   source env/bin/activate
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

(coming soon!)

## 🤝 Contributing

We welcome contributions! Please fork the repository and submit a pull request. For major changes, open an issue first to discuss proposed modifications. This code is being written with the possibility that other clubs can take the code and run with it. 

## 📧 Contact

For questions or support, please contact [Piet Barber](mailto:pb+GitHub@pietbarber.com)

---

Feel free to customize the contact information and any other sections to better fit your needs. Let me know if you'd like assistance with anything else! 