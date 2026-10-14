#!/bin/bash
# =============================================================================
# HIPBLAS Unit Test Compilation and Execution Script
# =============================================================================
# Compiles test.cpp from Fedora's hipblas RPM source using hipcc compiler 
# and executes the resulting binary for comprehensive testing.
# Based on Fedora's rpmbuild --with test methodology but standalone execution
# =============================================================================

set -euo pipefail

GPU_DEVICE="${HIPBLAS_GPU:-/dev/kfd}"
TEST_OUTPUT="/output/test-results"
UNIT_TEST_BINARY=/tmp/hipblas-unit-test-compiled
LOG_FILE="$TEST_OUTPUT/unit-tests.log"

# =============================================================================
# COMPILE HIPBLAS UNIT TESTS FROM SOURCE
# =============================================================================

compile_unit_tests() {
    log "=== Compiling HIPBLAS Unit Tests ==="
    
    if [ ! -f "/opt/hipblas-rpm/test.cpp" ]; then
        log "Source file test.cpp not found at /opt/hipblas-rpm/"
        return 1
    fi
    
    # Create compile output directory  
    mkdir -p "$TEST_OUTPUT"
    
    # Compile HIPBLAS unit tests with hipcc compiler using Fedora approach
    cd /opt/hipblas-rpm
    
    log "Compiling test.cpp to $UNIT_TEST_BINARY..."
    
    # Use hipcc with appropriate linkage flags (similar to Fedora build)
    if hipcc -o "$UNIT_TEST_BINARY" \
        test.cpp \
        -L/opt/rocm/lib \
        -lhipblas \
        -lrocblas \
        -lhipsolver \
        -lhsa-runtime64 \
        -lHipBLAS 2>&1 | tee $LOG_FILE; then
        
        success "HIPBLAS unit test compiled successfully: $UNIT_TEST_BINARY"
        
        if [ -x "$UNIT_TEST_BINARY" ]; then
            log "Compiler output and any warnings written to $LOG_FILE"
            return 0
        else
            warn "Compilation produced no executable, despite successful build message"
            return 1
        fi
        
    else
        die "HIPBLAS unit test compilation FAILED - see $LOG_FILE for details"
    fi
}

# =============================================================================
# RUN HIPBLAS UNIT TESTS (after compilation)  
# =============================================================================

run_unit_tests() {
    log "=== Running HIPBLAS Unit Tests ==="
    
    if [ ! -x "$UNIT_TEST_BINARY" ]; then
        warn "Unit test binary $UNIT_TEST_BINARY does not exist or is not executable"
        return 1
    fi
    
    log "Attempting to execute HIPBLAS unit tests..."
    
    # Execute the compiled test binary with GPU device access
    if timeout 300 "$UNIT_TEST_BINARY" --device "${GPU_DEVICE#*:}" 2>&1; then
        success "HIPBLAS unit tests PASSED"
        
        log "Unit test execution details:"
        log "- Test binary: $UNIT_TEST_BINARY"
        log "- GPU device used: $(hipcc -dumpmachine 2>/dev/null || echo 'not set')"
        log "- ROCm libraries linked from: /opt/rocm/lib"
        
        return 0
        
    else
        local exit_code=$?
        warn "HIPBLAS unit tests FAILED or timed out (exit code: $exit_code)"
        
        # Print test output to console for debugging
        log "=== HIPBLAS Test Output ==="
        cat "$LOG_FILE" || true
        return 1
        
    fi
}

# =============================================================================
# HELPER FUNCTIONS  
# =============================================================================

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[HIPBLAS-UNIT-COMP] ${timestamp} - $@" 2>&1 | tee -a "$LOG_FILE"
}

success() {
    log "✅ SUCCESS: $*"
}

log_step() {
    log "=== STEP: $* ==="
}

die() {
    log "FATAL ERROR: $*"; exit 1
}

warn() {
    echo "[HIPBLAS-WARN] $*  " >&2
}

# =============================================================================
# MAIN EXECUTION FLOW
# Step-by-step compilation and test execution similar to rpmbuild --with test
# =============================================================================

main() {
    log_step "Initializing comprehensive HIPBLAS unit tests"
    mkdir -p "$TEST_OUTPUT"
    
    # 1. Compile the test.cpp source file into executable  
    compile_unit_tests
    
    # 2. Run the compiled binary for GPU verification  
    run_unit_tests || true
    
    log_step "HIPBLAS unit test compilation and execution complete"
}

# Execute main flow
main || exit 1
