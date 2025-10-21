# Dockerfile for Django + Gunicorn
#FROM python:3.13-slim-alpine
FROM python:3.13-slim-bookworm

WORKDIR /app

# Copy only requirements.txt for install, then remove it
COPY requirements.txt ./

# Ensure we have up-to-date OS packages (pull security fixes) and install
# minimal packages required for building wheels (adjust as needed).
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates build-essential libpq-dev curl gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=manage2soar.settings
ENV PYTHONUNBUFFERED=1

# Install Node.js (for vendoring frontend deps) and run npm vendor steps
# Use Node 18 from nodesource
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -f package.json ]; then npm ci --no-audit --no-fund; fi
RUN if [ -f package.json ]; then npm run vendor:tablesort || true; fi

# Collect static files
RUN python manage.py collectstatic --noinput

# Gunicorn entrypoint
CMD ["gunicorn", "manage2soar.wsgi:application", "--bind", "0.0.0.0:8000", "--workers=3"]
