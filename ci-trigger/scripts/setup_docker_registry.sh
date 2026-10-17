#!/bin/bash
# =============================================================================
# setup_docker_registry.sh - ROCm Local Registry Deployment Script
# =============================================================================
# Purpose: Deploys the local Docker Registry (registry:2) on the builder node
# using the dedicated /rocm-builder storage root.
#
# Usage:
#   ./setup_docker_registry.sh [--dry-run] [--verbose] [--help]
# =============================================================================

set -euo pipefail

REGISTRY_NAME="rocm-registry"
REGISTRY_PORT=5000
DATA_ROOT="/rocm-builder/registry-data"

DRY_RUN=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift;;
        --verbose|-v) VERBOSE=true; set -x; shift;;
        --help|-h) cat << HELPUSAGE

ROCm-Tester Docker Registry Setup Script
=========================================

Deploys local Docker registry on builder for efficient image distribution.

USAGE:
  ./setup_docker_registry.sh [OPTIONS]

OPTIONS:
  --dry-run       Show what would be done without changes
  --verbose, -v   Verbose output during setup
  --help, -h      Show this help message

POST-SETUP STEPS (see PLAN.md Section 6 for details):
1. Configure test machines to trust registry at http://<builder>:5000
2. Build and push images using scripts/build-all-images.sh
3. Verify connectivity from test machines

HELPUSAGE
        exit 0;;
    esac
done

log() { echo "[REGISTRY] \$(date '+%Y-%m-%d %H:%M:%S') -\$*"; }

if [ "$DRY_RUN" = "true" ]; then
    log "Running in dry-run mode"
else
    if ! command -v docker &>/dev/null; then
        echo "ERROR: Docker not installed. Aborting." >&2
        exit 1
    fi
    
    # --- Storage Validation (Strict /rocm-builder requirement) ---
    if [ ! -d "/rocm-builder" ]; then
        echo "ERROR: /rocm-builder directory does not exist." >&2
        echo "Please mount your dedicated drive and create this directory before running setup scripts." >&2
        exit 1
    fi

    # Check strict permissions required by Docker daemon (root, mode 0700)
    FILE_PERMS=$(stat -c %a /rocm-builder 2>/dev/null || echo "N/A")
    if [ "$FILE_PERMS" != "700" ]; then
        echo "ERROR: /rocm-builder permissions are incorrect (${FILE_PERMS})." >&2
        echo "Permissions must be '0700' (owner-only read/write) to ensure Docker daemon security." >&2
        exit 1
    fi

    # Create the specific subdirectory for registry data
    mkdir -p "${DATA_ROOT}"
    
    # Clean up any previous failed attempts
    docker stop "${REGISTRY_NAME}" >/dev/null 2>&1 || true
    docker rm "${REGISTRY_NAME}" >/dev/null 2>&1 || true
    
    # Deploy registry container with the new storage path
    log "Starting 'rocm-registry' using data root: ${DATA_ROOT}"
    docker run -d \
        --name "${REGISTRY_NAME}" \
        --restart unless-stopped \
        -p "${REGISTRY_PORT}:5000" \
        -v "${DATA_ROOT}:/var/lib/registry" \
        registry:2
    
    sleep 3
    
    # Validate deployment
    if curl -s http://localhost:${REGISTRY_PORT}/v2/_catalog >/dev/null; then
        log "✓ Registry successfully deployed at http://localhost:${REGISTRY_PORT}"
        echo ""
        cat << 'INSTRUCTIONS'

NEXT STEPS (configure each test machine):
1. Edit /etc/docker/daemon.json on the GUEST nodes:
   {
     "insecure-registries": ["<builder-hostname>:5000"]
   }
   
2. Restart Docker daemon on all guest nodes:
   sudo systemctl restart docker

3. Verify connectivity from a test node:
   curl http://<builder-hostname>:5000/v2/_catalog
   
See PLAN.md Section 6 for full operational details.
INSTRUCTIONS
    else
        echo "WARNING: Registry validation failed on builder. Check logs with: docker logs ${REGISTRY_NAME}" >&2
        exit 1
    fi
fi
