#!/bin/bash
set -e

# Quick Deploy Script for Manage2Soar
# This is a simplified deployment that:
# 1. Builds Docker image
# 2. Pushes to GCR
# 3. Updates Kubernetes deployments
#
# Use this when you just want to deploy code changes without Ansible

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="manage2soar"
IMAGE_NAME="manage2soar"
GCR_REGISTRY="gcr.io"
TENANTS=("ssc" "masa")

# Generate timestamp and git hash
TIMESTAMP=$(date +%Y%m%d-%H%M)
GIT_HASH=$(git rev-parse --short HEAD)
if [ -n "$(git status --porcelain)" ]; then
    GIT_HASH="${GIT_HASH}-dirty"
    echo -e "${YELLOW}WARNING: Working tree has uncommitted changes. Image tag will include '-dirty' suffix.${NC}"
fi
IMAGE_TAG="${TIMESTAMP}-${GIT_HASH}"
FULL_IMAGE="${GCR_REGISTRY}/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Manage2Soar Quick Deploy${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Image: ${FULL_IMAGE}"
echo "Tenants: ${TENANTS[@]}"
echo ""

# Check if we're in docker group
if ! docker ps &>/dev/null; then
    echo -e "${RED}ERROR: Cannot access Docker${NC}"
    echo "Run: newgrp docker"
    echo "Or log out and back in to activate docker group"
    exit 1
fi

# Check kubectl access
if ! kubectl get nodes &>/dev/null; then
    echo -e "${RED}ERROR: Cannot access Kubernetes cluster${NC}"
    echo "Run: gcloud container clusters get-credentials manage2soar-cluster --zone=us-east1-b --project=manage2soar"
    exit 1
fi

# Verify kubectl context (production safety check)
CURRENT_CONTEXT=$(kubectl config current-context)
echo -e "${YELLOW}Current kubectl context: ${CURRENT_CONTEXT}${NC}"
echo -e "${YELLOW}This will deploy to PRODUCTION${NC}"
echo ""

# Validate context or require explicit confirmation
if [[ ! "$CURRENT_CONTEXT" =~ manage2soar ]]; then
    echo -e "${RED}WARNING: Current context does not contain 'manage2soar'!${NC}"
    echo -e "${RED}You may be pointed at the wrong cluster.${NC}"
    echo ""
    read -p "Type the cluster name 'manage2soar' to continue: " -r
    if [[ "$REPLY" != "manage2soar" ]]; then
        echo "Deployment cancelled"
        exit 1
    fi
fi

# Check for migration changes
MIGRATION_CHANGES=$(git diff --name-only origin/main...HEAD | grep -c 'migrations/.*\.py$' || true)
if [ "$MIGRATION_CHANGES" -gt 0 ]; then
    echo -e "${RED}⚠ WARNING: ${MIGRATION_CHANGES} migration file(s) changed in this deployment!${NC}"
    echo -e "${YELLOW}Schema changes detected - migrations must be run after deployment.${NC}"
    echo ""
fi

# Confirm deployment
read -p "Deploy current code to production? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Step 1: Build Docker image
echo -e "\n${GREEN}[1/5] Building Docker image...${NC}"
docker build --platform linux/amd64 -t "${FULL_IMAGE}" .

# Step 2: Push to GCR
echo -e "\n${GREEN}[2/5] Pushing to Google Container Registry...${NC}"
docker push "${FULL_IMAGE}"

# Step 3: Update deployments
echo -e "\n${GREEN}[3/5] Updating Kubernetes deployments...${NC}"
for tenant in "${TENANTS[@]}"; do
    namespace="tenant-${tenant}"
    deployment="django-app-${tenant}"

    echo "  Updating ${deployment} in ${namespace}..."
    kubectl set image deployment/${deployment} \
        django="${FULL_IMAGE}" \
        -n "${namespace}"

    echo "  Waiting for rollout..."
    kubectl rollout status deployment/${deployment} -n "${namespace}" --timeout=5m
done

# Step 4: Verify
echo -e "\n${GREEN}[4/5] Verifying deployment...${NC}"
for tenant in "${TENANTS[@]}"; do
    namespace="tenant-${tenant}"
    echo "  ${namespace}:"
    kubectl get pods -n "${namespace}" -l app=django-app-${tenant}

    # Show non-Running pods if any exist
    NON_RUNNING=$(kubectl get pods -n "${namespace}" -l app=django-app-${tenant} --field-selector=status.phase!=Running --no-headers 2>/dev/null | wc -l)
    if [ "$NON_RUNNING" -gt 0 ]; then
        echo -e "  ${YELLOW}⚠ Warning: ${NON_RUNNING} pod(s) not in Running state${NC}"
    fi
done

# Step 5: Run migrations if needed
if [ "$MIGRATION_CHANGES" -gt 0 ]; then
    echo -e "\n${YELLOW}[5/5] Migration files changed - run migrations now?${NC}"
    read -p "Run 'python manage.py migrate' on all tenants? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for tenant in "${TENANTS[@]}"; do
            namespace="tenant-${tenant}"
            deployment="django-app-${tenant}"
            echo "  Running migrations for ${namespace}..."

            # Get first pod name
            POD=$(kubectl get pods -n "${namespace}" -l app=django-app-${tenant} -o jsonpath='{.items[0].metadata.name}')

            if [ -n "$POD" ]; then
                kubectl exec -n "${namespace}" "$POD" -c django -- python manage.py migrate --noinput
                echo -e "  ${GREEN}✓ Migrations complete for ${namespace}${NC}"
            else
                echo -e "  ${RED}✗ No pod found for ${namespace}${NC}"
            fi
        done
    else
        echo -e "${YELLOW}⚠ Skipped migrations - remember to run manually if needed!${NC}"
    fi
else
    echo -e "\n${GREEN}[5/5] No migration changes detected - skipping migration step${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Deployed: ${FULL_IMAGE}"
echo ""
echo "Verify at:"
echo "  - https://skylinesoaring.org (tenant-ssc)"
echo "  - https://masa.manage2soar.com (tenant-masa)"
echo ""
echo "Rollback if needed:"
for tenant in "${TENANTS[@]}"; do
    echo "  kubectl rollout undo deployment/django-app-${tenant} -n tenant-${tenant}"
done
