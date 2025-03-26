# Skyline Soaring Club Member Portal

This is a Django-based web application for managing the members, gliders, badges, and operations of the Skyline Soaring Club.

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

- Python 3.12 / Django 5.1
- PostgreSQL
- Bootstrap 5
- TinyMCE rich text editor
- Pillow (for image resizing)
- qrcode and vobject (for QR/vCard support)

## Getting Started

1. Clone this repository:

   ```bash
   git clone https://github.com/pietbarber/skylinesoaring.git
   cd skylinesoaring
   ```

2. Set up your virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file for your secret keys (see `.env.example`).

4. Apply migrations:

   ```bash
   ./manage.py migrate
   ```

5. Run the development server:

   ```bash
   ./manage.py runserver
   ```

6. Log in via `/members/login/` or set up a superuser:

   ```bash
   ./manage.py createsuperuser
   ```

## Roadmap

See `roadmap.md` (or check pinned roadmap in ChatGPT thread).

## License

Creative Commons License

---

Built with ✈️, ⛅, and lots of glider love.

