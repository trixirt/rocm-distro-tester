#!/bin/bash
# =============================================================================
# verify_state_setup.sh - Dynamic ROCm State Stack Reachability Check (Tester)
# =============================================================================
# Purpose: Verifies from a TESTER machine that the state stack (PostgreSQL +
# state-svc + artifact store, PLAN.md Section 7) on host 'rocm-db' is:
#   1. resolvable (rocm-db alias — may live on the SAME machine as rocm-builder)
#   2. HTTP-reachable (state-svc, port 8443)
#   3. able to ACCEPT an artifact push (canary PUT /artifacts, requires NODE_TOKEN)
#
# Modelled after verify_registry_test.sh (same resolve/reach/reuse structure),
# with the registry v2 API replaced by the state-svc push protocol.
#
# Required packages on the CALLING (tester) machine: curl, sha256sum, getent.
#   → curl is the only one not guaranteed by base distros; it is checked for
#     and installed-able via verify_tester_setup.sh.
#
# Usage (from the tester machine):
#   scp verify_state_setup.sh <tester>:/tmp && ssh <tester> /tmp/verify_state_setup.sh
#   NODE_TOKEN=***        # enable step 3 (push canary)
#
# Environment overrides:
#   STATE_HOST=rocm-db   STATE_PORT=8443
# =============================================================================

STATE_HOST="${STATE_HOST:-rocm-db}"
STATE_PORT="${STATE_PORT:-8443}"
REGISTRY_ALIAS="rocm-builder"      # for the same-machine info hint only

echo "=========================================="
echo "--- ROCm State Stack Reachability (from tester) ---"
echo "Target Host: ${STATE_HOST}:${STATE_PORT}"
echo "Same-box hint: compared against '${REGISTRY_ALIAS}'"
echo -e "==========================================\n"

# (Reused from verify_registry_test.sh)
resolve_alias() {
    local a="$1"
    local ip=$(getent hosts "$a" 2>/dev/null | awk '{print $1}' | head -n 1)
    [ -n "$ip" ] && return 0
    local line=$(grep -v '^ *#' /etc/hosts 2>/dev/null | grep -w "$a" | head -n 1)
    if [ -n "$line" ]; then
        ip=$(echo "$line" | awk '{print $1}')
        if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            return 0
        fi
    fi
    return 1
}

# =============================================================================
# STEP 1: Host resolution (rocm-db)
# =============================================================================
echo "[Step 1/3] Resolving state host alias..."

if resolve_alias "$STATE_HOST"; then
    TARGET_IP=$(getent hosts "$STATE_HOST" 2>/dev/null | awk '{print $1}' | head -n 1)
    echo "✅ Resolved '${STATE_HOST}' → ${TARGET_IP}"

    # The state node MAY be the same machine as the builder/registry node.
    if resolve_alias "$REGISTRY_ALIAS" && \
       [ "$(getent hosts "$REGISTRY_ALIAS" 2>/dev/null | awk '{print $1}' | head -n 1)" = "$TARGET_IP" ]; then
        echo "ℹ️  'rocm-builder' resolves to the SAME address — the state stack likely co-hosts with the registry. Expected."
    fi
else
    echo "❌ FAILURE: Could not resolve '${STATE_HOST}'. Check DNS or /etc/hosts." >&2
    echo "   Fix:  sudo echo '<ip> ${STATE_HOST}' | sudo tee -a /etc/hosts" >&2
    exit 1
fi

# =============================================================================
# STEP 2: state-svc HTTP reachability (port 8443)
# =============================================================================
echo -e "\n[Step 2/3] Checking state-svc HTTP endpoint..."

if ! command -v curl &>/dev/null; then
    echo "❌ FAILURE: 'curl' is not installed on this tester — required to push artifacts/results." >&2
    echo "   Fix:  sudo dnf install curl   # or: sudo apt-get install curl" >&2
    exit 1
fi

TARGET="http://${TARGET_IP}:${STATE_PORT}"
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "${TARGET}/" 2>/dev/null)

if [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then
    echo "❌ UNREACHABLE: no HTTP response from ${TARGET}. Is the state stack (docker compose state.yml) up on ${TARGET_IP}?" >&2
    exit 1
fi

case "$HTTP_CODE" in
    2*)
        echo "✅ state-svc is LIVE at ${TARGET} (HTTP ${HTTP_CODE})."
        ;;
    401|403|404|405)
        echo "✅ state-svc is ALIVE at ${TARGET} (HTTP ${HTTP_CODE} — service up; route/auth expected)."
        ;;
    *)
        echo "ℹ️  Port ${STATE_PORT} open but unexpected HTTP ${HTTP_CODE} — verify the state stack is bound to that port."
        ;;
esac

# =============================================================================
# STEP 3: CANARY artifact push (PUT /artifacts?key=<sha256>)
# =============================================================================
echo -e "\n[Step 3/3] Verifying artifact-push path (canary upload)..."

if [ -z "${NODE_TOKEN:-}" ]; then
    echo "ℹ️  NODE_TOKEN not set — cannot authenticate the canary PUT. (Expected before node onboarding.)" >&2
    echo "    Re-run with NODE_TOKEN=*** to fully validate the push path." >&2
else
    CANARY_FILE="$(mktemp /tmp/rocm-state-canary.XXXXXX)"
    echo "rocm-state canary $(date -u +%Y-%m-%dT%H:%M:%SZ) node=$(hostname) — safe to delete" > "$CANARY_FILE"
    SHA256="$(sha256sum "$CANARY_FILE" | cut -d' ' -f1)"

    PUT_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
        -X PUT -H "Authorization: Bearer ${NODE_TOKEN}" \
        --data-binary @"${CANARY_FILE}" \
        "${TARGET}/artifacts?key=${SHA256}" 2>/dev/null)

    rm -f "$CANARY_FILE"

    case "${PUT_CODE:-000}" in
        200|201)
            echo "✅ ARTIFACT PUSH VERIFIED: canary accepted at sha256=${SHA256} (HTTP ${PUT_CODE})."
            echo "   This exercises the exact upload path the job runners use. Server-side copy can be GC'd (it is a canary)."
            ;;
        401|403)
            echo "❌ AUTH FAILED on canary PUT (HTTP ${PUT_CODE}). NODE_TOKEN unknown or node not registered." >&2
            exit 1
            ;;
        *)
            echo "❌ CANARY PUT FAILED (HTTP '${PUT_CODE:-000/no-response}') to ${TARGET}/artifacts. Check state-svc route + node registration." >&2
            exit 1
            ;;
    esac
fi

echo -e "\n=========================================="
echo "--- State Stack Reachability Complete ---"
echo "From this tester, the state stack at ${STATE_HOST}:${STATE_PORT} is reachable."
echo -e "==========================================\n"
