#!/bin/bash
# SSL Certificate Provisioning Script
#
# This script provisions Google-managed SSL certificates for the Manage2Soar
# multi-tenant deployment using the new manage2soar.com domains.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - DNS records must be pointing to Gateway IP (34.111.146.37)
#   - Appropriate GCP project permissions
#
# Usage:
#   ./setup-ssl-cert.sh
#
# This is an IaC script - commit changes and version control this file.

set -euo pipefail

# Configuration
PROJECT_ID="${GCP_PROJECT:-manage2soar}"
CERT_NAME="manage2soar-ssl-cert-v2"
OLD_CERT_NAME="manage2soar-ssl-cert"
DOMAINS="ssc.manage2soar.com,masa.manage2soar.com"
GATEWAY_NAME="manage2soar-gateway"

echo "==========================================="
echo "SSL Certificate Provisioning"
echo "==========================================="
echo "Project:     ${PROJECT_ID}"
echo "Certificate: ${CERT_NAME}"
echo "Domains:     ${DOMAINS}"
echo "==========================================="
echo

# Step 1: Create new Google-managed SSL certificate
echo "Step 1: Creating new Google-managed SSL certificate..."
if gcloud compute ssl-certificates describe "${CERT_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "✓ Certificate ${CERT_NAME} already exists"
else
    echo "Creating certificate for domains: ${DOMAINS}..."
    gcloud compute ssl-certificates create "${CERT_NAME}" \
        --domains="${DOMAINS}" \
        --global \
        --project="${PROJECT_ID}"
    echo "✓ Certificate created successfully"
fi
echo

# Step 2: Update Gateway to use new certificate
echo "Step 2: Updating Gateway to use new certificate..."
echo "Patching Gateway ${GATEWAY_NAME} in default namespace..."
kubectl patch gateway "${GATEWAY_NAME}" -n default --type='json' -p='[
  {
    "op": "replace",
    "path": "/spec/listeners/0/tls/options/networking.gke.io~1pre-shared-certs",
    "value": "'"${CERT_NAME}"'"
  }
]'
echo "✓ Gateway updated successfully"
echo

# Step 3: Check certificate provisioning status
echo "Step 3: Checking certificate provisioning status..."
echo "This can take 10-15 minutes after DNS propagation..."
echo
gcloud compute ssl-certificates describe "${CERT_NAME}" --project="${PROJECT_ID}"
echo

echo "==========================================="
echo "SSL Certificate provisioning initiated!"
echo "==========================================="
echo
echo "Monitor certificate status with:"
echo "  watch gcloud compute ssl-certificates describe ${CERT_NAME} --project=${PROJECT_ID}"
echo
echo "Certificate should transition from PROVISIONING to ACTIVE (10-15 minutes)"
echo
echo "Once ACTIVE, test with:"
echo "  curl -I https://ssc.manage2soar.com/"
echo "  curl -I https://masa.manage2soar.com/"
echo
echo "After verification, delete old certificate:"
echo "  gcloud compute ssl-certificates delete ${OLD_CERT_NAME} --project=${PROJECT_ID}"
