# Dockerfile for Nginx reverse proxy
FROM nginx:1.25-alpine

COPY nginx.conf /etc/nginx/nginx.conf

# SSL certs will be mounted via Kubernetes secrets
