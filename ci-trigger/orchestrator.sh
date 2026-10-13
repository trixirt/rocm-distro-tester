#!/bin/bash
# =============================================================================
# ROCm-Tester Orchestrator
# 
# Manages distributed execution of test matrices across GPU nodes.
# Polls Fedora Koji and Ubuntu Launchpad for package updates, builds distro-
# specific containers, runs smoke tests on target hardware, aggregates results.
#
# Usage:
#   ./orchestrator.sh --test-pack=hipblas [--distro=all|ubuntu|fedora] 
#                     [--gpu=all|mi250|mi300|vega] [--mode=live|dry-run]
#
# Environment Variables:
#   CONTROLLER_HOST     - Hostname/IP of controller machine (default: localhost)
#   TEST_REGISTRY       - Path to test container registry image cache
#   RESULTS_DIR         - Output directory for results JSONL (default: ./ci-trigger/results)
# =============================================================================

set -euo pipefail

# Default configuration - can be overridden via environment variables or flags
CONTROLLER_HOST="${CONTROLLER_HOST:-localhost}"
TEST_REGISTRY="${TEST_REGISTRY:-./ci-trigger/test-registry}"
RESULTS_DIR="${RESULTS_DIR:-./ci-trigger/results}"
PACKAGE_NAME="${1:-hipblas}"
DISTRO_LIST="all"
GPU_LIST="all"
MODE="live"  # live | dry-run

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --test-pack) PACKAGE_NAME="$2"; shift 2 ;;
        --distro) DISTRO_LIST="$2"; shift 2 ;;
        --gpu) GPU_LIST="$2"; shift 2 ;;
        --mode) MODE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Distro mapping for orchestration logic
declare -A DISTRO_MAP=(
    [all]="ubuntu fedora opensuse"
    [ubuntu]="ubuntu"
    [fedora]="fedora"
    [opensuse]="opensuse"
)

# GPU device mapping (actual device paths on test nodes)
declare -A GPU_MAP=(
    [all]="mi250 mi300 vega"
    [mi250]="/dev/kfd_mi250"
    [mi300]="/dev/kfd_mi300"
    [vega]="/dev/kfd_vega"
)

# =============================================================================
# FUNCTIONS
# =============================================================================

log() {
    local msg="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] ${msg}"
}

log_test_result() {
    local test_name="$1" distro="$2" gpu="$3" result="$4" duration="$5"
    local json_output="{\"test_name\":\"$test_name\",\"distro\":\"$distro\",\"gpu\":\"$gpu\",
                     \"result\":\"$result\",\"duration_seconds\":$duration,\"timestamp\":\"$(date -Iseconds)\"}"
    echo "$json_output" >> "${RESULTS_DIR}/all-results.jsonl"
}

build_test_image() {
    local distro="$1" package="$2" image_tag="rocmtester/${package}-${distro}:latest"
    
    log "Building test container for ${package} on ${distro}"
    
    case "$distro" in
        ubuntu)
            docker build -t "$image_tag" --file ./pkg-tests/${package}/Dockerfile.ubuntu .\
                --build-arg PACKAGENAME="${package}" 2>&1 | tee logs/build_${package}_${distro}.log
            ;;
        fedora)
            docker build -t "$image_tag" --file ./pkg-tests/${package}/Dockerfile.fedora .\
                --build-arg PACKAGENAME="${package}" 2>&1 | tee logs/build_${package}_${distro}.log
            ;;
        opensuse)
            log "OpenSUSSE support pending - using Fedora base"
            docker build -t "$image_tag" --file ./pkg-tests/${package}/Dockerfile.fedora .\
                --build-arg PACKAGENAME="${package}" 2>&1 | tee logs/build_${package}_${distro}.log
            ;;
        *)
            log "ERROR: Unsupported distro: ${distro}"
            return 1
            ;;
    esac
    
    echo "$image_tag"
}

run_test_on_gpu() {
    local image="$1" gpu_id="$2" test_name="$3" start_time="$4"
    
    log "Running tests on GPU node: ${gpu_id}"
    
    # Determine GPU device flag based on target machine type
    case "${gpu_id}" in
        mi250|mi300)     # AMD ROCm devices via /dev/kfd
            gpu_flags="--device=/dev/kfd --group-add=107"
            ;;
        vega)            # Legacy Vega - similar but different config
            gpu_flags="--device=/dev/kfd --group-add=107"
            ;;
        *)               # NVIDIA or fallback
            gpu_flags="--gpus=all"
            ;;
    esac
    
    local test_start=$(date +%s)
    
    if [ "$MODE" = "dry-run" ]; then
        log "DRY RUN: Would run: docker run ${gpu_flags} --rm ${image}"
        return 0
    fi
    
    timeout 1800 docker run --rm \
        $gpu_flags \
        -v "${RESULTS_DIR}:/output" \
        "$image" > logs/test_${test_name}_${gpu_id}.log 2>&1
    
    local exit_code=$?
    
    if [ $exit_code -eq 137 ]; then
        log "Test timed out after 1800 seconds"
        return 1
    fi
    
    local test_end=$(date +%s)
    local duration=$((test_end - start_time))
    
    if [ $exit_code -ne 0 ]; then
        log_test_result "$test_name" "$(uname -n)" "$gpu_id" "FAILED" "$duration"
        log "TEST FAILED (exit code: ${exit_code}): ${test_name} on ${gpu_id}"
        return 1
    fi
    
    log_test_result "$test_name" "$(uname -n)" "$gpu_id" "PASSED" "$duration"
    log "TEST PASSED: ${test_name} on ${gpu_id} (${duration}s)"
    return 0
}

generate_orchestrate_matrix() {
    local test_package="$1"
    
    log "Generating execution matrix for package: $test_package"
    
    mkdir -p "$RESULTS_DIR/logs"
    
    # Expand distro/GPU lists based on user input ("all" vs specific)
    local distros=($(echo "${DISTRO_MAP[$DISTRO_LIST]:-${DISTRO_LIST}}" | tr ' ' '\n' | sort -u))
    local gpus=($(echo "${GPU_MAP[$GPU_LIST]:-${GPU_LIST}}" | tr ' ' '\n' | sort -u))
    
    log "Test Matrix: ${distros[@]} × ${gpus[@]}"
    
    # Start orchestrating tests
    for distro in "${distros[@]}"; do
        for gpu in "${gpus[@]}"; do
            local image_tag
            image_tag=$(build_test_image "$distro" "$test_package") || return 1
            
            local start_time=$(date +%s)
            
            run_test_on_gpu "$image_tag" "$gpu" "$test_package" $start_time
        done
    done
    
    log "Orchestration complete. Results saved to ${RESULTS_DIR}/all-results.jsonl"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

log "=== ROCm-Tester Orchestrator v0.1 ==="
log "Executing tests for package: $PACKAGE_NAME (mode: $MODE)"
log "Testing on distros: ${DISTRO_LIST}, GPUs: ${GPU_LIST}"

# Execute matrix orchestration based on provided parameters
generate_orchestrate_matrix "$PACKAGE_NAME"
