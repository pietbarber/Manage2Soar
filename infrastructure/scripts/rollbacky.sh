#!/usr/bin/env bash
#
# Roll back GKE tenant deployments to a previous image using the Ansible deploy playbook.
#
# Modes:
#   1) Explicit tag (single tenant or all tenants)
#      rollbacky.sh svs --tag 20260504-1015-abcd123
#      rollbacky.sh --all --tag 20260504-1015-abcd123
#
#   2) Auto-detect previous tag from rollout history (single tenant only)
#      rollbacky.sh svs --previous
#
# Notes:
# - Uses IaC deploy path (ansible playbook), not ad-hoc kubectl patching.
# - Disables build/push and skips migrations/backfill during rollback.
# - --previous parses the previous deployment revision image tag from Kubernetes.

set -euo pipefail

ANSIBLE_DIR="/home/pb/Projects/skylinesoaring/infrastructure/ansible"
PLAYBOOK="playbooks/gcp-app-deploy.yml"
INVENTORY="inventory/gcp_app.yml"
VAULT_PASS_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-$HOME/.ansible_vault_pass}"

usage() {
  cat <<'EOF'
Usage:
  rollbacky.sh <tenant> --tag <image-tag> [--dry-run] [--yes]
  rollbacky.sh --all --tag <image-tag> [--dry-run] [--yes]
  rollbacky.sh <tenant> --previous [--dry-run] [--yes]

Examples:
  rollbacky.sh svs --tag 20260504-1015-abcd123
  rollbacky.sh --all --tag 20260504-1015-abcd123 --yes
  rollbacky.sh masa --previous

Options:
  --tag <image-tag>   Roll back to this exact image tag.
  --previous          Detect previous revision image tag for one tenant.
  --all               Target all tenants (requires --tag).
  --dry-run           Print resolved command and exit.
  --yes               Skip confirmation prompt.
  -h, --help          Show this help.
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command not found: $1" >&2
    exit 1
  }
}

resolve_previous_tag() {
  local tenant="$1"
  local namespace="tenant-${tenant}"
  local deployment="django-app-${tenant}"

  require_cmd kubectl

  local history
  if ! history="$(kubectl rollout history "deployment/${deployment}" -n "${namespace}" 2>/dev/null)"; then
    echo "Error: unable to read rollout history for ${deployment} in ${namespace}" >&2
    exit 1
  fi

  local revisions
  revisions="$(printf '%s\n' "$history" | awk '/^[[:space:]]*[0-9]+[[:space:]]/{print $1}')"
  local rev_count
  rev_count="$(printf '%s\n' "$revisions" | sed '/^$/d' | wc -l | tr -d ' ')"

  if [[ "$rev_count" -lt 2 ]]; then
    echo "Error: no previous revision found for tenant '${tenant}'" >&2
    exit 1
  fi

  local previous_revision
  previous_revision="$(printf '%s\n' "$revisions" | tail -2 | head -1 | tr -d '[:space:]')"

  local revision_details
  revision_details="$(kubectl rollout history "deployment/${deployment}" -n "${namespace}" --revision="${previous_revision}")"

  local image_ref
  image_ref="$(printf '%s\n' "$revision_details" | awk '/Image:[[:space:]]/{print $2; exit}')"

  if [[ -z "$image_ref" ]]; then
    echo "Error: could not parse image from revision ${previous_revision} for tenant '${tenant}'" >&2
    exit 1
  fi

  # Expect image like gcr.io/project/manage2soar:<tag>
  # If digest form appears (..@sha256:...), instruct caller to use explicit --tag.
  if [[ "$image_ref" == *@* ]]; then
    echo "Error: previous revision image uses digest (${image_ref}); use --tag explicitly" >&2
    exit 1
  fi

  if [[ "$image_ref" != *:* ]]; then
    echo "Error: previous revision image has no tag (${image_ref}); use --tag explicitly" >&2
    exit 1
  fi

  printf '%s\n' "${image_ref##*:}"
}

TARGET=""
IMAGE_TAG=""
USE_PREVIOUS=false
DRY_RUN=false
ASSUME_YES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      TARGET="--all"
      shift
      ;;
    --tag)
      [[ $# -ge 2 ]] || { echo "Error: --tag requires a value" >&2; usage; exit 1; }
      IMAGE_TAG="$2"
      shift 2
      ;;
    --previous)
      USE_PREVIOUS=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --yes)
      ASSUME_YES=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$TARGET" ]]; then
        TARGET="$1"
        shift
      else
        echo "Error: unexpected argument: $1" >&2
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "Error: missing target tenant or --all" >&2
  usage
  exit 1
fi

if [[ "$TARGET" == "--all" && "$USE_PREVIOUS" == true ]]; then
  echo "Error: --previous is only supported for a single tenant" >&2
  echo "Tip: resolve one tenant first, then run --all --tag <resolved-tag>." >&2
  exit 1
fi

if [[ "$USE_PREVIOUS" == true && -n "$IMAGE_TAG" ]]; then
  echo "Error: choose either --tag or --previous, not both" >&2
  exit 1
fi

if [[ "$USE_PREVIOUS" == false && -z "$IMAGE_TAG" ]]; then
  echo "Error: provide --tag <image-tag> or --previous" >&2
  exit 1
fi

if [[ "$USE_PREVIOUS" == true ]]; then
  IMAGE_TAG="$(resolve_previous_tag "$TARGET")"
fi

if [[ ! -f "$VAULT_PASS_FILE" ]]; then
  echo "Error: vault password file not found at ${VAULT_PASS_FILE}" >&2
  exit 1
fi

if [[ "$TARGET" == "--all" ]]; then
  TARGET_DESC="ALL tenants"
  TENANT_FLAG=""
else
  TARGET_DESC="tenant ${TARGET}"
  TENANT_FLAG="-e gke_deploy_tenant=${TARGET}"
fi

echo "==> Rollback target: ${TARGET_DESC}"
echo "==> Image tag: ${IMAGE_TAG}"
echo "==> Mode: IaC replay via ${PLAYBOOK}"

if [[ "$ASSUME_YES" == false ]]; then
  read -r -p "Proceed with rollback? [y/N] " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi
fi

CMD=(
  ansible-playbook
  -i "$INVENTORY"
  --vault-password-file "$VAULT_PASS_FILE"
  -e "gke_build_image=false"
  -e "gke_push_image=false"
  -e "gke_run_migrations=false"
  -e "gke_run_backfill_document_sizes=false"
  -e "gke_image_tag=${IMAGE_TAG}"
)

if [[ -n "$TENANT_FLAG" ]]; then
  CMD+=( $TENANT_FLAG )
fi

CMD+=( "$PLAYBOOK" )

if [[ "$DRY_RUN" == true ]]; then
  echo "==> Dry run (command):"
  printf 'cd %q && ' "$ANSIBLE_DIR"
  printf '%q ' "${CMD[@]}"
  printf '\n'
  exit 0
fi

(
  cd "$ANSIBLE_DIR"
  "${CMD[@]}"
)

echo "==> Rollback completed for ${TARGET_DESC} to image tag ${IMAGE_TAG}"
