#!/bin/bash
# =============================================================================
# verify_tester_setup.sh - ROCm Test Node Readiness Checker
# =============================================================================
# Purpose: Validates that a target test machine has Docker, Network Alias, 
# Registry Trust Configuration, and AMD GPU (ROCm) prerequisites met for 
# automated distro testing.
# Designed to be copied via scp/ssh to remote tester nodes before execution.
#
# Usage:
#   scp verify_tester_setup.sh <tester>:/tmp && ssh <tester> /tmp/verify_tester_setup.sh
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS_COUNT++)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL_COUNT++)); exit 1; }
log_info() { echo -e "[INFO] $1"; }

# Detect OS & Package Manager for accurate installation recommendations
OS_NAME="Unknown Linux"
PKG_MANAGER="unknown"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME="$NAME"
fi

if command -v dnf &>/dev/null; then PKG_MANAGER="dnf"; 
elif command -v apt-get &>/dev/null; then PKG_MANAGER="apt";
fi

echo -e "\n=========================================="
echo "--- ROCm Tester Node Verification ---"
echo "Target OS: ${OS_NAME}"
echo "Package Manager: ${PKG_MANAGER}"
echo "Registry Alias to Test: rocm-builder (port 5000)"
echo "==========================================\n"

# =============================================================================
# CHECK 1: Docker Runtime Verification
# =============================================================================
echo -e "[Step 1/4] Verifying Container Runtime (Docker)..."

if command -v docker &> /dev/null; then
    log_pass "Docker CLI is installed."
    
    # Check if we have permission to interact with the daemon
    DOCK_PERM_OK=false
    if [ "$(docker info &>/dev/null; echo $?)" = "0" ]; then
        DOCK_PERM_OK=true
    fi

    if "$DOCK_PERM_OK"; then
        log_pass "Docker daemon is responding."
        
        log_info "Verifying Docker runtime health..."
        if docker run --rm hello-world &>/dev/null; then
            log_pass "Hello World container executed successfully. Runtime is healthy."
        else
            log_fail "Docker daemon is up, but 'docker run' failed (check network or permissions)."
        fi
    else
        # Permission Denied scenario: Likely missing usermod/group add
        echo -e "\n${RED}Permission denied. Docker is installed, but your user lacks access.${NC}" >&2
        echo "To fix this, run the following command and re-run this script:" >&2
        echo "   sudo usermod -aG docker \$USER" >&2
        exit 1
    fi
else
    # Recommend how to install Docker otherwise based on distro (with UserMod fix)
    echo -e "\n${RED}Docker CLI is missing. Installation recommendations:${NC}" >&2
    
    if [ "$PKG_MANAGER" = "dnf" ]; then
        cat << 'INSTALL_DOCKER'

## 1. Install Docker Engine:
sudo dnf install docker-ce docker-ce-cli containerd.io

## 2. Start and enable service:
sudo systemctl start docker && sudo systemctl enable docker

## 3. CRITICAL: Add your current user to the docker group (required for non-root access):
sudo usermod -aG docker $USER

(You may need to log out/in or run 'newgrp docker' for changes to take effect)
INSTALL_DOCKER
    elif [ "$PKG_MANAGER" = "apt" ]; then
        cat << 'INSTALL_DOCKER'

## 1. Add Docker's official GPG key & repository:
sudo apt-get update
sudo apt-get install ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=\$(dpkg --print_architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

## 2. Install Docker Engine:
sudo apt-get update && sudo apt-get install docker-ce docker-ce-cli containerd.io

## 3. Start and enable the service:
sudo systemctl start docker && sudo systemctl enable docker

## 4. CRITICAL: Add your current user to the docker group (required for non-root access):
sudo usermod -aG docker $USER

(You may need to log out/in or run 'newgrp docker' for changes to take effect)
INSTALL_DOCKER
    else
        cat << 'INSTALL_DOCKER'
## Please visit https://docs.docker.com/engine/install/ for your specific Linux distribution.

**IMPORTANT:** After installation, ensure you add your user to the docker group:
$ sudo usermod -aG docker $USER
INSTALL_DOCKER
    fi
fi

# =============================================================================
# CHECK 2: Network Registry Alias Resolution (rocm-builder) - FIXED
# =============================================================================
echo -e "\n[Step 2/4] Verifying Controller Registry Alias..."

REGISTRY_ALIAS="rocm-builder"
EXPECTED_IP="192.168.1.25"
HOSTS_FILE="/etc/hosts"

if grep "^${EXPECTED_IP}.*${REGISTRY_ALIAS}$" "$HOSTS_FILE" &>/dev/null; then
    CURRENT_IP="$(grep "${REGISTRY_ALIAS}" "$HOSTS_FILE" | awk '{print $1}')"
    if [ "$CURRENT_IP" = "$EXPECTED_IP" ]; then
        log_pass "Registry alias '${REGISTRY_ALIAS}' resolves correctly to ${EXPECTED_IP}"
    else
        echo -e "${RED}Alias '${REGISTRY_ALIAS}' exists but points to '${CURRENT_IP}'. Expected '${EXPECTED_IP}'.${NC}" >&2
        log_fail "Network configuration is incorrect. Update /etc/hosts to resolve 'rocm-builder' to $EXPECTED_IP."
    fi
else
    echo -e "${RED}Registry alias '${REGISTRY_ALIAS}' not found in ${HOSTS_FILE}.${NC}" >&2
    log_fail "Please add the following line to /etc/hosts on this machine: $EXPECTED_IP rocm-builder"
fi

# =============================================================================
# CHECK 3: Docker Insecure Regisries Config (Required for Test Pulls!)
# =============================================================================
echo -e "\n[Step 3/4] Verifying Docker Security Configuration..."

DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
TARGET_REGISTRY="192.168.1.25:5000"
ALIAS_REGISTRY="rocm-builder:5000"

if [ -f "$DOCKER_DAEMON_JSON" ]; then
    if grep -q "insecure-registries" "$DOCKER_DAEMON_JSON"; then
        # Verify it trusts either the IP or our alias so pulls succeed later!
        if grep -q "${TARGET_REGISTRY}" "$DOCKER_DAEMON_JSON" || grep -q "${ALIAS_REGISTRY}" "$DOCKER_DAEMON_JSON"; then
            log_pass "Docker daemon.json correctly includes registry in insecure-registries."
        else
            echo -e "${RED}WARNING: 'insecure-registries' is present, but your builder's registry is missing.${NC}" >&2
            log_fail "Update ${DOCKER_DAEMON_JSON} to include the IP '${TARGET_REGISTRY}' or alias '${ALIAS_REGISTRY}'."
        fi
    else
        echo -e "${RED}WARNING: docker.json exists but lacks 'insecure-registries'.${NC}" >&2
        log_fail "Add '192.168.1.25:5000' to your insecure_registries list."
    fi
else
    echo -e "${RED}CRITICAL: ${DOCKER_DAEMON_JSON} does not exist.${NC}" >&2
    log_fail "Create this file and add '192.168.1.25:5000' to your daemon configuration!"
fi

# =============================================================================
# CHECK 4: AMD GPU & ROCm Driver Verification (Updated for local paths)
# =============================================================================
echo -e "\n[Step 4/4] Verifying AMD GPU / ROCm Drivers..."

if command -v rocm_agent_enumerator &> /dev/null; then
    log_pass "rocm_agent_enumerator is available."
    
    # Use rocm_agent_enumerator to verify gpus
    echo "[INFO] Enumerating active AMD GPUs via ROCm tools:"
    AGENTS=$(rocm_agent_enumerator 2>/dev/null)
    
    if [ -n "${AGENTS}" ]; then
        log_pass "AMD GPUs successfully enumerated. Hardware is ready for ROCm workloads."
    else
        log_fail "rocm_agent_enumerator ran but found no GPU agents. Is the amdgpu_driver loaded?"
    fi
else
    # Recommend how to install rocminfo with rpm / standard packages
    echo -e "\n${RED}ROCm CLI tools (rocminfo / rocm_agent_enumerator) are missing.${NC}" >&2
    echo "--- Recommended Installation ---"
    
    if [ "$PKG_MANAGER" = "dnf" ]; then
        cat << 'INSTALL_ROCM'

## Installing ROCm Tools (Fedora/RHEL):
# Install rocminfo and related ROCm CLI utilities via RPM:
sudo dnf install -y rocminfo amdgpu-libs rocm-smi-lib
# Alternatively, use the official AMD setup script for full toolchains:
# curl -sL https://amdgpu-install.amd.com/unstable/setup.sh | sudo bash

INSTALL_ROCM
    elif [ "$PKG_MANAGER" = "apt" ]; then
        cat << 'INSTALL_ROCM'

## Installing ROCm Tools (Ubuntu/Debian):
# Install rocminfo via standard repositories:
sudo apt-get update && sudo apt-get install -y rocminfo libdrm-amdgpu1 rocm-smi-lib
# For the complete ROCm toolkit and GPU passthrough support, use AMD's official setup:
# curl -sL https://amdgpu-install.amd.com/unstable/setup.sh | sudo bash

INSTALL_ROCM
    else
        echo "Download the ROCm installation script for your distro from AMD's developer portal."
    fi

    # Fallback check to ensure it's not just a missing package but a driver issue
    if [ -e /dev/kfd ]; then
        log_pass "Base GPU driver is active (/dev/kfd exists), userland CLI tools just need installation."
    else
        log_fail "AMD GPU hardware or base kernel driver (amdgpu) does not appear to be loaded. Please check lspci and dmesg for errors."
    fi
fi

# =============================================================================
# FINAL SUMMARY
# =============================================================================
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "\n${GREEN}==========================================${NC}"
    echo -e "${GREEN}--- SYSTEM READY: All checks PASSED ---${NC}"
    echo -e "${GREEN}==========================================${NC}"
else
    echo -e "\n${RED}==========================================${NC}"
    echo -e "${RED}--- VERIFICATION FAILED: Address issues above ---${NC}"
    echo -e "${RED}==========================================${NC}"
fi

exit "$FAIL_COUNT"