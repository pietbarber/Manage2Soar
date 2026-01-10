# Dockerfile for Django + Gunicorn
#FROM python:3.13-slim-alpine
FROM python:3.14-slim-bookworm

WORKDIR /app

# Copy only requirements.txt for install, then remove it
COPY requirements.txt ./

# Ensure we have up-to-date OS packages (pull security fixes) and install
# minimal packages required for building wheels (adjust as needed).
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates build-essential libpq-dev libffi-dev curl gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

COPY . .

# Generate build hash from git commit or timestamp for cache busting
# This is used by the service worker to version its cache
ARG BUILD_HASH
ENV BUILD_HASH=${BUILD_HASH}

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

# Static files are collected post-deployment by Ansible with GCS credentials
# (see roles/gke-deploy/tasks/deploy.yml)

# Gunicorn entrypoint
# Increased timeout to 60s to handle slow SMTP server connections (mail server has 10s connection delay)
CMD ["gunicorn", "manage2soar.wsgi:application", "--bind", "0.0.0.0:8000", "--workers=3", "--timeout=60"]
