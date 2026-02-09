#!/bin/bash
#
# Admin Workstation Setup Script (Ubuntu/Debian)
# Automates installation of tools needed for Manage2Soar production deployments
#
# Usage: ./infrastructure/scripts/setup-admin-ubuntu.sh
#
# This script:
# - Installs gcloud CLI
# - Installs kubectl
# - Installs Docker
# - Installs Ansible + required collections
# - Installs optional tools (k9s, helm, jq)
# - Sets up user permissions
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
echo -e "${GREEN}Manage2Soar Admin Setup (Ubuntu)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running on Ubuntu
if ! grep -q "Ubuntu" /etc/os-release; then
    echo -e "${RED}ERROR: This script is designed for Ubuntu.${NC}"
    echo "Your OS: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2)"
    exit 1
fi

echo -e "${YELLOW}This script will install:${NC}"
echo "  - Google Cloud CLI (gcloud)"
echo "  - kubectl"
echo "  - Docker Engine"
echo "  - Ansible + collections"
echo "  - k9s, helm, jq (optional tools)"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Setup cancelled."
    exit 0
fi

# Update system
echo -e "\n${GREEN}[1/6] Updating system packages...${NC}"
sudo apt-get update

# Install gcloud CLI
echo -e "\n${GREEN}[2/6] Installing Google Cloud CLI...${NC}"
if ! command -v gcloud &> /dev/null; then
    echo "Installing gcloud CLI..."
    sudo apt-get install -y apt-transport-https ca-certificates gnupg curl

    # Import Google Cloud public key
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

    # Add repository
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

    # Install
    sudo apt-get update && sudo apt-get install -y google-cloud-cli google-cloud-cli-gke-gcloud-auth-plugin

    echo -e "${GREEN}✓ gcloud CLI installed${NC}"
else
    echo -e "${YELLOW}✓ gcloud CLI already installed${NC}"
fi

# Install kubectl
echo -e "\n${GREEN}[3/6] Installing kubectl...${NC}"
if ! command -v kubectl &> /dev/null; then
    echo "Downloading kubectl..."
    KUBECTL_VERSION=$(curl -L -s https://dl.k8s.io/release/stable.txt)
    curl -LO "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl"
    chmod +x kubectl
    sudo mv kubectl /usr/local/bin/
    echo -e "${GREEN}✓ kubectl installed${NC}"
else
    echo -e "${YELLOW}✓ kubectl already installed${NC}"
fi

# Install Docker
echo -e "\n${GREEN}[4/6] Installing Docker Engine...${NC}"
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."

    # Remove old versions
    for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
        sudo apt-get remove -y $pkg 2>/dev/null || true
    done

    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    # Add repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker Engine
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Add user to docker group
    sudo usermod -aG docker $USER

    echo -e "${GREEN}✓ Docker installed${NC}"
    echo -e "${YELLOW}  IMPORTANT: Log out and log back in for docker group to take effect${NC}"
else
    echo -e "${YELLOW}✓ Docker already installed${NC}"
fi

# Install Ansible
echo -e "\n${GREEN}[5/6] Installing Ansible...${NC}"
if ! command -v ansible &> /dev/null; then
    echo "Installing Ansible..."
    sudo apt-get install -y ansible
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
    if sudo apt-get install -y jq 2>/dev/null; then
        echo -e "${GREEN}✓ jq installed${NC}"
    else
        echo -e "${RED}✗ jq installation failed${NC}"
        OPTIONAL_FAILED+=("jq")
    fi
else
    echo -e "${YELLOW}✓ jq already installed${NC}"
fi

# helm (with fallback to direct binary download)
if ! command -v helm &> /dev/null; then
    echo "Installing helm..."

    # Try apt installation first
    if curl -fsSL https://baltocdn.com/helm/signing.asc 2>/dev/null | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null 2>&1 && \
       echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list >/dev/null && \
       sudo apt-get update 2>/dev/null && \
       sudo apt-get install -y helm 2>/dev/null; then
        echo -e "${GREEN}✓ helm installed via apt${NC}"
    else
        # Fallback to direct binary download
        echo -e "${YELLOW}  apt method failed, trying direct download...${NC}"
        if curl -fsSL https://get.helm.sh/helm-v3.14.0-linux-amd64.tar.gz 2>/dev/null | tar -xz && \
           sudo mv linux-amd64/helm /usr/local/bin/ && \
           rm -rf linux-amd64; then
            echo -e "${GREEN}✓ helm installed via direct download${NC}"
        else
            echo -e "${RED}✗ helm installation failed (network issue)${NC}"
            OPTIONAL_FAILED+=("helm")
        fi
    fi
else
    echo -e "${YELLOW}✓ helm already installed${NC}"
fi

# k9s
if ! command -v k9s &> /dev/null; then
    echo "Installing k9s..."
    if curl -fsSL https://webinstall.dev/k9s 2>/dev/null | bash; then
        # Add to PATH
        if ! grep -q '$HOME/.local/bin' ~/.bashrc; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
        fi
        echo -e "${GREEN}✓ k9s installed${NC}"
    else
        echo -e "${RED}✗ k9s installation failed (network issue)${NC}"
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
        echo "  - $tool (you can install manually later)"
    done
    echo ""
fi

echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Log out and log back in (for docker group)"
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
echo "   cp inventory/gcp_app.yml.example inventory/gcp_app.yml"
echo "   cp group_vars/gcp_app/vars.yml.example group_vars/gcp_app/vars.yml"
echo "   cp group_vars/gcp_app/vault.yml.example group_vars/gcp_app/vault.yml"
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
