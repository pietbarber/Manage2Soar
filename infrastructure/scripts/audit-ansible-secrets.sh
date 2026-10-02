#!/usr/bin/env bash
# =============================================================================
# audit-ansible-secrets.sh
# Keep the list of "secret files that must be present but never committed"
# correct, complete, and in-sync -- so it "always remembers, and never forgets."
#
# The single source of truth is:
#   infrastructure/ansible/required-secrets-manifest.txt   (TRACKED in git)
#
# Every entry in that manifest MUST be:
#   1. present on disk
#   2. gitignored   (git check-ignore passes)
#   3. NOT tracked  (git ls-files does not match it)
#
# Usage:
#   audit-ansible-secrets.sh audit    [default]  Verify the manifest is complete
#                                                and correct. Exits non-zero on
#                                                any violation.
#   audit-ansible-secrets.sh list              Print the manifest (comments stripped)
#   audit-ansible-secrets.sh sync              Overwrite ~/bin/ansible-secrets-files.txt
#                                                with the current manifest
#   audit-ansible-secrets.sh tarball [OUT]     Build a backup tarball of every file
#                                                in the manifest. OUT defaults to
#                                                ./ansible-secrets-YYYYmmdd-HHMMSS.tar.gz
#
# Exit codes:
#   0  all good
#   1  one or more violations (see output)
#   2  usage / environment error
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve project root + manifest path
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# script lives in infrastructure/scripts/ ; project root is two levels up
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MANIFEST="${PROJECT_ROOT}/infrastructure/ansible/required-secrets-manifest.txt"

if [[ ! -f "${MANIFEST}" ]]; then
    echo "ERROR: manifest not found: ${MANIFEST}" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Print active (non-comment, non-blank) entries, one per line.
active_entries() {
    sed -E 's/^[[:space:]]*//; s/[[:space:]]*$//' "${MANIFEST}" \
        | awk 'NF && $0 !~ /^#/ {print}'
}

# Return 0 (success) if the given repo-relative path is ignored by git.
is_ignored() {
    ( cd "${PROJECT_ROOT}" && git check-ignore -q -- "$1" )
}

# Return 0 (success) if the given repo-relative path is tracked by git.
is_tracked() {
    ( cd "${PROJECT_ROOT}" && git ls-files --error-unmatch -- "$1" >/dev/null 2>&1 )
}

# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------
audit() {
    local failures=0
    local entry

    echo "Audit: required-secrets-manifest.txt"
    echo "Root : ${PROJECT_ROOT}"
    echo

    # Pass 1: every manifest entry must exist, be ignored, and be untracked.
    while IFS= read -r entry; do
        [[ -z "${entry}" ]] && continue

        if [[ ! -e "${PROJECT_ROOT}/${entry}" ]]; then
            printf '  [FAIL] MISSING on disk   : %s\n' "${entry}"
            failures=$((failures + 1))
        fi

        if ! is_ignored "${entry}"; then
            printf '  [FAIL] NOT gitignored    : %s\n' "${entry}"
            failures=$((failures + 1))
        fi

        if is_tracked "${entry}"; then
            printf '  [FAIL] TRACKED by git    : %s   <-- MUST NOT be committed\n' "${entry}"
            failures=$((failures + 1))
        fi
    done < <(active_entries)

    # Pass 2: detect gitignored files that live under infrastructure/ansible
    # or at the repo root (the places secrets live) but are NOT in the
    # manifest. These are "maybe you forgot to add it" warnings -- they are
    # NOT hard failures because some are legitimately optional (e.g. an
    # extra service-account key). They are printed so a human can decide.
    local known tmp_forg
    known="$(active_entries)"
    tmp_forg="$(mktemp)"

    ( cd "${PROJECT_ROOT}" && \
      git ls-files --others --ignored --exclude-standard \
        | grep -E '^(infrastructure/ansible/|\.env$|.*\.private$|.*dkim-keys/.*\.txt$|.*key.*\.json$|.*account.*\.json$|.*service-account.*|.*\.pem$|.*credentials/)' \
        | grep -vE '\.example$|\.retry$|node_modules|staticfiles|static/|__pycache__|\.pyc|media/|\.github/conversations/|/files/README|manifest|site-packages|dist-packages|\.venv|/venv-|/env/|\.tox/' \
        || true ) > "${tmp_forg}" 2>/dev/null

    if [[ -s "${tmp_forg}" ]]; then
        echo
        echo "  [WARN] Gitignored secret-looking files NOT in the manifest:"
        while IFS= read -r f; do
            [[ -z "${f}" ]] && continue
            if ! printf '%s\n' "${known}" | grep -qxF -- "${f}"; then
                printf '           + %s\n' "${f}"
            fi
        done < "${tmp_forg}"
        echo "       (add them to the manifest if they are required, or leave them out if optional)"
    fi
    rm -f "${tmp_forg}"

    echo
    if (( failures == 0 )); then
        echo "PASS: all manifest entries exist, are gitignored, and are untracked."
        return 0
    else
        echo "FAIL: ${failures} violation(s). Fix before committing."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
list() {
    active_entries
}

# ---------------------------------------------------------------------------
# sync  -> overwrite ~/bin/ansible-secrets-files.txt
# ---------------------------------------------------------------------------
sync_bin_list() {
    local dest="${HOME}/bin/ansible-secrets-files.txt"
    local tmp
    tmp="$(mktemp)"

    {
        echo "# Ansible Secrets Tarball - File List"
        echo "# GENERATED by infrastructure/scripts/audit-ansible-secrets.sh sync"
        echo "# Source of truth: infrastructure/ansible/required-secrets-manifest.txt"
        echo "# One file path per line, relative to project root"
        active_entries
    } > "${tmp}"

    mkdir -p "$(dirname "${dest}")"
    if [[ -f "${dest}" && ! -w "${dest}" ]]; then
        echo "ERROR: cannot write ${dest} (not writable)" >&2
        exit 2
    fi
    cp "${tmp}" "${dest}"
    rm -f "${tmp}"
    echo "Updated: ${dest}"
    echo "Entries: $(active_entries | wc -l | tr -d ' ')"
}

# ---------------------------------------------------------------------------
# tarball  -> build a backup archive of every manifest entry
# ---------------------------------------------------------------------------
build_tarball() {
    local out="${1:-}"
    if [[ -z "${out}" ]]; then
        local ts
        ts="$(date +%Y%m%d-%H%M%S)"
        out="${PROJECT_ROOT}/ansible-secrets-${ts}.tar.gz"
    fi
    # Resolve to absolute if relative
    case "${out}" in
        /*) : ;;
        *)  out="${PWD}/${out}" ;;
    esac

    local files=()
    local entry
    while IFS= read -r entry; do
        [[ -z "${entry}" ]] && continue
        if [[ ! -e "${PROJECT_ROOT}/${entry}" ]]; then
            echo "ERROR: manifest entry missing on disk: ${entry}" >&2
            exit 2
        fi
        files+=("${entry}")
    done < <(active_entries)

    echo "Creating backup tarball with ${#files[@]} file(s)..."
    ( cd "${PROJECT_ROOT}" && tar -czf "${out}" "${files[@]}" )

    echo
    echo "Created: ${out}"
    echo "Files  : ${#files[@]}"
    echo "SHA-256:"
    ( cd "${PROJECT_ROOT}" && sha256sum "${out}" )
    echo
    echo "NEXT: store this tarball securely (encrypted at rest, off-box). "
    echo "      ALSO back up the Vault password (ANSIBLE_VAULT_PASSWORD) "
    echo "      separately -- it is not in the tarball."
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
cmd="${1:-audit}"
case "${cmd}" in
    audit)   audit ;;
    list)    list ;;
    sync)    sync_bin_list ;;
    tarball) shift; build_tarball "${1:-}" ;;
    -h|--help|help)
        sed -n '2,40p' "${BASH_SOURCE[0]}"
        ;;
    *)
        echo "Unknown command: ${cmd}" >&2
        echo "Try: audit | list | sync | tarball" >&2
        exit 2
        ;;
esac
