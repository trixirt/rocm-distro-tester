#!/bin/bash
set -euo pipefail

REGISTRY_NAME="rocm-registry"
REGISTRY_PORT=5000

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

POST-SETUP STEPS (see README.md for details):
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
        echo "ERROR: Docker not installed" >&2
        exit 1
    fi
    
    # Create storage directory
    mkdir -p /var/lib/registry/docker-registry
    
    # Remove existing container if any
    docker stop "${REGISTRY_NAME}" >/dev/null 2>&1 || true
    docker rm "${REGISTRY_NAME}" >/dev/null 2>&1 || true
    
    # Deploy registry container
    docker run -d \
        --name "${REGISTRY_NAME}" \
        --restart unless-stopped \
        -p "${REGISTRY_PORT}:5000" \
        -v /var/lib/registry/docker-registry:/var/lib/registry \
        registry:2
    
    sleep 3
    
    if curl -s http://localhost:${REGISTRY_PORT}/v2/_catalog >/dev/null; then
        log "✓ Registry running at http://localhost:${REGISTRY_PORT}"
        echo ""
        cat << 'INSTRUCTIONS'

NEXT STEPS (configure each test machine):
1. Edit /etc/docker/daemon.json:
   {
     "insecure-registries": ["<builder-hostname>:5000"]
   }
   
2. Restart Docker daemon:
   sudo systemctl restart docker

3. Verify connectivity:
   docker run --rm <builder hostname>:5000/image-name
   
See PLAN.md Section 6 for full details.
INSTRUCTIONS
    else
        echo "WARNING: Registry validation failed. Check logs with: docker logs ${REGISTRY_NAME}" >&2
        exit 1
    fi
fi
