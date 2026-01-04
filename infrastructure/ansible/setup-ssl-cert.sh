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
# Comma-separated list of domains for the certificate. Add new tenants here or
# override via CERT_DOMAINS environment variable.
DOMAINS="${CERT_DOMAINS:-ssc.manage2soar.com,masa.manage2soar.com}"
# Gateway name - override via GATEWAY_NAME environment variable if using a different Gateway.
GATEWAY_NAME="${GATEWAY_NAME:-manage2soar-gateway}"

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

# Validate kubectl is installed
if ! command -v kubectl >/dev/null 2>&1; then
    echo "✗ Error: kubectl is required but not installed."
    echo "   Install kubectl before running this script: https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi

# Validate jq is installed (needed for dynamic listener detection)
if ! command -v jq >/dev/null 2>&1; then
    echo "✗ Error: jq is required but not installed."
    echo "   Install jq before running this script: https://stedolan.github.io/jq/download/"
    exit 1
fi

# Validate Gateway exists before patching
if kubectl get gateway "${GATEWAY_NAME}" -n default >/dev/null 2>&1; then
    # Determine the index of the HTTPS listener dynamically to avoid relying on fragile ordering.
    HTTPS_LISTENER_INDEX="$(kubectl get gateway "${GATEWAY_NAME}" -n default -o json \
        | jq -r '
            .spec.listeners
            | to_entries[]
            | select(.value.protocol == "HTTPS")
            | .key
        ' | head -n 1)"

    if [[ -z "${HTTPS_LISTENER_INDEX}" ]]; then
        echo "✗ No HTTPS listener found on Gateway ${GATEWAY_NAME} in namespace 'default'."
        echo "   Ensure the Gateway has an HTTPS listener defined before running this script."
        exit 1
    fi

    echo "Using HTTPS listener at index ${HTTPS_LISTENER_INDEX} for certificate update."

    kubectl patch gateway "${GATEWAY_NAME}" -n default --type='json' -p='[
  {
    "op": "replace",
    "path": "/spec/listeners/'"${HTTPS_LISTENER_INDEX}"'/tls/options/networking.gke.io~1pre-shared-certs",
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
