#!/bin/bash
# verify_docker_mount_test.sh
set -euo pipefail

# 1. Setup isolated variables
TEST_DIR=$(mktemp -d /tmp/docker-mount-test-XXXXXX) && chmod 777 "${TEST_DIR}" || exit 1
CONTAINER_NAME="mt_tester_$$"
IMAGE="alpine" 
MOUNT_PATH="/mnt/testdata"

echo "------------------------------------------------------"
echo "  Docker Mount Verification (Mount/Read/Write)"
echo "------------------------------------------------------"
echo "[Step 1] Creating temporary host directory: ${TEST_DIR}"

# 2. Define cleanup to run on exit regardless of success/failure
cleanup() {
    echo "[Cleanup]"
    docker stop "${CONTAINER_NAME}" &>/dev/null || true 
    docker rm -f "${CONTAINER_NAME}" &>/dev/null || true 
    rm -rf "${TEST_DIR}"
}
trap cleanup EXIT

# 3. Launch the container with :z flag to allow SELinux context relabeling
echo "[Step 2] Spinning up Docker container '${CONTAINER_NAME}'..."
docker run -d \
    --name "${CONTAINER_NAME}" \
    -v "${TEST_DIR}:${MOUNT_PATH}:z" \
    "${IMAGE}" sleep 3600 > /dev/null

sleep 1 

# 4. Verify Mount exists (check if we can enter the mount point)
echo "[Step 3] Verifying mount is successfully mounted..."
if docker exec "${CONTAINER_NAME}" test -d "${MOUNT_PATH}" &>/dev/null; then
    echo "   PASSED: Directory exists inside the container."
    
    # Detailed permissions check (Numeric format to see exact UID/GID mapping)
    echo ""
    echo "--- Mount Point Permission Diagnostics ---"
    HOST_PERMS=$(ls -ldn "${TEST_DIR}")
    CONTAINER_PERMS=$(docker exec "${CONTAINER_NAME}" ls -ldn "${MOUNT_PATH}")
    
    printf "     Host side ('%s'):      %s\n" "$(basename "$TEST_DIR")" "$HOST_PERMS"
    printf "     Container side ('%s'): %s\n" "$(basename "$MOUNT_PATH")" "$CONTAINER_PERMS"
else
    echo "FAILED: Mount failed to appear." >&2
    exit 1
fi

# 5. Verify Read Capability (Host write -> Container read)
echo "======================================================"
echo "[Step 4] Verifying mount is READABLE from inside the container..."
test_read_file="${TEST_DIR}/host-read-test.txt"
echo "This file was written ON THE HOST." > "${test_read_file}"

# Check permissions for both host and container sides of the read test
HOST_READ_PERMS=$(ls -ldn "${test_read_file}")
CONTAINER_READ_PERMS=$(docker exec "${CONTAINER_NAME}" ls -ldn "${MOUNT_PATH}/host-read-test.txt")
printf "     Host read ('%s'):      %s\n" "$(basename "$test_read_file")" "$HOST_READ_PERMS"
printf "     Container read:        %s\n" "$CONTAINER_READ_PERMS"

read_output=$(docker exec "${CONTAINER_NAME}" cat "${MOUNT_PATH}/host-read-test.txt")
if [[ $read_output == *"This file was"* ]]; then
    echo "   PASSED: Host-created file is readable inside the container."
else
    echo "FAILED: File created on host is NOT accessible inside!" >&2
    exit 1
fi

# 6. Verify Writable (Container write -> Host read)
echo "======================================================"
echo "[Step 5] Verifying mount is writable via 'docker exec'..."
CONTAINER_TEST_FILE="${MOUNT_PATH}/container-write-test.txt"
HOST_TEST_FILE="${TEST_DIR}/container-write-test.txt"

if docker exec "${CONTAINER_NAME}" touch "${CONTAINER_TEST_FILE}"; then
    
    # Check permissions for both host and container sides of the write test file
    CONTAINER_WRITE_RESULT=$(docker exec "${CONTAINER_NAME}" ls -ldn "${CONTAINER_TEST_FILE}")
    
    if [ -f "${HOST_TEST_FILE}" ]; then
        HOST_WRITE_RESULT=$(ls -ldn "${HOST_TEST_FILE}")
        
        printf "     Container write:       %s\n" "$CONTAINER_WRITE_RESULT"
        printf "     Host write ('%s'):      %s\n" "$(basename "${HOST_TEST_FILE}")" "$HOST_WRITE_RESULT"
        echo "   PASSED: Container successfully wrote a file to the volume." 
    else
        echo "FAILED: File exists in container but NOT on host!" >&2
        exit 1
    fi
else
    echo ""
    echo "FAILED: Container cannot write to this mount!" >&2
    exit 1
fi

echo ""
echo "[SUCCESS] All checks passed! (Mounted, Readable from host, Writable)"
exit 0