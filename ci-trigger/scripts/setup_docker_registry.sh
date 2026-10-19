#!/bin/bash
# =============================================================================
# setup_docker_registry.sh - ROCm Registry Deployment (BOTH tiers)
# =============================================================================
# Purpose: Deploys the two local Docker registries (registry:2) on the builder
# node using the dedicated /rocm-builder storage root:
#
#   TIER   HOST PORT  CONTAINER            STORAGE                        IMAGES
#   ----   ---------  -------------------  ---------------------------    -------------------------------
#   test      5000    rocm-registry        /rocm-builder/registry-test    matrix test images (PLAN §6)
#   infra     5001    rocm-infra-registry  /rocm-builder/registry-infra   postgres/state-svc/dashboard (PLAN §7.5.1)
#
# Security model: testers trust ONLY :5000 (samples/daemon.json.tester). The
# infra registry is reachable by the builder (loopback) and state nodes only.
#
# Usage:
#   ./setup_docker_registry.sh [--tier test|infra|both] [--dry-run] [--verbose] [--help]
#
# Env overrides: STORAGE_ROOT (default /rocm-builder), TEST_PORT (5000),
#                INFRA_PORT (5001)
# =============================================================================

set -euo pipefail

REGISTRY_IMAGE="registry:2"
STORAGE_ROOT="${STORAGE_ROOT:-/rocm-builder}"
TEST_PORT="${TEST_PORT:-5000}"
INFRA_PORT="${INFRA_PORT:-5001}"
TIER="both"
DRY_RUN=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --tier) TIER="${2:?--tier requires test|infra|both}"; shift 2;;
        --dry-run) DRY_RUN=true; shift;;
        --verbose|-v) VERBOSE=true; shift;;
        --help|-h) cat << 'HELPUSAGE'

ROCm Registry Setup Script (test + infra tiers)
===============================================

Deploys local Docker registries on the builder for image distribution:

  --tier test    rocm-registry          host :5000   (matrix test images)
  --tier infra   rocm-infra-registry    host :5001   (postgres/state-svc/dashboard)
  --tier both    (default)

OPTIONS:
  --tier TIER    Which registry tier(s) to deploy (test|infra|both)
  --dry-run      Show what would be done without changes
  --verbose, -v  Verbose output during setup
  --help, -h     Show this help

POST-SETUP STEPS:
  test tier  -> testers need the trust entry: samples/daemon.json.tester
  infra tier -> state node (if != builder) needs:      samples/daemon.json.db
  builder    -> no extra docker config (loopback-HTTP covers 127.0.0.1:* ports)

See PLAN.md Section 6 and Section 7.5.1 for full operational details.
HELPUSAGE
        exit 0;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 1;;
    esac
done

case "$TIER" in test|infra|both) ;; *) echo "ERROR: --tier must be test|infra|both (got '${TIER}')" >&2; exit 1;; esac
if [ "$VERBOSE" = "true" ]; then set -x; fi

log()  { echo -e "[REGISTRY] $(date '+%Y-%m-%d %H:%M:%S') - $*"; }
fail() { echo -e "[REGISTRY] ERROR: $*" >&2; exit 1; }

# HTTP liveness probe with fallbacks (registry:2 image itself ships no curl)
http_ok() {
    local url="$1" hostport host port
    if command -v curl &>/dev/null; then
        curl -fsS --max-time 5 "$url" >/dev/null 2>&1
    elif command -v wget &>/dev/null; then
        wget -q -T 5 -O /dev/null "$url" 2>/dev/null
    else
        # last resort: raw TCP connect (proves the port is open)
        hostport="${url#http://}"
        host="${hostport%%/*}"; port="${host##*:}"; host="${host%%:*}"
        (exec 3<>"/dev/tcp/${host}/${port}" && exec 3>&- 3<&-) 2>/dev/null
    fi
}

# =============================================================================
# PER-TIER SETUP
# =============================================================================
setup_one() {
    local tier="$1" name="$2" port="$3" datadir="$4"

    log "=== Tier '${tier}': ${name} @ host port ${port} (storage: ${datadir}) ==="

    # --- Storage validation (strict for real runs; warn-only under --dry-run) ---
    if [ ! -d "$STORAGE_ROOT" ]; then
        if [ "$DRY_RUN" = "true" ]; then
            log "  [dry-run][WARN] ${STORAGE_ROOT} absent — a real run needs it: mount the dedicated drive first (verify_db_setup.sh / verify_builder_setup.sh)"
        else
            fail "${STORAGE_ROOT} does not exist. Mount the dedicated drive and create it first (see verify_db_setup.sh / verify_builder_setup.sh)."
        fi
    else
        local perms owner user
        perms=$(stat -c '%a' "$STORAGE_ROOT" 2>/dev/null || echo 'N/A')
        owner=$(stat -c '%U' "$STORAGE_ROOT" 2>/dev/null || echo 'N/A')
        user=$(id -un)
        if [ "$owner" = "root" -o "$owner" = "$user" ] && [ "$perms" = "755" ] && [ -r "$STORAGE_ROOT" ]; then
            log "  storage OK: ${STORAGE_ROOT} (${owner}:755, readable by ${user})"
        elif [ "$DRY_RUN" = "true" ]; then
            log "  [dry-run][WARN] ${STORAGE_ROOT} is '${owner}:${perms}' — a real run needs owner root|${user} mode 755 (see verify_builder_setup.sh)"
        else
            fail "${STORAGE_ROOT} is owned by '${owner}' mode '${perms}' — must be mode 755 owned by 'root' or '${user}' and readable (see verify_builder_setup.sh)."
        fi
    fi

    # The registry itself writes as root (root docker daemon + in-container
    # root), so a root-owned 755 datadir is sufficient; the invoker only needs
    # it to be readable/traversable. If absent and the parent is user-writable,
    # mkdir -p below creates it; otherwise the admin pre-creates it.
    if [ ! -d "$datadir" ] && [ ! -w "$STORAGE_ROOT" ]; then
        if [ "$DRY_RUN" = "true" ]; then
            log "  [dry-run][WARN] ${datadir} absent and ${STORAGE_ROOT} not writable by ${user} — admin pre-create: sudo mkdir -p ${datadir} && sudo chmod 755 ${datadir}"
        else
            fail "${datadir} does not exist and ${STORAGE_ROOT} is not writable by '${user}' (a root-owned parent, as intended). Admin pre-create: sudo mkdir -p \"${datadir}\" && sudo chmod 755 \"${datadir}\""
        fi
    fi

    # Loopback trust: Docker's default loopback-HTTP exception covers
    # 127.0.0.1:<any-port>, so no insecure-registries entry is needed for
    # same-host pushes/pulls to either registry.
    log "  loopback trust: 127.0.0.1:${port} — no builder daemon.json change required."

    if [ "$DRY_RUN" = "true" ]; then
        log "  [dry-run] docker run -d --name ${name} --restart unless-stopped \\"
        log "            -p ${port}:5000 -v ${datadir}:/var/lib/registry --label rocm-tier=${tier} ${REGISTRY_IMAGE}"
        return 0
    fi

    mkdir -p "${datadir}"

    # Clean up any previous instance
    docker stop "$name" >/dev/null 2>&1 || true
    docker rm   "$name" >/dev/null 2>&1 || true

    log "  starting '${name}' from ${REGISTRY_IMAGE}"
    docker run -d \
        --name "$name" \
        --restart unless-stopped \
        -p "${port}:5000" \
        -v "${datadir}:/var/lib/registry" \
        --label "rocm-tier=${tier}" \
        "$REGISTRY_IMAGE" >/dev/null

    sleep 3

    local url="http://localhost:${port}"
    if http_ok "${url}/v2/_catalog"; then
        log "  ✓ ${name} healthy at ${url} (catalog endpoint OK)"
        if [ "$tier" = "infra" ]; then
            log "  NOTE: pin the infra images here for offline state-stack boot, e.g.:"
            log "        docker pull postgres:16"
            log "        docker tag  postgres:16  \${BUILDER_ALIAS}:${port}/postgres"
            log "        docker push \${BUILDER_ALIAS}:${port}/postgres"
        fi
    else
        docker logs "$name" 2>&1 | tail -5 >&2 || true
        fail "${name} failed the liveness check on port ${port} (log lines above); audit with scripts/verify_registry_${tier}.sh"
    fi
}

# =============================================================================
# MAIN
# =============================================================================
log "ROCm registry setup starting (tier=${TIER}, storage=${STORAGE_ROOT})"
if [ "$DRY_RUN" = "true" ]; then
    log "  running in DRY-RUN mode (no docker, no filesystem writes)"
fi

if [ "$TIER" = "test" ] || [ "$TIER" = "both" ]; then
    setup_one "test"  "rocm-registry"       "$TEST_PORT"  "${STORAGE_ROOT}/registry-test"
fi

if [ "$TIER" = "infra" ] || [ "$TIER" = "both" ]; then
    setup_one "infra" "rocm-infra-registry" "$INFRA_PORT" "${STORAGE_ROOT}/registry-infra"
fi

# =============================================================================
# POST-SETUP GUIDE (informational; the per-tier work is host-specific)
# =============================================================================
log "Per-tier next steps:"
if [ "$TIER" = "test" ] || [ "$TIER" = "both" ]; then
    log "  [test/:5000]  each TESTER machine: trust entry from samples/daemon.json.tester → sudo systemctl restart docker → check with scripts/verify_registry_test.sh"
fi
if [ "$TIER" = "infra" ] || [ "$TIER" = "both" ]; then
    log "  [infra/:5001] state node (if NOT the builder): trust entry from samples/daemon.json.db → check with scripts/verify_db_setup.sh"
    log "                if the state node IS the builder: nothing extra — 127.0.0.1:* is loopback-trusted by default"
fi
log "Audit any time: scripts/verify_registry_test.sh  |  scripts/verify_registry_infra.sh"
