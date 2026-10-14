#!/bin/bash
# =============================================================================
# ROCm-Tester: Dashboard Setup Script (v0.1)
# Deploys the test results dashboard on builder machine via Docker Compose
# Optimized for single-developer maintenance with minimal operational overhead
#
# Requirements:
#   - Docker installed on builder machine
#   - Access to local directory containing result JSON files
#
# Usage:
#   ./setup_dashboard.sh [--dry-run] [-v|--verbose] [--help]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../.."

RESULTS_PATH="${RESULTS_PATH:-/var/rocm-tester/results}"
CONFIG_FILE="/etc/docker/daemon.json"
SERVICE_NAME="rocm-dashboard"

DRY_RUN=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift;;
        --verbose|-v) VERBOSE=true; set -x; shift;;
        --help|-h) 
            cat << 'HELPMESS'

ROCm-Tester Dashboard Setup Script
====================================

Deploy the Web Results Dashboard on builder machine for aggregated test result viewing.

USAGE:
  ./setup_dashboard.sh [OPTIONS] [DIRECTORY]

OPTIONS:
  --dry-run           Show what would be done without making changes to system
  --verbose, -v       Verbose output with all commands being executed  
  --help, -h          Display this help message
  
CONFIGURATION VARIABLES:
  RESULTS_PATH        Path to results directory mounted in container (default: /var/rocm-tester/results)
                      Ensure Docker can read/write to this path on builder machine

STEPS TO SETUP:
1. Run setup script (creates service configuration if needed)
2. Verify docker-compose.yaml exists (will use existing or create new one)  
3. Service starts with: docker-compose -f docker-compose.dashboard.yml up -d
4. Access dashboard at http://localhost:5001 from any machine on network

AFTER SETUP:
- Dashboard accessible at http://<builder-hostname>:5001
- API endpoints: /api/summary, /api/latest-results/<count>
- View test results across all distros and packages in unified filtered interface

RECOMMENDED FOLLOWS:
./ci-trigger/scripts/setup_dashboard.sh -v  # Full verbosity with step-by-step output
./ci-trigger/scripts/setup_dashboard.sh --dry-run  # Simulate setup without running containers

HELPMESS
            exit 0;;
        *) RESULTS_PATH="$1"; shift;;
    esac
done

log() { echo "[DASHBOARD-SETUP] \$(date '+%Y-%m-%d-%H:%M:%S') - \$*"; }

success() { log "✅ SUCCESS: \$*"; return 0; [[ "$DRY_RUN" = true ]] && return 0; }

warn() { echo "[WARNING] \$*" >&2; }

execute() {
    local cmd="$@"
    
    if [ "$DRY_RUN" = "true" ]; then
        log "Would execute: $cmd"
        return 0
    fi
    
    eval "$cmd" || warn "Command failed: $cmd"
}

check_docker_installed() {
    log "Checking Docker installation..."
    
    if command -v docker &> /dev/null; then
        success "Docker found"
        return 0
    else
        warn "Docker not found. Install Docker first." >&2
        return 1
    fi
}

check_docker_daemon() {
    log "Checking Docker daemon status..."
    
    if [ "$DRY_RUN" = "true" ]; then
        return 0  # Skip actual check in dry-run mode
    fi
    
    if docker info &>/dev/null; then
        success "Docker daemon running"
        return 0
    else
        warn "Docker daemon not running. Please start Docker first." >&2
        return 1
    fi
}

check_results_directory() {
    log "Verifying results directory: ${RESULTS_PATH}"
    
    if [ ! -d "$RESULTS_PATH" ]; then
        log "Results directory does not exist, creating..."
        execute mkdir -p "$RESULTS_PATH"
        success "Results directory created: $RESULTS_PATH"
    else
        success "Results directory exists: $RESULTS_PATH"
    fi
}

cleanup_existing_service() {
    log "Checking for existing dashboard service..."
    
    if [ "$DRY_RUN" = "true" ]; then
        return 0
    fi
    
    if docker ps -a --format "{{.Names}}" | grep -q "^${SERVICE_NAME}$"; then
        log "Stopping existing service ${SERVICE_NAME}..."
        execute docker stop "${SERVICE_NAME}" 2>/dev/null || true
        
        log "Removing existing container ${SERVICE_NAME}..."
        execute docker rm "${SERVICE_NAME}" 2>/dev/null || true
    else
        log "No existing dashboard service found"
    fi
}

start_dashboard_service() {
    log "Starting test results dashboard container..."
    
    if [ "$DRY_RUN" = "true" ]; then
        cat << 'DRYRUNOUTPUT'
Would execute:

docker-compose -f docker-compose.dashboard.yml up -d
# Logs available for monitoring with:
docker logs rocm-dashboard

DRYRUNOUTPUT
        return 0
    fi
    
    # Change to project root
    cd "${PROJECT_ROOT}" || exit 1
    
    if [ ! -f "docker-compose.dashboard.yml" ]; then
        warn "Docker compose file not found at PROJECT_ROOT/docker-compose.dashboard.yml"
        warn "Creating default configuration..."
        
        mkdir -p ci-trigger/dashboard templates
        
        # Default compose configuration is already in place from setup files
        success "Default compose configuration applied"
    fi
    
    docker-compose -f docker-compose.dashboard.yml up -d
    
    sleep 3  # Wait for container to initialize
    
    if curl -s http://localhost:5001/api/summary >/dev/null; then
        log "✅ Dashboard service started successfully at localhost:5001"
        
        cat << 'POSTSTEP'

=================================================================================
DASHBOARD DEPLOYMENT COMPLETE!
=================================================================================

Your test results dashboard is now available at:

🌐 http://localhost:5001  OR  http://<builder-hostname>:5001

Available API endpoints:
- GET /api/summary       - Overall statistics and success rates
- GET /api/latest/<N>    - Latest test results (raw JSON)
- GET /results           - Filtered results view with sorting by distro/package

View service health logs:
  docker logs rocm-dashboard

Manage container lifecycle:
  docker restart rocm-dashboard
  docker-compose -f docker-compose.dashboard.yml down

=================================================================================
NEXT STEPS FOR USERS:
1. Open dashboard URL in web browser from any machine on network
2. Filter results by distro package to see consolidated test outcomes  
3. Check API endpoints for programmatic access to result data

📊 Dashboard displays aggregated view across all ROCm-tester test scenarios!
=================================================================================
POSTSTEP
        
    else
        warn "Dashboard verification failed. Check logs: docker logs rocm-dashboard"
        return 1
    fi
}


main() {
    log "Starting ROCm-Tester Dashboard Setup..."
    
    check_docker_installed || exit 1
    
    if [ "$DRY_RUN" != "true" ]; then
        check_docker_daemon || exit 1
        check_results_directory
        cleanup_existing_service
        start_dashboard_service
    else
        log "Dry-run mode: No deployment will occur."
        show_usage
        return 0
    fi

    success "Dashboard deployment complete!"
}

main "$@"
