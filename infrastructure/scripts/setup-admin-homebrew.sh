#!/bin/bash
#
# Admin Workstation Setup Script (macOS with Homebrew)
# Automates installation of tools needed for Manage2Soar production deployments
#
# Usage: ./infrastructure/scripts/setup-admin-homebrew.sh
#
# This script:
# - Installs gcloud CLI
# - Installs kubectl
# - Installs Docker Desktop for Mac (or prompts for manual installation)
# - Installs Ansible + required collections
# - Installs optional tools (k9s, helm, jq)
#
# Run this script, then manually configure:
# - gcloud init (authenticate with GCP)
# - kubectl access (get-credentials for your cluster)
# - Ansible vault password (~/.ansible_vault_pass)
# - Infrastructure config files (inventory, group_vars)

set -e  # Exit on error

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Manage2Soar Admin Setup (macOS)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}ERROR: This script is designed for macOS.${NC}"
    echo "Your OS: $OSTYPE"
    echo "For Ubuntu/Debian systems, use infrastructure/scripts/setup-admin-ubuntu.sh instead."
    exit 1
fi

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo -e "${RED}ERROR: Homebrew is not installed.${NC}"
    echo ""
    echo "Install Homebrew first:"
    echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
    exit 1
fi

echo -e "${YELLOW}This script will install:${NC}"
echo "  - Google Cloud CLI (gcloud)"
echo "  - kubectl"
echo "  - Docker Desktop for Mac (manual step)"
echo "  - Ansible + collections"
echo "  - k9s, helm, jq (optional tools)"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Setup cancelled."
    exit 0
fi

# Update Homebrew
echo -e "\n${GREEN}[1/6] Updating Homebrew...${NC}"
brew update

# Install gcloud CLI
echo -e "\n${GREEN}[2/6] Installing Google Cloud CLI...${NC}"
if ! command -v gcloud &> /dev/null; then
    echo "Installing gcloud CLI..."
    brew install google-cloud-sdk

    # Install GKE auth plugin
    brew install google-cloud-sdk-gke-gcloud-auth-plugin

    echo -e "${GREEN}✓ gcloud CLI installed${NC}"
else
    echo -e "${YELLOW}✓ gcloud CLI already installed${NC}"
    # Try to update components
    gcloud components update --quiet 2>/dev/null || true
fi

# Install kubectl
echo -e "\n${GREEN}[3/6] Installing kubectl...${NC}"
if ! command -v kubectl &> /dev/null; then
    echo "Installing kubectl..."
    brew install kubectl
    echo -e "${GREEN}✓ kubectl installed${NC}"
else
    echo -e "${YELLOW}✓ kubectl already installed${NC}"
fi

# Check for Docker
echo -e "\n${GREEN}[4/6] Checking Docker installation...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker is not installed.${NC}"
    echo ""
    echo "Docker Desktop for Mac must be installed manually:"
    echo "  1. Visit: https://www.docker.com/products/docker-desktop"
    echo "  2. Download and install Docker Desktop for Mac"
    echo "  3. Start Docker Desktop from Applications"
    echo ""
    echo "Alternatively, install via Homebrew:"
    echo "  brew install --cask docker"
    echo ""
    read -p "Press Enter to continue without Docker (you can install it later)..."
    echo -e "${YELLOW}⚠ Docker not installed - you'll need to install it manually${NC}"
else
    echo -e "${GREEN}✓ Docker already installed${NC}"

    # Check if Docker is running
    if docker info &> /dev/null; then
        echo -e "${GREEN}✓ Docker is running${NC}"
    else
        echo -e "${YELLOW}⚠ Docker is installed but not running. Start Docker Desktop.${NC}"
    fi
fi

# Install Ansible
echo -e "\n${GREEN}[5/6] Installing Ansible...${NC}"
if ! command -v ansible &> /dev/null; then
    echo "Installing Ansible..."
    brew install ansible
    echo -e "${GREEN}✓ Ansible installed${NC}"
else
    echo -e "${YELLOW}✓ Ansible already installed${NC}"
fi

# Install Ansible collections
echo "Installing Ansible collections..."
ansible-galaxy collection install kubernetes.core --force
ansible-galaxy collection install google.cloud --force
ansible-galaxy collection install community.postgresql --force
echo -e "${GREEN}✓ Ansible collections installed${NC}"

# Install optional tools (failures are non-blocking)
echo -e "\n${GREEN}[6/6] Installing optional tools...${NC}"
OPTIONAL_FAILED=()

# jq
if ! command -v jq &> /dev/null; then
    if brew install jq 2>/dev/null; then
        echo -e "${GREEN}✓ jq installed${NC}"
    else
        echo -e "${RED}✗ jq installation failed${NC}"
        OPTIONAL_FAILED+=("jq")
    fi
else
    echo -e "${YELLOW}✓ jq already installed${NC}"
fi

# helm
if ! command -v helm &> /dev/null; then
    echo "Installing helm..."
    if brew install helm 2>/dev/null; then
        echo -e "${GREEN}✓ helm installed${NC}"
    else
        echo -e "${RED}✗ helm installation failed${NC}"
        OPTIONAL_FAILED+=("helm")
    fi
else
    echo -e "${YELLOW}✓ helm already installed${NC}"
fi

# k9s
if ! command -v k9s &> /dev/null; then
    echo "Installing k9s..."
    if brew install k9s 2>/dev/null; then
        echo -e "${GREEN}✓ k9s installed${NC}"
    else
        echo -e "${RED}✗ k9s installation failed${NC}"
        OPTIONAL_FAILED+=("k9s")
    fi
else
    echo -e "${YELLOW}✓ k9s already installed${NC}"
fi

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Show optional tool failures if any
if [ ${#OPTIONAL_FAILED[@]} -gt 0 ]; then
    echo -e "${YELLOW}Note: Some optional tools failed to install:${NC}"
    for tool in "${OPTIONAL_FAILED[@]}"; do
        echo "  - $tool (you can install manually later with: brew install $tool)"
    done
    echo ""
fi

echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. If you installed Docker Desktop via Homebrew:"
echo "   - Open Docker Desktop from Applications"
echo "   - Wait for it to start (whale icon in menu bar)"
echo ""
echo "2. Authenticate with GCP:"
echo "   gcloud init"
echo "   gcloud auth application-default login"
echo "   gcloud auth configure-docker"
echo ""
echo "3. Get kubectl access to your cluster:"
echo "   gcloud container clusters get-credentials CLUSTER_NAME --region=REGION --project=PROJECT_ID"
echo ""
echo "4. Set up Ansible vault password:"
echo "   echo 'your-vault-password' > ~/.ansible_vault_pass"
echo "   chmod 600 ~/.ansible_vault_pass"
echo ""
echo "5. Configure infrastructure files:"
echo "   cd infrastructure/ansible"
echo "   mkdir -p group_vars/gcp_app"
echo "   cp inventory/gcp_app.yml.example inventory/gcp_app.yml"
echo "   cp group_vars/gcp_app.vars.yml.example group_vars/gcp_app/vars.yml"
echo "   cp group_vars/gcp_app.vault.yml.example group_vars/gcp_app/vault.yml"
echo "   vim inventory/gcp_app.yml"
echo "   vim group_vars/gcp_app/vars.yml"
echo "   vim group_vars/gcp_app/vault.yml"
echo "   ansible-vault encrypt group_vars/gcp_app/vault.yml --vault-password-file ~/.ansible_vault_pass"
echo ""
echo "6. Verify setup:"
echo "   gcloud projects list"
echo "   kubectl get nodes"
echo "   docker run hello-world"
echo "   ansible --version"
echo ""
echo "7. See full documentation:"
echo "   docs/admin-workstation-setup.md"
echo ""
echo -e "${GREEN}Happy deploying! 🚀${NC}"
