#!/bin/bash
# =============================================================================
# verify_single_image.sh - Test a single registered image on the local GPU node
# =============================================================================
# Purpose: 
#   Pulls and executes a specific test container from the central test registry 
#   to confirm hardware readiness (GPU passthrough) and runtime behavior.
#
# Usage:
#   ./scripts/verify_single_image.sh hipblas-fedora-smoke:latest          # Defaults to :latest
#   ./scripts/verify_single_image.sh rocm-builder:5000/my-image:v1.2     # Full reference
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

REGISTRY_ALIAS="${REGISTRY_ALIAS:-rocm-builder}"
REGISTRY_PORT=5000
DRY_RUN=false

IMAGE_REF=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        *) 
            # If it's just a name, add the registry prefix. 
            # If it contains :5000 or rocm-builder, treat it as a full reference.
            if [[ "$1" == *"$REGISTRY_ALIAS*:$REGISTRY_PORT"* ]] || [[ -z "$IMAGE_REF" && ! "$1" == "${REGISTRY_ALIAS}:*" ]]; then
                IMAGE_REF="${REGISTRY_ALIAS}:${REGISTRY_PORT}/${1}"
            else
                IMAGE_REF="$1"
            fi
            shift 
            ;;
    esac
done

if [ -z "$IMAGE_REF" ]; then
    echo "❌ Please provide an image tag (e.g., 'hipblas-fedora-smoke:latest')." >&2
    exit 1
fi

echo "=========================================="
echo "--- Single Image Registry Test ---"
echo "Target Image: ${IMAGE_REF}"
# Fixed line 50 issue: removed backticks which were accidentally triggering command execution.
echo "Registry Alias : ${REGISTRY_ALIAS}:${REGISTRY_PORT}"
echo "GPU Passthrough: /dev/kfd, /dev/dri"
echo "==========================================\n"

# =========================================================================
# Step 0: Validate local GPU availability (must be a tester/GPU node)
# =========================================================================
echo "[Step 0/3] Checking local GPU device availability..."

# Check KFD (usually a character device)
if [ ! -c /dev/kfd ]; then
    echo "❌ FAILURE: Missing ROCm KFD device (/dev/kfd is not a character file)." >&2
    exit 1
fi

# Check DRI directory (DRI support is typically present if the directory itself exists)
if [ ! -d /dev/dri ]; then
    echo "❌ FAILURE: Missing DRI support (/dev/dri directory not found)." >&2
    exit 1
fi

# =========================================================================
# Step 1: Pull from the Test Registry (with real-time output logging)
# =========================================================================
echo -e "\n[Step 1/3] Pulling image '${IMAGE_REF}'..."
if [ "$DRY_RUN" = true ]; then
    echo "ℹ️  DRY RUN: Would pull ${IMAGE_REF}"
else
    # Create a temp file to capture the raw pull log for debugging if it fails
    PULL_LOG=$(mktemp)

    if docker pull "${IMAGE_REF}" 2>&1 | tee "${PULL_LOG}"; then
        echo "✅ Image pulled successfully:"
        tail -n 3 "${PULL_LOG}"
        rm -f "${PULL_LOG}"
    else
        echo "❌ FAILURE: Could not pull '${IMAGE_REF}' from registry." >&2
        # The log was already printed in real-time by tee, but we can cat it for inspection:
        echo "--- Pull Log Snapshot ---" >&2
        cat "${PULL_LOG}" >&2
        echo "--- End Pull Log ---" >&2
        rm -f "${PULL_LOG}"
        exit 1
    fi
fi

# =========================================================================
# Step 2: Execute on Local GPU Hardware (mimics run-nossh constraints)
# =========================================================================
echo -e "\n[Step 2/3] Executing container..."
if [ "$DRY_RUN" = true ]; then
    echo "ℹ️  DRY RUN: Would execute command:"
    docker run \
        --device /dev/kfd \
        --device /dev/dri \
        -e HIP_VISIBLE_DEVICES=0 \
        -it --rm \
        --cpus=8 \
        "${IMAGE_REF}" || true
else
    # Run with standard GPU environment variables required for ROCm containers
    RUN_OUTPUT=$(docker run \
        --device /dev/kfd \
        --device /dev/dri \
        -e HIP_VISIBLE_DEVICES=0 \
        -it --rm \
        --cpus=8 \
        "${IMAGE_REF}" 2>&1)

    if [ $? -ne 0 ]; then
        echo "❌ FAILURE: Container process exited with an error." >&2
        echo "--- Docker Error Log ---"
        echo "$RUN_OUTPUT" >&2
        echo "--- End Error Log ---" >&2
        exit 1
    else
        # If successful, we might still want to show what the container printed (e.g. rocminfo output)
        echo "${RUN_OUTPUT}" 
    fi
fi

# =========================================================================
# Step 3: Verification Complete
# =========================================================================
echo -e "\n=========================================="
echo "--- Image Test Complete ---"
echo "If no errors were shown above, the image is valid."
echo "==========================================\n"
