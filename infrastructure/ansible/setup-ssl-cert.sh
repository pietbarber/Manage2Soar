#!/bin/bash
# SSL Certificate Provisioning Script
#
# This script provisions Google-managed SSL certificates for the Manage2Soar
# multi-tenant deployment using the new manage2soar.com domains.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - DNS records must be pointing to the current Gateway IP (verify via IaC docs, e.g. gke-gateway-ingress-guide.md)
#   - Appropriate GCP project permissions
#
# Usage:
#   # Run against the default project (manage2soar):
#   ./setup-ssl-cert.sh
#
#   # Override the GCP project via environment variable (preferred IaC-friendly pattern):
#   GCP_PROJECT=my-gcp-project-id ./setup-ssl-cert.sh
#
#   If GCP_PROJECT is not set, the script defaults to the 'manage2soar' project.
#
# This is an IaC script - commit changes and version control this file.

set -euo pipefail

# Configuration
PROJECT_ID="${GCP_PROJECT:-manage2soar}"
# v2 suffix indicates this certificate is for the new manage2soar.com domains.
# The original certificate (manage2soar-ssl-cert) was for deprecated domains
# (m2s.skylinesoaring.org, m2s.midatlanticsoaring.org) and should be deleted
# after the new certificate is active.
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

# Validate Gateway exists before patching
if kubectl get gateway "${GATEWAY_NAME}" -n default >/dev/null 2>&1; then
    # Note: Assumes HTTPS listener is at index 0 in spec.listeners array.
    # If Gateway listener order changes, this path may need adjustment.
    kubectl patch gateway "${GATEWAY_NAME}" -n default --type='json' -p='[
  {
    "op": "replace",
    "path": "/spec/listeners/0/tls/options/networking.gke.io~1pre-shared-certs",
    "value": "'"${CERT_NAME}"'"
  }
]'
    echo "✓ Gateway updated successfully"
else
    echo "✗ Gateway ${GATEWAY_NAME} not found in namespace 'default'."
    echo "   Ensure the Gateway exists and is in the correct namespace, then re-run this script."
    exit 1
fi
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
