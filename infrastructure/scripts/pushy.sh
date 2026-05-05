#!/usr/bin/env bash
#
# Deploy to GKE with migrations.
#
# Usage:
#   pushy.sh              -> deploy tenant-demo only (safe default)
#   pushy.sh demo         -> deploy tenant-demo only
#   pushy.sh ssc          -> deploy tenant-ssc only
#   pushy.sh masa         -> deploy tenant-masa only
#   pushy.sh --all        -> deploy all tenants

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ANSIBLE_DIR="$(cd -- "${SCRIPT_DIR}/../ansible" >/dev/null 2>&1 && pwd)"

TENANT="${1:-demo}"

if [[ "$TENANT" == "--all" ]]; then
  echo "==> Deploying to ALL tenants"
  TENANT_FLAG=""
else
  echo "==> Deploying to tenant: ${TENANT}"
  TENANT_FLAG="-e gke_deploy_tenant=${TENANT}"
fi

cd "$ANSIBLE_DIR"
ansible-playbook -i inventory/gcp_app.yml \
  --vault-password-file ~/.ansible_vault_pass \
  -e gke_run_migrations=true \
  -e gke_run_backfill_document_sizes=true \
  ${TENANT_FLAG} \
  playbooks/gcp-app-deploy.yml
