# Dockerfile for Django + Gunicorn
FROM python:3.13-slim-alpine
#FROM python:3.13-slim-bullseye

WORKDIR /app


# Copy only requirements.txt for install, then remove it
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=manage2soar.settings
ENV PYTHONUNBUFFERED=1

# Collect static files
RUN python manage.py collectstatic --noinput

# Gunicorn entrypoint
CMD ["gunicorn", "manage2soar.wsgi:application", "--bind", "0.0.0.0:8000", "--workers=3"]
