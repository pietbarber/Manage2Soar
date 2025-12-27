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
LENGTH=32

# Handle --length argument or positional length
if [[ "${1:-}" == "--length" ]]; then
    LENGTH="${2:-32}"
elif [[ -n "${1:-}" ]]; then
    LENGTH="$1"
fi

# Validate LENGTH is a positive integer
if ! [[ "$LENGTH" =~ ^[0-9]+$ ]] || [ "$LENGTH" -le 0 ]; then
    echo "Error: LENGTH must be a positive integer (got: '$LENGTH')" >&2
    exit 1
fi

# Generate password using openssl (available on most systems)
# Using alphanumeric only for maximum compatibility with database connection strings
# Note: 32-char alphanumeric (62 chars/position) provides ~190 bits of entropy
PASSWORD=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c "$LENGTH")

# Ensure we got enough characters
if [[ ${#PASSWORD} -lt $LENGTH ]]; then
    # Fallback using /dev/urandom
    PASSWORD=$(head -c 64 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c "$LENGTH")

    # Final validation: fail if we still don't have enough characters
    if [[ ${#PASSWORD} -lt $LENGTH ]]; then
        echo "Error: Could not generate password of sufficient length" >&2
        exit 1
    fi
fi

echo "$PASSWORD"
