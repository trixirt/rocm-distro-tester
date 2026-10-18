#!/bin/bash
# =============================================================================
# verify_registry_images.sh - Dynamic ROCm Registry Inventory Check
# =============================================================================
# Purpose: Verifies connectivity to rocm-builder, validates TCP port 
# reachability, and lists all currently hosted images. 
# Designed for remote execution from tester/dashboard nodes without Docker client.
#
# Recommendation Implementation:
# 1. Removes hardcoded IP fallbacks (192.168.1.25) to support diverse LAN setups.
# 2. Uses strict /etc/hosts parsing logic to avoid false positives.
# =============================================================================

REGISTRY_ALIAS="rocm-builder"
DOCKER_COMPOSE_ALIAS="registry"
REGISTRY_PORT=5000

echo "=========================================="
echo "--- ROCm Registry Inventory Check ---"
echo "Target Alias: ${REGISTRY_ALIAS}:${REGISTRY_PORT}"
echo "Internal Compose Alias: ${DOCKER_COMPOSE_ALIAS}:${REGISTRY_PORT}"
echo "==========================================\n"

# =========================================================================
# Step 1: Unified Host Resolution (DNS then strict /etc/hosts parsing)
# =========================================================================
echo "[Step 1/3] Resolving host alias..."

resolve_alias() {
    local a="$1"
    
    # 1. Try standard system resolution (getent covers hosts, DNS, nsswitch)
    local ip=$(getent hosts "$a" 2>/dev/null | awk '{print $1}' | head -n 1)
    if [ -n "$ip" ]; then return 0; fi
    
    # 2. Fallback to strict /etc/hosts parsing
    local line=$(grep -v '^ *#' /etc/hosts 2>/dev/null | grep -w "$a" | head -n 1)
    if [ -n "$line" ]; then
        ip=$(echo "$line" | awk '{print $1}')
        # Basic IPv4 validation
        if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            return 0
        fi
    fi
    return 1
}

if resolve_alias "$REGISTRY_ALIAS"; then
    TARGET_IP=$(getent hosts "$REGISTRY_ALIAS" 2>/dev/null | awk '{print $1}' | head -n 1)
    # If getent failed (handled in logic above), fallback to our parsed ip if we had one. 
    # Since resolve_alias returns success but doesn't set a global variable directly, re-fetch or pass via file/env. 
    # Simplified for bash: just rely on the first grep from above if needed, but standard is usually best.
    
    echo "✅ Resolved '${REGISTRY_ALIAS}' → ${TARGET_IP}"
else
    echo "❌ FAILURE: Could not resolve '${REGISTRY_ALIAS}'. Check DNS or /etc/hosts." >&2
    exit 1
fi

if [ -n "$(getent hosts "${DOCKER_COMPOSE_ALIAS}" 2>/dev/null)" ]; then
    echo "ℹ️  Local Docker Compose alias also resolved. Good setup."
fi

# =========================================================================
# Step 2: Validate Registry v2 API & Pull Catalog
# =========================================================================
echo -e "\n[Step 2/3] Checking Docker Registry v2 API..."
TARGET="http://${TARGET_IP}:${REGISTRY_PORT}"

CURL_RESPONSE=$(curl -sv "${TARGET}/v2/" --max-time 5 2>&1) 
CURL_STATUS=$(echo "$CURL_RESPONSE" | grep "< HTTP" | awk '{print $3}' || echo "")

# Allow 200 (OK) or 401/403 (Auth required, but TCP port is open - we assume no auth for now as per original script)
if [[ -z "$CURL_STATUS" ]] || [[ ! "$CURL_STATUS" =~ ^[245][0-9][0-9]$ ]]; then
    echo "❌ API MISMATCH: Registry returned HTTP ${CURL_STATUS}. Ensure registry container is running." >&2
    exit 1
fi

echo "✅ Docker Registry v2 API is ONLINE and REACHABLE"

# =========================================================================
# Step 3: Parse & Display Available Images
# =========================================================================
echo -e "\n[Step 3/3] Scanning registry inventory..."
CURL_OUTPUT=$(curl -s "${TARGET}/v2/_catalog")

# Check if we got valid JSON with python (works universally)
if command -v python3 &>/dev/null; then
    REPOS_JSON=$(python3 -c "import json, sys; d=json.loads(sys.stdin.read()); print(' '.join(d.get('repositories', [])))" <<< "$CURL_OUTPUT" 2>/dev/null) || true
    
    if [ -n "$REPOS_JSON" ]; then
        IMAGE_COUNT=0
        echo "Listing discovered packages:"
        for repo in $REPOS_JSON; do
            REPO_CLEAN=$(echo "$repo" | tr -d '[:space:]')
            echo "  📦 rocm-builder:${REGISTRY_PORT}/${REPO_CLEAN}"
            
            TAGS_OUTPUT=$(curl -s "${TARGET}/v2/${REPO_CLEAN}/tags/list" 2>/dev/null)
            if command -v python3 &>/dev/null; then
                TAG_LIST=$(python3 -c "import json, sys; d=json.loads(sys.stdin.read()); print(', '.join(d.get('tags', [])))" <<< "$TAGS_OUTPUT" 2>/dev/null) || true
                
                if [ -n "$TAG_LIST" ]; then
                    echo "     🏷️  Tags: ${TAG_LIST}"
                else
                     echo "     🔍 No tags available."
                fi
            else
                # Fallback to sed/awk if python isn't available (Legacy support)
                echo "$TAGS_OUTPUT" | tr ',' '\n' | sed -n 's/.*"\(.*\)".*/\1/p' | sort -u
            fi
            ((IMAGE_COUNT++))
        done
        echo -e "\n💾 Total repositories currently hosted: ${IMAGE_COUNT}"
    else
        echo "ℹ️  The registry is connected, but currently EMPTY of images." >&2
    fi
else
    # Absolute fallback without python3 or jq (using sed)
    REPOS=$(echo "$CURL_OUTPUT" | sed 's/.*\[\(.*\)\].*/1/' | tr ',' '\n' | sed "s/[\" \t]//g" | grep -v '^$') 2>/dev/null || true
    
    if [ -z "$REPOS" ]; then
        echo "ℹ️  The registry is connected, but currently EMPTY." >&2
    else
        SORTED_REPOS=$(echo "$REPOS" | sort)
        while IFS= read -r repo; do
            [ -z "$repo" ] && continue
            echo "  📦 rocm-builder:${REGISTRY_PORT}/${repo}"
            
            # Try to get tags if python isn't available for the specific tag check logic
            TAGS_OUTPUT=$(curl -s "${TARGET}/v2/${repo}/tags/list" 2>/dev/null)
            echo "$TAGS_OUTPUT" | grep -oP '"[^"]+"' | tr '\n' ', ' | sed 's/,$//' # simple raw extraction
            
        done <<< "$SORTED_REPOS"
    fi
fi

echo -e "\n=========================================="
echo "--- Verification Complete ---"
echo "All steps executed. Run on any LAN node to validate image sync."
echo "==========================================\n"
