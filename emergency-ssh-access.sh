#!/bin/bash
# Emergency SSH Access from New Location
#
# This script adds your current public IP to the GCP firewall rules
# for SSH access to m2s-database and m2s-mail servers.
# It modifies firewall sourceRanges only — no SSH keys are touched.
# Remember to remove your IP when you return home.
#
# Usage from ANYWHERE with gcloud installed:
#   ./emergency-ssh-access.sh
#
# Or from ANY computer with a browser:
#   1. Go to: https://shell.cloud.google.com
#   2. Download and review the script before running:
#        TAG_OR_COMMIT="main"  # or pin to a specific tag/commit
#        curl -s -o emergency-ssh-access.sh "https://raw.githubusercontent.com/pietbarber/Manage2Soar/${TAG_OR_COMMIT}/emergency-ssh-access.sh"
#        less emergency-ssh-access.sh   # review before executing
#        bash emergency-ssh-access.sh
#
# Or the safest manual method:
#   1. Get your IP: curl ifconfig.me
#   2. Go to: https://console.cloud.google.com/net-security/firewall-manager/firewall-policies/list?project=manage2soar
#   3. Edit: m2s-database-allow-ssh and m2s-mail-allow-ssh
#   4. Add your IP with /32 suffix (IPv4) or /128 suffix (IPv6)

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT_ID="manage2soar"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Emergency SSH Access Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Get current public IP
echo -e "${YELLOW}Getting your current public IP...${NC}"
CURRENT_IP=$(curl -s https://ifconfig.me)
if [ -z "$CURRENT_IP" ]; then
    echo -e "${RED}ERROR: Could not determine public IP${NC}"
    echo "Try manually: curl https://ifconfig.me"
    exit 1
fi
# Validate IP format (IPv4 or IPv6) and determine CIDR
if echo "$CURRENT_IP" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
    IP_CIDR="${CURRENT_IP}/32"
elif echo "$CURRENT_IP" | grep -qE '^[0-9a-fA-F:]+$'; then
    IP_CIDR="${CURRENT_IP}/128"
else
    echo -e "${RED}ERROR: Invalid IP address received: ${CURRENT_IP}${NC}"
    exit 1
fi
echo -e "Your IP: ${GREEN}${CURRENT_IP}${NC} (CIDR: ${IP_CIDR})"
echo ""

# Check if already allowed
echo -e "${YELLOW}Checking current firewall rules...${NC}"
DB_RULE_IPS=$(gcloud compute firewall-rules describe m2s-database-allow-ssh \
    --project=$PROJECT_ID --format="value(sourceRanges)" 2>/dev/null || echo "")
MAIL_RULE_IPS=$(gcloud compute firewall-rules describe m2s-mail-allow-ssh \
    --project=$PROJECT_ID --format="value(sourceRanges)" 2>/dev/null || echo "")

if echo "$DB_RULE_IPS" | grep -Fq "${IP_CIDR}"; then
    echo -e "${GREEN}✓ Your IP is already allowed for database server${NC}"
    DB_NEEDS_UPDATE=false
else
    echo -e "${YELLOW}⚠ Your IP is NOT allowed for database server${NC}"
    DB_NEEDS_UPDATE=true
fi

if echo "$MAIL_RULE_IPS" | grep -Fq "${IP_CIDR}"; then
    echo -e "${GREEN}✓ Your IP is already allowed for mail server${NC}"
    MAIL_NEEDS_UPDATE=false
else
    echo -e "${YELLOW}⚠ Your IP is NOT allowed for mail server${NC}"
    MAIL_NEEDS_UPDATE=true
fi

if [ "$DB_NEEDS_UPDATE" = false ] && [ "$MAIL_NEEDS_UPDATE" = false ]; then
    echo ""
    echo -e "${GREEN}No changes needed - you already have access!${NC}"
    exit 0
fi

# Confirm update
echo ""
echo -e "${YELLOW}This will ADD your IP to the firewall rules.${NC}"
echo "Existing IPs will be PRESERVED."
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

# Update database rule
if [ "$DB_NEEDS_UPDATE" = true ]; then
    echo ""
    echo -e "${YELLOW}Updating m2s-database-allow-ssh...${NC}"

    # Get existing IPs and add new one
    EXISTING_IPS=$(echo "$DB_RULE_IPS" | tr ';' ',' | sed 's/,$//')
    if [ -n "$EXISTING_IPS" ]; then
        NEW_IPS="${EXISTING_IPS},${IP_CIDR}"
    else
        NEW_IPS="${IP_CIDR}"
    fi

    gcloud compute firewall-rules update m2s-database-allow-ssh \
        --project=$PROJECT_ID \
        --source-ranges="$NEW_IPS" \
        --quiet

    echo -e "${GREEN}✓ Database firewall rule updated${NC}"
fi

# Update mail rule
if [ "$MAIL_NEEDS_UPDATE" = true ]; then
    echo ""
    echo -e "${YELLOW}Updating m2s-mail-allow-ssh...${NC}"

    # Get existing IPs and add new one
    EXISTING_IPS=$(echo "$MAIL_RULE_IPS" | tr ';' ',' | sed 's/,$//')
    if [ -n "$EXISTING_IPS" ]; then
        NEW_IPS="${EXISTING_IPS},${IP_CIDR}"
    else
        NEW_IPS="${IP_CIDR}"
    fi

    gcloud compute firewall-rules update m2s-mail-allow-ssh \
        --project=$PROJECT_ID \
        --source-ranges="$NEW_IPS" \
        --quiet

    echo -e "${GREEN}✓ Mail server firewall rule updated${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Emergency Access Granted!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "You can now SSH to:"
echo "  gcloud compute ssh m2s-database --zone=us-east1-b --project=manage2soar"
echo "  gcloud compute ssh m2s-mail --zone=us-east1-b --project=manage2soar"
echo ""
echo "Or use Ansible:"
echo "  cd infrastructure/ansible"
echo "  ansible gcp_database_servers -i inventory/gcp_database.yml -m ping"
echo ""
echo -e "${YELLOW}Remember to REMOVE this IP when you return home!${NC}"
echo "Run: gcloud compute firewall-rules update m2s-database-allow-ssh \\"
echo "       --source-ranges=LIST_WITHOUT_THIS_IP --project=manage2soar"
