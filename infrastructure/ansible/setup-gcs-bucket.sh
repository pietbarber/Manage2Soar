#!/bin/bash
# GCS Bucket Setup Script
#
# This script provisions Google Cloud Storage bucket and IAM permissions
# for the Manage2Soar multi-tenant deployment.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - Appropriate GCP project permissions
#
# Usage:
#   ./setup-gcs-bucket.sh
#
# This is an IaC script - commit changes and version control this file.

set -euo pipefail

# Configuration
PROJECT_ID="${GCP_PROJECT:-manage2soar}"
BUCKET_NAME="${GCS_BUCKET_NAME:-manage2soar}"
LOCATION="${GCS_LOCATION:-us-east1}"
SERVICE_ACCOUNT="${GCS_SERVICE_ACCOUNT:-django@skyline-soaring-storage.iam.gserviceaccount.com}"

echo "==========================================="
echo "GCS Bucket Setup for Manage2Soar"
echo "==========================================="
echo "Project:         ${PROJECT_ID}"
echo "Bucket:          gs://${BUCKET_NAME}"
echo "Location:        ${LOCATION}"
echo "Service Account: ${SERVICE_ACCOUNT}"
echo "==========================================="
echo

# Step 1: Create bucket if it doesn't exist
echo "Step 1: Checking if bucket exists..."
if gcloud storage buckets describe "gs://${BUCKET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "✓ Bucket gs://${BUCKET_NAME} already exists"
else
    echo "Creating bucket gs://${BUCKET_NAME}..."
    gcloud storage buckets create "gs://${BUCKET_NAME}" \
        --project="${PROJECT_ID}" \
        --location="${LOCATION}" \
        --uniform-bucket-level-access
    echo "✓ Bucket created successfully"
fi
echo

# Step 2: Grant Storage Object Admin role to service account
echo "Step 2: Granting IAM permissions..."

# Check if the IAM binding already exists to keep this step idempotent
EXISTING_ROLE="$(gcloud storage buckets get-iam-policy "gs://${BUCKET_NAME}" \
    --project="${PROJECT_ID}" \
    --format="value(bindings.role)" \
    --filter="bindings.role=roles/storage.objectAdmin AND bindings.members=serviceAccount:${SERVICE_ACCOUNT}" 2>/dev/null || true)"

if [[ "${EXISTING_ROLE}" == "roles/storage.objectAdmin" ]]; then
    echo "✓ IAM binding roles/storage.objectAdmin for ${SERVICE_ACCOUNT} already exists"
else
    echo "Granting roles/storage.objectAdmin to ${SERVICE_ACCOUNT}..."
    gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/storage.objectAdmin" \
        --project="${PROJECT_ID}"
    echo "✓ IAM permissions granted successfully"
fi
echo

# Step 3: Verify setup
echo "Step 3: Verifying bucket configuration..."
gcloud storage buckets describe "gs://${BUCKET_NAME}" --project="${PROJECT_ID}"
echo
echo "IAM Policy:"
gcloud storage buckets get-iam-policy "gs://${BUCKET_NAME}" --project="${PROJECT_ID}"
echo

echo "==========================================="
echo "✓ GCS Bucket setup complete!"
echo "==========================================="
echo
echo "Bucket URL: https://storage.googleapis.com/${BUCKET_NAME}"
echo
echo "Next steps:"
echo "  1. Verify Django pods can access bucket"
echo "  2. Create Django superuser (will test avatar upload)"
echo "  3. Monitor bucket usage in GCP Console"
