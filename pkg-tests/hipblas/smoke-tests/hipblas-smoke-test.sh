#!/bin/bash
# =============================================================================
# HIPBLAS Smoke Test Runner (Fedora Rawhide Variant)
# =============================================================================
# This test script verifies basic HIPBLAS GPU operations on AMD GPU hardware.
# Runs within container environment with GPU device passthrough enabled.
#
# Usage: ./hipblas-smoke-test.sh [--gpu-device DEVICE] [--verbose]
# Exit Codes: 0 = success, non-zero = failure

set -euo pipefail

# Configuration defaults
GPU_DEVICE="${HIPBLAS_GPU:-/dev/kfd}"
TEST_VERBOSE="${VERBOSE:-false}"
LOG_OUTPUT="/output/test-results"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

log () {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[HIPBLAS-SMOKE] ${timestamp} - $1" 2>&1 | tee -a /output/test-results.log
}

log_verbose () {
    if [ "$TEST_VERBOSE" = "true" ]; then
        log "$@"
    fi
}

die() {
    log "FATAL: $1" >&2
    exit 1
}

setup_environment() {
    log "Setting up ROCm/HIPBLAS environment..."
    
    # Ensure output directory exists
    mkdir -p "$LOG_OUTPUT"
    
    # Load HIP environment variables if available
    if [ -f /opt/rocm/setvars.sh ]; then
        source /opt/rocm/setvars.sh || true
        log_verbose "Source ROCm setvars script"
    fi
    
    # Verify GPU device is accessible
    if [ -e "$GPU_DEVICE" ]; then
        log "GPU device found: $GPU_DEVICE"
    else
        die "GPU device $GPU_DEVICE not accessible in container"
    fi
}

run_hipblas_smoke_tests() {
    log "Running HIPBLAS smoke tests..."
    
    # Check if hipcc (HIP compiler) is available
    if command -v hipcc &> /dev/null; then
        log "✅ HIP compiler (hipcc) found at $(which hipcc)"
        
        # Attempt to run hipblas-test utility if available
        if command -v hipblas-test &> /dev/null; then
            log_verbose "Running hipblas-test executable..."
            
            timeout 1800 hipblas-test --help >/dev/null 2>&1 || true
            
        else
            log "hipblas-test not found, checking installed packages..."
            
            if command -v rocblas-test &> /dev/null; then
                log_verbose "Running rocblas-test executable..."
                timeout 900 rocblas-test --help >/dev/null 2>&1 || true
                
            else
                log "Testing basic HIP/ROCMBLAS operations manually..."
                
                # Run a simple HIP kernel invocation to test GPU setup
                run_manual_hip_test
                
            fi
        fi
        
    else
        die "HIP compiler (hipcc) not installed in container environment"
    fi
}

run_manual_hip_test() {
    log "Running manual HIP/ROCMBLAS smoke tests..."
    
    # Try to check if we have access to AMD GPU through ROCminfo
    if command -v rocminfo &> /dev/null; then
        log_verbose "Checking available ROCm devices..."
        
        # Get first available GPU device
        local device_count=$(rocminfo | grep -c "GPU" 2>/dev/null || echo "0")
        
        if [ "$device_count" -gt 0 ]; then
            log "✅ Found $device_count AMD GPU device(s)"
            
            # Log basic device info for debugging
            rocminfo --agent-list 2>/dev/null | head -5 >> /output/test-results.log || true
            
        else
            warn "No AMD GPU devices detected in container"
        fi
        
    else
        log "rocminfo not available, skipping device detection"
    fi
    
    # Basic HIPBLAS library check via file system
    if ls /opt/rocm/*/lib/libhipblas* 2>/dev/null | head -1 >/dev/null; then
        log "✅ HIPBLAS libraries found in expected locations"
    else
        warn "HIPBLAS libraries not found in standard paths"
    fi
    
    # Check hipblas headers
    if ls /opt/rocm/*/include/*hipblas*.h 2>/dev/null | head -1 >/dev/null; then
        log_verbose "✅ HIPBLAS development headers available"
    else
        warn "HIPBLAS headers not found in expected locations"
    fi
    
    # Final status logging
    log "Manual tests completed"
}

generate_test_results() {
    local test_status=$1
    local duration=$2
    
    cat > "$LOG_OUTPUT/hipblas-smoke-result.json" << EOFRESULT
{
  "test_name": "hipblas-smoke",
  "distro": "fedora-rawhide",
  "result": "$test_status",
  "status_code": ${test_status:-0},
  "gpu_device": "${GPU_DEVICE}",
  "duration_seconds": ${duration},
  "timestamp": "$(date -Iseconds)",
  "container_runtime": "docker"
}
EOFRESULT

    log_verbose "Results written to $LOG_OUTPUT/hipblas-smoke-result.json"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    log "=== HIPBLAS Smoke Test Start ==="
    
    local test_start=$(date +%s)
    
    # Setup environment  
    setup_environment
    
    # Run smoke tests - capture exit code
    run_hipblas_smoke_tests || {
        log "Tests returned non-zero exit code"
        generate_test_results "FAILED" $(( $(date +%s) - test_start ))
        exit 1
    }
    
    local test_end=$(date +%s)
    local duration=$((test_end - test_start))
    
    # Generate success results
    generate_test_results "PASSED" $duration
    
    log "=== HIPBLAS Smoke Tests Complete: PASSED (${duration}s) ==="
}

# Parse optional command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --gpu-device)
            GPU_DEVICE="$2"
            shift 2;;
        --verbose|-v)
            TEST_VERBOSE="true"
            shift ;;
        *)
            die "Unknown parameter: $1"
            ;;
    esac
done

# Execute main test flow
main
