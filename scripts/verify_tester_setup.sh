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
echo "State Host to Test:     rocm-db (port 8443)"
echo "==========================================\n"

# =============================================================================
# CHECK 1: Docker Runtime Verification
# =============================================================================
echo -e "[Step 1/5] Verifying Container Runtime (Docker)..."

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
            # Note: Fails if networking or pull permissions are blocked
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
# CHECK 2: Network Registry Alias Resolution (rocm-builder)
# =============================================================================
echo -e "\n[Step 2/5] Verifying State-Client Packages (curl)..."

if command -v curl &> /dev/null; then
    log_pass "curl is installed (required to push artifacts/results to rocm-db via verify_state_setup.sh)."
else
    echo -e "\n${RED}curl is missing. It is REQUIRED for pushing test results to the state stack:${NC}" >&2
    if [ "$PKG_MANAGER" = "dnf" ]; then
        echo "   sudo dnf install curl" >&2
    elif [ "$PKG_MANAGER" = "apt" ]; then
        echo "   sudo apt-get update && sudo apt-get install curl" >&2
    else
        echo "   Install the 'curl' package for your distribution." >&2
    fi
    log_fail "curl not found — tester nodes cannot report jobs/artifacts without it."
fi

# =============================================================================
# CHECK 3: Network Registry Alias Resolution (rocm-builder)
# =============================================================================
echo -e "\n[Step 3/5] Verifying Controller Registry Alias..."

REGISTRY_ALIAS="rocm-builder"
EXPECTED_IP="192.168.1.25"
HOSTS_FILE="/etc/hosts"

# Robust check: look for the exact IP followed by the alias to avoid parsing errors on various Linux distros
if grep "^${EXPECTED_IP}.*${REGISTRY_ALIAS}$" "$HOSTS_FILE" &>/dev/null; then
    log_pass "Registry alias '${REGISTRY_ALIAS}' correctly resolves to ${EXPECTED_IP}"
else
    echo -e "${RED}Registry alias '${REGISTRY_ALIAS}' is missing or pointing to the wrong IP in ${HOSTS_FILE}.${NC}" >&2
    log_fail "Please run this on your test machine: sudo echo '$EXPECTED_IP $REGISTRY_ALIAS' | sudo tee -a /etc/hosts"
fi

# =============================================================================
# CHECK 3: Docker Insecure Registries Config (Required for Test Pulls!)
# =============================================================================
echo -e "\n[Step 4/5] Verifying Docker Security Configuration..."

DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
TARGET_REGISTRY="192.168.1.25:5000"
ALIAS_REGISTRY="rocm-builder:5000"

if [ ! -f "$DOCKER_DAEMON_JSON" ]; then
    # If the file doesn't exist, the daemon will default back to saving images on your main root partition!
    log_fail "Configuration file $DOCKER_DAEMON_JSON does not exist. Docker will likely use /var/lib/docker unless you create it." >&2
    echo -e "\n${RED}Immediate Fix Instructions:${NC}" >&2
    log_info "  Start from the repo's sample (TESTER sample: insecure-registries — not the builder one):" >&2
    log_info "    cp <rocm-distro-tester>/samples/daemon.json.tester /etc/docker/daemon.json" >&2
    log_info "    # ...adjust the IP/alias if your builder's is different, then:" >&2
    log_info "    sudo systemctl restart docker" >&2
    exit 1 # Stop here because without this, builds will fail due to storage exhaustion.
fi

# Check if insecure-registries is present
if grep -q "insecure-registries" "$DOCKER_DAEMON_JSON"; then
    # Verify it trusts either the IP or our alias so pulls succeed later!
    if grep -q "${TARGET_REGISTRY}" "$DOCKER_DAEMON_JSON" || grep -q "${ALIAS_REGISTRY}" "$DOCKER_DAEMON_JSON"; then
        log_pass "Docker daemon.json correctly includes registry in insecure-registries."
    else
        echo -e "${RED}WARNING: 'insecure-registries' is present, but your builder's registry is missing.${NC}" >&2
        echo -e "See samples/daemon.json.tester in the repo for the expected entries ('${TARGET_REGISTRY}' and/or '${ALIAS_REGISTRY}')." >&2
        echo -e "Update ${DOCKER_DAEMON_JSON} to include the IP '${TARGET_REGISTRY}' or alias '${ALIAS_REGISTRY}', then: sudo systemctl restart docker" >&2
        log_fail "insecure-registries does not list the builder registry." >&2
        exit 1
    fi
else
    echo -e "${RED}WARNING: docker.json exists but lacks 'insecure-registries'.${NC}" >&2
    echo -e "See samples/daemon.json.tester in the repo for the expected content, then: sudo systemctl restart docker" >&2
    log_fail "Add 'rocm-builder:5000' to your insecure-registries list." >&2
    exit 1
fi

# =============================================================================
# CHECK 4: AMD GPU & ROCm Driver Verification
# =============================================================================
echo -e "\n[Step 5/5] Verifying AMD GPU / ROCm Drivers..."

if command -v rocm_agent_enumerator &> /dev/null; then
    log_pass "rocm_agent_enumerator is available."
    
    # Use rocm_agent_enumerator to verify gpus
    echo "[INFO] Enumerating active AMD GPUs via ROCm tools:"
    AGENTS=$(rocm_agent_enumerator 2>/dev/null)
    
    if [ -n "${AGENTS}" ]; then
        log_pass "AMD GPUs successfully enumerated. Hardware is ready for ROCm workloads."
    else
        echo -e "${RED}rocm_agent_enumerator ran but found no GPU agents. Is the amdgpu driver loaded?${NC}" >&2
        log_fail "Check /dev/kfd permissions or ensure you have a compatible AMD GPU installed." >&2
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
        log_fail "AMD GPU hardware or base kernel driver (amdgpu) does not appear to be loaded. Please check lspci and dmesg for errors." >&2
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