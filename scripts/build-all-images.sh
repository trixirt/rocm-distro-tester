#!/bin/bash
# =============================================================================
# ROCm-Tester: Build and Push All Docker Images to Registry
# =============================================================================
# Builds all test images for supported distros (Fedora, Ubuntu, RHEL) 
# Once built, pushes everything to the local registry for deployment to 
# all test machine nodes via pull operation.
#
# Usage:
#   ./scripts/build-all-images.sh [--dry-run] [--force-rebuild] [distro]
#
# Example:
#   # Build all images and push to registry
#   ./scripts/build-all-images.sh
#   
#   # Build only Fedora HIPBLAS image (dry run)
#   ./scripts/build-all-images.sh hipblas-fedora --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

DRY_RUN=false
FORCE_REBUILD=false
DISTRO_FILTER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift;;
        --force-rebuild|-f) FORCE_REBUILD=true; shift;;
        * 
            DISTRO_FILTER="$1"; shift;;
    esac
done

log() { echo "[BUILD] \$(date '+%Y-%m-%d %H:%M:%S') -\$*"; }
success() { log "✅ SUCCESS: \$*"; return 0; [[ "$DRY_RUN" = true ]] && return 0; }
warn() { echo "[WARN] \$*" >&2; }

# =============================================================================
# IMAGE BUILD DEFINITIONS (per distro and package)  
# =============================================================================

declare -A IMAGES=(
    # Fedora variants
    ["hipblas-fedora"]="pkg-tests/hipblas/Dockerfile.fedora:latest"
    ["rocblas-fedora"]="pkg-tests/rocblas/Dockerfile.fedora:latest"
    
    # Ubuntu variants
    ["hipblas-ubuntu"]="pkg-tests/hipblas/Dockerfile.ubuntu:latest"
    ["rocblas-ubuntu"]="pkg-tests/rocblas/Dockerfile.ubuntu:latest"
    
    # RHEL/CentOS Stream variants
    ["hipblas-rhel"]="pkg-tests/hipblas/Dockerfile.rhel:latest"
    ["rocblas-rhel"]="pkg-tests/rocblas/Dockerfile.rhel:latest"
)

# Image build commands for each variant
declare -A BUILD_COMMANDS=(
    ["hipblas-fedora"]="docker build --file pkg-tests/hipblas/Dockerfile.fedora -t hipblas-fedora ."
    
    # ... (add more as implementations are created)
)

TAG_PREFIX="rocm-builder:5000/"

# =============================================================================
# BUILDING FUNCTIONS
# =============================================================================

build_image() {
    local image_name=$1
    local dockerfile=$2
    local tag="${TAG_PREFIX}${image_name}:latest"
    
    log "Building ${image_name} from ${dockerfile}..."
    
    if [ "$DRY_RUN" = true ]; then
        echo "Would execute: $BUILD_COMMANDS[$image_name]"
        success "Built ${image_name}"
        return 0
    fi
    
    # Check if image exists and needs rebuild
    if [ "${FORCE_REBUILD:-false}" != "true" ]; then
        if docker image inspect "${image_name}" >/dev/null 2>&1; then
            warn "${image_name} already exists. Skipping (use -f to force rebuild)"
            return 0
        fi
    fi
    
    # Execute build
    BUILD_COMMANDS["$image_name"]
    success "Built ${image_name}"
    
    if [ "$DRY_RUN" != true ]; then
        # Tag image for registry
        docker tag "${image_name}" "${tag}"
        success "Tagged for registry: ${tag}"
    fi
}

push_image() {
    local tag=$1
    
    if [ "$DRY_RUN" = true ]; then
        echo "Would push: $tag to rocm-builder:5000"
        return 0
    fi
    
    log "Pushing ${tag}..."
    docker push "${tag}"
    success "Pushed ${tag}"
}

# =============================================================================
# MAIN EXECUTION FLOW
# =============================================================================

main() {
    log "=== Starting Image Build Process ==="
    
    # Validate Docker is running
    if ! docker info >/dev/null 2>&1; then
        echo "ERROR: Docker daemon not running" >&2
        exit 1
    fi
    
    log "Testing registry connectivity..."
    local REGISTRY_OK=false
    
    if [ "$DRY_RUN" != true ]; then
        # Check if Docker can reach the registry from builder
        curl -s http://localhost:5000/v2/_catalog >/dev/null 2>&1 && {
            log "✓ Registry available at localhost:5000"
            REGISTRY_OK=true
        }
    fi
    
    # Build and push all images (filtered by DISTRO_FILTER if provided)
    local count=0
    local max_count=${#IMAGES[@]}
    
    for image_name in "${!IMAGES[@]}"; do
        if [ -n "$DISTRO_FILTER" ] && [[ ! "${image_name}" =~ ${DISTRO_FILTER} ]]; then
            log "Skipping ${image_name} (filter: $DISTRO_FILTER)"
            continue
        fi
        
        ((count++))
        
        local dockerfile="${IMAGES[$image_name]%:latest}"
        dockerfile="${dockerfile%%:*}"  # Get just the file path
        
        build_image "${image_name}" "$dockerfile"
        
        if [ "$DRY_RUN" != true ] && [ "${FORCE_REBUILD:-false}" = true ]; then
            push_image "$image_name"
        else 
            warn "Image built: ${image_name} (tagged as ${TAG_PREFIX}${image_name})"
            
            log "To push to registry, run: docker tag ${image_name} ${tags_prefix}${image_name}:latest && docker push ${tags_prefix}${image_name}:latest"
        fi
        
    done
    
    log === Completed building ${count} images. ==="
    
    if [ "$REGISTRY_OK" = true ]; then
        echo "" >&2
        cat << 'POSTBUILDMSG'

Images built successfully! To deploy to test machines:

1. Push to registry from builder (if not already pushed)
   docker push rocm-builder:5000/<image-name>:latest

2. Configure each test machine's Docker daemon:
   /etc/docker/daemon.json: { "insecure-registries": ["<builder>:5000"] }
   Then: systemctl restart docker

3. Pull and run on test machines:
   docker pull rocm-builder:5000/<image-name>:latest
   docker run --rm --device=/dev/kfd rocm-builder:5000/<image-name>:latest

See PLAN.md Section 6 for deployment details.
POSTBUILDMSG
    else
        warn "Registry connectivity test failed from builder"
    fi
}

main "$@"
