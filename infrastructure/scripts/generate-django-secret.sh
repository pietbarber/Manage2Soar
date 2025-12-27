#!/bin/bash
# generate-django-secret.sh
# Generates a secure Django SECRET_KEY
#
# Usage:
#   ./generate-django-secret.sh
#   ./generate-django-secret.sh --length 64
#
# Output: A URL-safe base64-encoded random string suitable for Django SECRET_KEY

set -euo pipefail

# Default length (Django recommends at least 50 characters)
LENGTH=${1:-50}

# Handle --length argument
if [[ "${1:-}" == "--length" ]]; then
    LENGTH="${2:-50}"
fi

# Validate LENGTH is a positive integer
if ! [[ "$LENGTH" =~ ^[0-9]+$ ]] || [ "$LENGTH" -le 0 ]; then
    echo "Error: LENGTH must be a positive integer (got: '$LENGTH')." >&2
    exit 1
fi

# Generate the secret key
# Using /dev/urandom with base64 encoding, filtering to URL-safe characters
SECRET_KEY=$(head -c 64 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9!@#$%^&*(-_=+)' | head -c "$LENGTH")

# Ensure we got enough characters
if [[ ${#SECRET_KEY} -lt $LENGTH ]]; then
    # Fallback: generate more and try again
    SECRET_KEY=$(openssl rand -base64 128 | tr -dc 'a-zA-Z0-9!@#$%^&*(-_=+)' | head -c "$LENGTH")
    # Final check: if still too short, fail explicitly
    if [[ ${#SECRET_KEY} -lt $LENGTH ]]; then
        echo "Error: Could not generate secret of sufficient length (requested $LENGTH, got ${#SECRET_KEY})." >&2
        exit 1
    fi
fi

echo "$SECRET_KEY"
