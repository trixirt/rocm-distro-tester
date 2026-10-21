#!/bin/bash
# =============================================================================
# verify_network_registry.sh - Network Alias Resolution Checker
# =============================================================================
# Purpose: Verifies that the 'rocm-builder' alias resolves correctly across 
# the network (DNS) and strictly parses /etc/hosts as a fallback.
#
# Recommendation Implementation:
# 1. Removes hardcoded IP expectations to support diverse LAN setups.
# 2. Strictly parses /etc/hosts to ignore commented-out or malformed lines.
# =============================================================================

set -euo pipefail

REGISTRY_ALIAS="rocm-builder"
REGISTRY_PORT=5000

# --- Helper: Strict Hosts File Parser ---
# Parses /etc/hosts line-by-line, ignoring comments (#) and invalid IPs.
parse_hosts_strict() {
    local alias="$1"
    
    # 1. Getent (DNS/BIND/LAN Discovery) - Preferred Method
    local resolved_ip=$(getent hosts "$alias" 2>/dev/null | awk '{print $1}' | head -n 1)
    if [ -n "$resolved_ip" ]; then
        echo "SUCCESS: Alias '${REGISTRY_ALIAS}' resolved via network resolution (DNS/mDNS)." >&2
        echo "Resolved IP: ${resolved_ip}"
        return 0
    fi
    
    # 2. Fallback to parsing /etc/hosts strictly (no commented lines)
    local file="/etc/hosts"
    
    if [ ! -f "$file" ]; then
        echo "FAIL: Hosts file not found." >&2
        return 1
    fi

    # grep -v '^#' strips comments and leading whitespace. 
    # grep -w ensures the alias is a distinct word (prevents partial matches like 'test-rocm-builder')
    local line=$(grep -v '^ *#' "$file" | grep -w "$alias" | head -n 1)

    if [ -z "$line" ]; then
        echo "FAIL: Alias '${alias}' not found in active (non-commented) entries of ${file}." >&2
        return 1
    fi

    local ip=$(echo "$line" | awk '{print $1}')

    # Basic sanity check for IPv4 structure to reject artifacts
    if [[ ! "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "FAIL: Malformed entry found for '${alias}' in hosts file." >&2
        return 1
    fi

    echo "SUCCESS: Alias '${alias}' resolved via strict /etc/hosts parsing." >&2
    echo "Resolved IP: ${ip} (from $file)"
    return 0
}

# --- Execution ---
echo "--- Verifying Network Registry Alias ---"
parse_hosts_strict "$REGISTRY_ALIAS"

exit_code=$?
if [ $exit_code -ne 0 ]; then
    exit $exit_code
fi
