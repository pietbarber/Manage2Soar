#!/bin/bash
# initialize-vault-secrets.sh
# Generates all required secrets and creates an Ansible vault file
#
# Usage:
#   ./initialize-vault-secrets.sh [vault-file-path]
#
# This script:
# 1. Generates all required secrets (Django key, DB passwords)
# 2. Creates or updates an Ansible vault file
# 3. Encrypts the file with ansible-vault
#
# Prerequisites:
#   - ansible-vault must be installed
#   - Either ANSIBLE_VAULT_PASSWORD_FILE env var or ~/.ansible_vault_pass must exist

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_FILE="${1:-${SCRIPT_DIR}/../ansible/group_vars/gcp_database/vault.yml}"
VAULT_DIR="$(dirname "$VAULT_FILE")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}M2S Secret Initialization${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check for vault password file
VAULT_PASS_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-$HOME/.ansible_vault_pass}"
if [[ ! -f "$VAULT_PASS_FILE" ]]; then
    echo -e "${YELLOW}Warning: Vault password file not found at: $VAULT_PASS_FILE${NC}"
    echo ""
    echo "To create one:"
    echo "  echo 'your-secure-vault-password' > $VAULT_PASS_FILE"
    echo "  chmod 600 $VAULT_PASS_FILE"
    echo ""
    read -p "Would you like to create one now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Generating vault password...${NC}"
        VAULT_PASS=$(openssl rand -base64 32)
        echo "$VAULT_PASS" > "$VAULT_PASS_FILE"
        chmod 600 "$VAULT_PASS_FILE"
        echo -e "${GREEN}Created: $VAULT_PASS_FILE${NC}"
        echo -e "${RED}IMPORTANT: Save this password securely! You cannot recover encrypted data without it.${NC}"
    else
        echo -e "${RED}Cannot proceed without vault password file.${NC}"
        exit 1
    fi
fi

# Ensure vault directory exists
mkdir -p "$VAULT_DIR"

# Check if vault file already exists
if [[ -f "$VAULT_FILE" ]]; then
    echo -e "${YELLOW}Vault file already exists: $VAULT_FILE${NC}"
    read -p "Overwrite existing secrets? This cannot be undone! (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo ""
echo "Generating secrets..."
echo ""

DJANGO_SECRET_SCRIPT="$SCRIPT_DIR/generate-django-secret.sh"
DB_PASSWORD_SCRIPT="$SCRIPT_DIR/generate-db-password.sh"

# Verify generator scripts exist and are executable
for script in "$DJANGO_SECRET_SCRIPT" "$DB_PASSWORD_SCRIPT"; do
    if [[ ! -f "$script" ]]; then
        echo -e "${RED}Error: Required script not found: $script${NC}"
        echo "Ensure this script exists in the infrastructure/scripts directory."
        exit 1
    fi
    if [[ ! -x "$script" ]]; then
        echo -e "${RED}Error: Script is not executable: $script${NC}"
        echo "Make it executable with: chmod +x \"$script\""
        exit 1
    fi
done

# Generate secrets
echo -e "${YELLOW}Note:${NC} SMTP password is for external mail relay authentication (if configured)."
DJANGO_SECRET=$("$DJANGO_SECRET_SCRIPT")
DB_PASSWORD=$("$DB_PASSWORD_SCRIPT")
SMTP_PASSWORD=$("$DB_PASSWORD_SCRIPT" --length 24)

echo -e "${GREEN}✓${NC} Django SECRET_KEY generated (${#DJANGO_SECRET} chars)"
echo -e "${GREEN}✓${NC} PostgreSQL password generated (${#DB_PASSWORD} chars)"
echo -e "${GREEN}✓${NC} SMTP password generated (${#SMTP_PASSWORD} chars) - for mail relay"

# Prompt for tenant configuration
echo ""
echo "Multi-tenant database configuration:"
read -p "How many tenants/clubs? (0 for single-tenant): " TENANT_COUNT

while [[ ! "$TENANT_COUNT" =~ ^[0-9]+$ ]]; do
    echo -e "${RED}Error: Please enter a non-negative integer for the tenant count.${NC}"
    read -p "$(echo -e "${YELLOW}How many tenants/clubs? (0 for single-tenant): ${NC}")" TENANT_COUNT
done

TENANT_SECRETS=""
if [[ "$TENANT_COUNT" -gt 0 ]]; then
    # Note: Only iterate when TENANT_COUNT > 0; seq 1 0 behavior varies by shell.
    # When TENANT_COUNT is 0, the for loop produces no iterations (seq 1 0 outputs nothing
    # in bash), so TENANT_SECRETS remains empty, which is correct for single-tenant mode.
    for i in $(seq 1 "$TENANT_COUNT"); do
        while true; do
            read -p "  Tenant $i prefix (e.g., ssc, masa): " TENANT_PREFIX
            if [[ "$TENANT_PREFIX" =~ ^[A-Za-z0-9_]+$ ]]; then
                break
            fi
            echo -e "  ${RED}Error:${NC} Tenant prefix may only contain letters, numbers, and underscores (_). Please try again.\"
        done
        TENANT_PASS=$(\"$SCRIPT_DIR/generate-db-password.sh\") || {
            echo -e \"  ${RED}Error: Failed to generate password for tenant: $TENANT_PREFIX${NC}\"
            exit 1
        }
        TENANT_SECRETS="${TENANT_SECRETS}vault_postgresql_password_${TENANT_PREFIX}: \"${TENANT_PASS}\""$'\n'
        echo -e "  ${GREEN}✓${NC} Generated password for tenant: $TENANT_PREFIX"
    done
fi

# Create the vault file content
# Note: TENANT_SECRETS is an empty string when TENANT_COUNT is 0 (single-tenant mode), so the
#       tenant section expands to just a blank line in the generated YAML. When tenants exist,
#       each entry ends with a newline (line 126), and then line 152 adds the TENANT_SECRETS
#       expansion, resulting in a trailing blank line before the comments section. This trailing
#       newline is an artifact of the string concatenation pattern and is harmless in YAML.
cat > "$VAULT_FILE" << EOF
# M2S Ansible Vault Secrets
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# NEVER commit this file to version control!
# This file should be encrypted with ansible-vault.
---
# Django secret key
vault_django_secret_key: "${DJANGO_SECRET}"

# PostgreSQL password (single-tenant mode)
vault_postgresql_password: "${DB_PASSWORD}"

# SMTP password (for mail server authentication)
vault_smtp_password: "${SMTP_PASSWORD}"

# Tenant-specific passwords (multi-tenant mode)
${TENANT_SECRETS}
# Optional: Google OAuth credentials
# vault_google_oauth_client_id: "your-client-id.apps.googleusercontent.com"
# vault_google_oauth_client_secret: "your-client-secret"

# Optional: External SMTP relay credentials
# vault_smtp_relay_username: "your-smtp-username"
# vault_smtp_relay_password: "your-smtp-password"
EOF

echo ""
echo "Encrypting vault file with ansible-vault..."

# Encrypt the vault file
ansible-vault encrypt "$VAULT_FILE" --vault-password-file "$VAULT_PASS_FILE"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Secrets initialized successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Vault file: $VAULT_FILE"
echo "Vault password file: $VAULT_PASS_FILE"
echo ""
echo "To view secrets:"
echo "  ansible-vault view $VAULT_FILE --vault-password-file $VAULT_PASS_FILE"
echo ""
echo "To edit secrets:"
echo "  ansible-vault edit $VAULT_FILE --vault-password-file $VAULT_PASS_FILE"
echo ""
echo -e "${RED}IMPORTANT: Never commit these files to version control!${NC}"
