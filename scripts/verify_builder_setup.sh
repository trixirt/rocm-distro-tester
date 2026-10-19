#!/bin/bash
# =============================================================================
# verify_builder_setup.sh - ROCm CI Builder Node Checker
# =============================================================================
# Purpose: Validates that a target machine is ready to act as the 
# centralized Image Registry and Build Controller (EXPECTED_IP).
# Designed to be copied via scp/ssh to build nodes before execution.
#
# Usage:
#   scp verify_builder_setup.sh <builder_host>:/tmp && ssh <builder_host> /tmp/verify_builder_setup.sh
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

# --- Reuse: Logging helpers from verify_tester_setup.sh ---
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS_COUNT++)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL_COUNT++)); exit 1; }
log_info() { echo -e "[INFO] $1"; }

# --- Reuse: OS/PKG detection logic from verify_tester_setup.sh ---
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
echo "--- ROCm CI Builder Node Verification ---"
echo "Target OS: ${OS_NAME}"
echo "Package Manager: ${PKG_MANAGER}"
echo "Expected Registry IP: 192.168.1.25"
echo "Storage Standard: XFS | Root Has rwx (7)"
echo "==========================================\n"

# =============================================================================
# CHECK 1: Docker Runtime and Config File Verification (Step 1b Included!)
# =============================================================================
echo -e "[Step 1/4] Verifying Container Runtime and Configuration..."

if command -v docker &> /dev/null; then
    log_pass "Docker CLI is installed."
    
    # Reusable permission check
    DOCK_PERM_OK=false
    if [ "$(docker info &>/dev/null; echo $?)" = "0" ]; then
        DOCK_PERM_OK=true
    fi

    if "$DOCK_PERM_OK"; then
        log_pass "Docker daemon is responding."
        
        log_info "Verifying Docker runtime health..."
        if docker run --rm hello-world &>/dev/null; then
            log_pass "Hello World container executed successfully. Build environment is healthy."
        else
            log_fail "Docker daemon is up, but 'docker run' failed on this node (check local network/daemon)."
        fi
    else
        echo -e "\n${RED}Permission denied. Docker is installed, but your user lacks access.${NC}" >&2
        echo "To fix this, run the following command and re-run this script:" >&2
        echo "   sudo usermod -aG docker \$USER" >&2
        exit 1
    fi

    # --- CRITICAL CHECK: Verify /etc/docker/daemon.json (Step 1b) ---
    DAEMON_JSON="/etc/docker/daemon.json"
    
    if [ ! -d "/etc/docker" ]; then
        log_fail "Directory /etc/docker is missing! Docker does not automatically create it; you must manually create the directory." >&2
        
        echo -e "\n${RED}Immediate Fix Instructions (run on the builder node):${NC}" >&2
        echo "   Start from the repo's builder sample (BUILDER sample, not the tester one):" >&2
        echo "     cp <rocm-distro-tester>/samples/daemon.json.builder /etc/docker/daemon.json" >&2
        echo "     # ...adjust 'data-root' if your build dir differs, then:" >&2
        echo "     sudo systemctl restart docker" >&2

    elif [ ! -f "$DAEMON_JSON" ]; then
        log_fail "Configuration file $DAEMON_JSON is missing. Without it, Docker defaults to '/var/lib/docker', which will quickly fill your root partition." >&2
        echo "   Fix: cp <rocm-distro-tester>/samples/daemon.json.builder $DAEMON_JSON && sudo systemctl restart docker" >&2

    else
        # The directory and file exist! Now verify the content.
        DAEMON_CONTENT=$(cat "$DAEMON_JSON" 2>/dev/null)
        if [[ $(echo "$DAEMON_CONTENT" | grep -c '"data-root":') -eq 0 ]]; then
            echo "$DAEMON_CONTENT" | head -3 | sed 's/^/  /' >&2
        echo "   Expected (see samples/daemon.json.builder in the repo):" >&2
        echo '     {"data-root": "/rocm-builder"}' >&2
        echo "   If your builder's build dir differs, adjust that value, then: sudo systemctl restart docker" >&2
        log_fail "/etc/docker/daemon.json exists but lacks 'data-root': '/rocm-builder'. Matrix builds will fail due to default storage exhaustion." >&2
            
                # If neither condition is met, we fail out and exit with an error.
                        echo "EOF" | tee /dev/stderr >/dev/null
                        printf '    "data-root": "/rocm-builder"\n' | sed -i '/^$/d' "$DAEMON_JSON"
        else
            # If both conditions are met, we have a config and it points to the correct place.
                log_pass "Docker daemon.json correctly points storage to '/rocm-builder'." 
        fi
    fi
    
    log_info "  sudo systemctl restart docker"

else
    # Reuse OS-specific installation logic (abbreviated)
    echo -e "\n${RED}Docker CLI is missing. Installation recommendations:${NC}" >&2
    if [ "$PKG_MANAGER" = "dnf" ]; then
        cat << 'INSTALL_DOCKER'

## Install Docker Engine:
sudo dnf install docker-ce docker-ce-cli containerd.io
sudo systemctl start docker && sudo systemctl enable docker
# Add user to group!
sudo usermod -aG docker $USER
INSTALL_DOCKER
    elif [ "$PKG_MANAGER" = "apt" ]; then
        cat << 'INSTALL_DOCKER'

## Install Docker Engine:
sudo apt-get update && sudo apt-get install docker-ce docker-ce-cli containerd.io
sudo systemctl start docker && sudo systemctl enable docker
# Add user to group!
sudo usermod -aG docker $USER
INSTALL_DOCKER
    fi
fi

# =============================================================================
# CHECK 2: Registry Alias Validation (Identity Check)
# =============================================================================
echo -e "\n[Step 2/4] Verifying Builder Identity..."

EXPECTED_IP="192.168.1.25"
REGISTRY_ALIAS="rocm-builder"

# Verify that this machine actually IS the expected IP
ACTIVE_IPS=$(hostname -I | tr '[:space:]' '\n')
IDENTITY_OK=false

for IP in $ACTIVE_IPS; do
    if [ "$IP" = "$EXPECTED_IP" ]; then
        IDENTITY_OK=true
        break
    fi
done

if "$IDENTITY_OK"; then
    log_pass "This node correctly identifies as '${EXPECTED_IP}' (Expected Registry IP)."
else
    echo -e "${RED}WARNING: This node's active IPs ($ACTIVE_IPS) do not match the expected builder IP (${EXPECTED_IP}).${NC}" >&2
    log_fail "Do not run image build commands unless this node has the correct static IP: ${EXPECTED_IP}" >&2
fi

# =============================================================================
# CHECK 3: Storage & Mount Point Security (/rocm-builder)
# =============================================================================
echo -e "\n[Step 3/4] Verifying Container Data Root (/rocm-builder)..."

DOCKER_DATA_ROOT="/rocm-builder"

if [ ! -d "$DOCKER_DATA_ROOT" ]; then
    log_fail "CRITICAL: Target directory '$DOCKER_DATA_ROOT' does not exist!" >&2
fi

# Check Storage Volume (>= 500GB). Removed XFS bsize check as requested.
echo -e "[Step 3/4-b] Verifying Disk Space..."
SPACE_CHECK=$(df -BG "$DOCKER_DATA_ROOT" | tail -1)
TOTAL_GB=$(echo "$SPACE_CHECK" | awk '{gsub("G","",$2); print $2}')
REMAINING_GB=$(echo "$SPACE_CHECK" | awk '{gsub("G","",$4); print $4}')

if [ "$TOTAL_GB" -lt 500 ]; then
    log_fail "INSUFFICIENT CAPACITY: /rocm-builder has a total of ${TOTAL_GB}GB. A minimum of 500GB is required." >&2
elif [ "$REMAINING_GB" -lt 100 ]; then
    log_fail "CRITICAL: Only ${REMAINING_GB}GB free on /rocm-builder. Matrix builds will fail due to layer exhaustion." >&2
else
    log_pass "Storage healthy on configured Root Dir (/rocm-builder): ${TOTAL_GB}GB total, ${REMAINING_GB}GB available."
fi

# Check XFS filesystem type (Recommendation only)
echo -e "[Step 3/4-c] Verifying Filesystem Type..."
FILE_SYSTEM_TYPE=$(df --output=fstype "$DOCKER_DATA_ROOT" | tail -1)

if [ "$FILE_SYSTEM_TYPE" = "xfs" ]; then
    log_pass "Filesystem is XFS. Recommended for ROCm builds."
elif [ "$FILE_SYSTEM_TYPE" = "ext4" ]; then
    log_pass "Filesystem is ext4. Acceptable but XFS is strongly recommended for high-throughput large files." >&2
else
    echo -e "${RED}WARNING: Uncommon filesystem (${FILE_SYSTEM_TYPE}). Ensure compatibility with Docker storage drivers.${NC}" >&2
fi

# Verify Permissions (Owner must be root with rwx/7)
echo -e "[Step 4d] Verifying Mount Point Security..."
FILE_PERMS=$(stat -c %a "$DOCKER_DATA_ROOT")
FILE_OWNER=$(stat -c %U "$DOCKER_DATA_ROOT")

if [ "$FILE_OWNER" != "root" ]; then
    log_fail "Security Violation: $DOCKER_DATA_ROOT is owned by '$FILE_OWNER'. Docker daemon requires root ownership." >&2
fi

# Check that the owner (first digit) has 7 (rwx).
OWNER_PERMS=${FILE_PERMS:0:1}
if [ "$OWNER_PERMS" != "7" ]; then
    log_fail "Permissions on $DOCKER_DATA_ROOT are set to $FILE_PERMS. Owner (root) must have 7 (rwx)." >&2
fi
log_pass "Mount point security is correct (Root owner has rwx access)."

# =============================================================================
# FINAL SUMMARY
# =============================================================================
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "\n${GREEN}==========================================${NC}"
    echo -e "${GREEN}--- BUILDER NODE READY FOR WORKLOADS ---${NC}"
    echo -e "${GREEN}==========================================${NC}"
else
    echo -e "\n${RED}==========================================${NC}"
    echo -e "${RED}--- VERIFICATION FAILED: Address issues above ---${NC}"
    echo -e "${RED}==========================================${NC}"
fi

exit "$FAIL_COUNT"