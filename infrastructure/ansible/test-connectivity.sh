#!/bin/bash
# Test Ansible Connectivity
# Validates SSH access, Ansible ping, and vault access to all managed hosts

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Ansible Connectivity Test${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check vault password file
if [ ! -f ~/.ansible_vault_pass ]; then
    echo -e "${RED}ERROR: Vault password file not found at ~/.ansible_vault_pass${NC}"
    exit 1
fi

echo -e "${YELLOW}[1/5] Testing vault access...${NC}"
VAULT_TEST_FILE="group_vars/localhost/vault.yml"
if [ ! -f "$VAULT_TEST_FILE" ]; then
    echo -e "${RED}✗ Vault test file not found: ${VAULT_TEST_FILE}${NC}"
    echo -e "${YELLOW}  Ensure you're running this script from the infrastructure/ansible directory.${NC}"
    exit 1
fi
if ansible-vault view "$VAULT_TEST_FILE" --vault-password-file ~/.ansible_vault_pass > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Vault password file works${NC}"
else
    echo -e "${RED}✗ Vault decryption failed (wrong password or corrupted vault file)${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[2/5] Testing SSH keys...${NC}"
# Check for common SSH keys (Ansible defaults to google_compute_engine for GCP)
if [ -f ~/.ssh/google_compute_engine ] || [ -f ~/.ssh/id_ed25519 ] || [ -f ~/.ssh/id_rsa ]; then
    echo -e "${GREEN}✓ SSH key found${NC}"
else
    echo -e "${RED}✗ No SSH key found (checked: google_compute_engine, id_ed25519, id_rsa)${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[3/5] Testing Ansible ping: Database server...${NC}"
if [ ! -f inventory/gcp_database.yml ]; then
    echo -e "${RED}✗ inventory/gcp_database.yml not found (copy from .example)${NC}"
    exit 1
fi
if ansible gcp_database_servers -i inventory/gcp_database.yml -m ping 2>&1 | grep -q "SUCCESS"; then
    echo -e "${GREEN}✓ m2s-database: reachable${NC}"
else
    echo -e "${RED}✗ m2s-database: unreachable${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[4/5] Testing Ansible ping: Mail server...${NC}"
if [ ! -f inventory/gcp_mail.yml ]; then
    echo -e "${RED}✗ inventory/gcp_mail.yml not found (copy from .example)${NC}"
    exit 1
fi
if ansible gcp_mail_servers -i inventory/gcp_mail.yml -m ping 2>&1 | grep -q "SUCCESS"; then
    echo -e "${GREEN}✓ m2s-mail: reachable${NC}"
else
    echo -e "${RED}✗ m2s-mail: unreachable${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[5/5] Testing fact gathering with vault...${NC}"
if ansible gcp_database_servers -i inventory/gcp_database.yml \
    -m setup -a 'filter=ansible_hostname' \
    --vault-password-file ~/.ansible_vault_pass 2>&1 | grep -q "SUCCESS"; then
    echo -e "${GREEN}✓ Can gather facts with vault access${NC}"
else
    echo -e "${RED}✗ Fact gathering failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All Connectivity Tests Passed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "You can now run Ansible playbooks:"
echo ""
echo "  # Database deployment:"
echo "  ansible-playbook -i inventory/gcp_database.yml \\"
echo "    --vault-password-file ~/.ansible_vault_pass \\"
echo "    playbooks/gcp-database.yml"
echo ""
echo "  # Mail server deployment:"
echo "  ansible-playbook -i inventory/gcp_mail.yml \\"
echo "    --vault-password-file ~/.ansible_vault_pass \\"
echo "    playbooks/gcp-mail-server.yml"
echo ""
echo "  # GKE app deployment:"
echo "  ansible-playbook -i inventory/gcp_app.yml \\"
echo "    --vault-password-file ~/.ansible_vault_pass \\"
echo "    playbooks/gcp-app-deploy.yml"
