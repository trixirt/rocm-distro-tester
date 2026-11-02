#!/usr/bin/env bash
# =============================================================================
# /tutorials/verification/test_docker_volume.sh
# =============================================================================
# 
# PURPOSE & CONTEXT: (For your future self)
# When mounting a volume from the HOST filesystem into a Docker container, it is
# extremely common to run into "Permission Denied" errors where you can read 
# files but not write them. On Fedora/RHEL systems (which this environment uses),
# Linux SELinux prevents containers from writing to unapproved host folders.
#
# THE FIX:
# If the test below FAILS, add ":Z" to your docker -v flag like this:
# Example fix: docker run -v "./path:/var/lib/postgresql/data:Z"
# The ":Z" tells SELinux to allow *this specific* container to write.
# =============================================================================

set -euo pipefail # Strict mode: Fail fast, treat unset variables as errors

# ---------------------------------------------------------------
# STEP 1: PATH ISOLATION (Crucial for Robustness)
# ---------------------------------------------------------------
# We MUST resolve the absolute path to the script's directory so Docker 
# always sees the correct mount location, preventing "invalid reference" errors.
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "--------------------------------------------------------"
echo "  Docker Mount Writability Test"
echo "--------------------------------------------------------"
echo ""
echo "[Step 1] Creating a generic temporary test folder on HOST..."

# ---------------------------------------------------------------
# STEP 2: CREATE A GENERIC HOST DIRECTORY
# ---------------------------------------------------------------
# We use 'mktemp' so we don't leave behind messy folders in your codebase.
HOST_TEST_DIR=$(mktemp -d)

echo "[Result] -> $HOST_TEST_DIR"
echo ""
echo "[Step 2] Running a lightweight Docker container (Busybox)..."

# ---------------------------------------------------------------
# STEP 3: RUN DOCKER AND ATTEMPT THE WRITE
# ---------------------------------------------------------------
# Flags used:
# --rm : Clean up the container immediately when it finishes.
# -w /test : Set the working directory inside the container to '/test'.
# -v "$HOST_TEST_DIR":/test : Mount the HOST folder into the CONTAINER at '/test'.

docker run --rm \
    -w /test \
    -v "$HOST_TEST_DIR":/test \
    busybox sh -c "
        echo '  [Inside Docker] Attempting to write a file...'
        
        # Try to actually create a file in the mounted folder.
        # If this hangs or errors, Docker doesn't have permission to write.
        touch .writable_check

        if [ -f .writable_check ]; then
            exit 0    # Success! We can read and write.
        else
            exit 1    # Fail! We cannot write (or don't have permissions).
        fi
    "

# ---------------------------------------------------------------
# STEP 4: RECOVERY AND DIAGNOSIS
# ---------------------------------------------------------------
if [ $? -eq 0 ]; then
    echo ""
    echo "[RESULT] SUCCESS! Your Docker volume configuration is valid."
    echo "         You can safely ignore this test folder ($HOST_TEST_DIR)."
else
    echo ""
    echo "[RESULT] FAILURE! Docker was denied permission to write."
    echo ""
    echo "DIAGNOSIS (Read this part):"
    echo "---------------------------------------------"
    echo "1. SELinux (Common on Fedora/RHEL):"
    echo "   You likely need the SELinux 'Z' flag in your -v mount."
    echo "   Update your docker -v line to look like this:" 
    echo "      ... -v '\$HERE/data:/var/lib/postgresql/data:Z'"
    echo ""
    echo "2. Permissions Mismatch:"
    echo "   The folder on your host might not be writable by 'root' (UID 0), which"
    echo "   Docker usually uses inside a container. Try running on your host first:"
    echo "      chmod -R a+w $HOST_TEST_DIR" 
fi

echo ""
echo "Script Finished."
echo "--------------------------------------------------------"
