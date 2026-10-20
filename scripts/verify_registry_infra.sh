#!/bin/bash
# =============================================================================
# verify_registry_infra.sh - ROCm INFRA Registry Audit (port 5001)
# =============================================================================
# Purpose: Verifies connectivity to the INFRA-STRUCTURE registry (rocm-builder:5001),
# validates TCP port reachability, lists all currently hosted images, and
# checks the expected pins (postgres:16, rocm-state-svc, rocm-dashboard) so
# the state stack can boot offline (PLAN §7.5.1).
#
# Companion: verify_registry_test.sh audits the :5000 TEST-IMAGE registry.
# Design: run from the BUILDER itself — testers are deliberately NOT trusted
# to reach :5001 (that boundary is the point of the tier split).
#
# Usage (on the builder):
#   ./verify_registry_infra.sh
# =============================================================================

REGISTRY_ALIAS="${REGISTRY_ALIAS:-rocm-builder}"
REGISTRY_PORT=5001

echo -e "\n=========================================="
echo "--- ROCm INFRA Registry Audit (port ${REGISTRY_PORT}) ---"
echo "Target Alias: ${REGISTRY_ALIAS}:${REGISTRY_PORT}"
echo -e "==========================================================================\n"

# =========================================================================
# Step 1: Strict /etc/hosts Resolution
# =========================================================================
echo "[Step 1/4] Resolving host alias from /etc/hosts..."

resolve_alias() {
    local a="$1"
    local line=$(grep -v '^ *#' /etc/hosts 2>/dev/null | grep -w "$a" | head -n 1)
    if [ -n "$line" ]; then
        ip=$(echo "$line" | awk '{print $1}')
        if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            return 0
        fi
    fi
    return 1
}

if resolve_alias "$REGISTRY_ALIAS"; then
    TARGET_IP=$(grep -v '^ *#' /etc/hosts 2>/dev/null | grep -w "$REGISTRY_ALIAS" | head -n 1 | awk '{print $1}')
    echo "✅ Resolved '${REGISTRY_ALIAS}' → ${TARGET_IP}"
else
    echo "❌ FAILURE: Could not resolve '${REGISTRY_ALIAS}'. Ensure it is explicitly listed in /etc/hosts." >&2
    exit 1
fi

# =========================================================================
# Step 2: Validate INFRA registry v2 API
# =========================================================================
echo -e "\n[Step 2/4] Checking INFRA registry v2 API (port ${REGISTRY_PORT})..."
TARGET="http://${TARGET_IP}:${REGISTRY_PORT}"

CURL_RESPONSE=$(curl -sv "${TARGET}/v2/" --max-time 5 2>&1)
CURL_STATUS=$(echo "$CURL_RESPONSE" | grep "< HTTP" | awk '{print $3}' || echo "")

if [[ -z "$CURL_STATUS" ]] || [[ ! "$CURL_STATUS" =~ ^[245][0-9][0-9]$ ]]; then
    echo "❌ API NOT REACHABLE: INFRA registry returned HTTP ${CURL_STATUS:-<none>}. " >&2
    echo "   The second registry container (rocm-infra, compose port ${REGISTRY_PORT}) must be up on the builder." >&2
    exit 1
fi

echo "✅ INFRA registry v2 API is ONLINE at ${TARGET}"

# =========================================================================
# Step 3: Parse & display the (small) infra image inventory
# =========================================================================
echo -e "\n[Step 3/4] Scanning infra registry inventory..."
CURL_OUTPUT=$(curl -s "${TARGET}/v2/_catalog")

REPOS_ALL=""
if command -v python3 &>/dev/null; then
    REPOS_ALL=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); [print(r) for r in d.get('repositories', [])]" <<< "$CURL_OUTPUT" 2>/dev/null) || true
else
    REPOS_ALL=$(echo "$CURL_OUTPUT" | tr ',' '\n' | sed -n 's/.*"\(.*\).*/\1/p' | sort -u)
fi

if [ -n "$REPOS_ALL" ]; then
    REPO_COUNT=0
    while IFS= read -r repo; do
        [ -z "$repo" ] && continue
        echo "  📦 ${REGISTRY_ALIAS}:${REGISTRY_PORT}/${repo}"
        ((REPO_COUNT++))
    done <<< "$REPOS_ALL"
    echo "  Total infra repositories hosted: ${REPO_COUNT}"
else
    echo "ℹ️  INFRA registry is CONNECTED but EMPTY — the state stack images have not been pushed yet." >&2
fi

# =========================================================================
# Step 4: Expectation check — state-stack pins for offline boot (PLAN §7.5.1)
#         Missing pins = WARNING, not failure: the registry is new until
#         Phase 7.x build; absence only means first boot needs upstream pull.
# =========================================================================
echo -e "\n[Step 4/4] Checking expected infrastructure pins..."
EXPECTED_REPOS=("postgres" "rocm-state-svc" "rocm-dashboard")
WARNINGS=0
for repo in "${EXPECTED_REPOS[@]}"; do
    if echo "$REPOS_ALL" | grep -qx "$repo"; then
        echo "✅ present:  ${REGISTRY_ALIAS}:${REGISTRY_PORT}/${repo}"
    else
        echo "⚠️  MISSING:  ${REGISTRY_ALIAS}:${REGISTRY_PORT}/${repo} — state stack will pull from upstream on first boot" >&2
        ((WARNINGS++))
    fi
done

echo -e "\n=========================================="
echo "--- INFRA Registry Audit Complete (warnings: ${WARNINGS}) ---"
echo -e "==========================================================================\n"
