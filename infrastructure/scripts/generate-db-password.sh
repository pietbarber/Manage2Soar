#!/bin/bash
# generate-db-password.sh
# Generates a secure database password
#
# Usage:
#   ./generate-db-password.sh
#   ./generate-db-password.sh --length 32
#
# Output: A secure random password suitable for PostgreSQL

set -euo pipefail

# Default length
LENGTH=${1:-32}

# Handle --length argument
if [[ "${1:-}" == "--length" ]]; then
    LENGTH="${2:-32}"
fi

# Generate password using openssl (available on most systems)
# Using alphanumeric + some special chars that are safe for most contexts
PASSWORD=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c "$LENGTH")

# Ensure we got enough characters
if [[ ${#PASSWORD} -lt $LENGTH ]]; then
    # Fallback using /dev/urandom
    PASSWORD=$(head -c 64 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c "$LENGTH")
fi

echo "$PASSWORD"
