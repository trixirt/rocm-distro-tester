#!/usr/bin/env bash
# =============================================================================
# /tutorials/tests/verify_docker_volume.sh
# =============================================================================
# 
# PURPOSE & CONTEXT: (For your future self)
# When mounting a volume from the HOST filesystem into a Docker container, it is
# extremely common to run into "Permission Denied" errors where you can read 
# data but cannot write files. On Fedora/RHEL systems (which this project uses),
# Linux SELinux prevents containers from writing to unapproved host folders by default.
#
# THE FIX:
# If the test below FAILS, add ":Z" to your docker -v command line like this:
# Example fix: docker run --mount "./path:/var/lib/postgresql/data:Z"
# The ":Z" tells SELinux to allow *this specific* container to write.
# =============================================================================

set -euo pipefail # Fail fast, treat unset variables as errors

# ---------------------------------------------------------------
# STEP 1: PATH ISOLATION (Crucial for Robustness)
# ---------------------------------------------------------------
# We MUST resolve the absolute path to the script's directory so Docker 
# always sees the correct mount location, preventing "invalid reference" errors.
# We NEVER use $() or ${PWD} for -v arguments as they can break on split paths.
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "--------------------------------------------------------"
echo "  Docker Mount Writability Test"
echo "--------------------------------------------------------"
echo ""
echo "[Step 1] Creating a generic temporary test folder on HOST..."

# ---------------------------------------------------------------
# STEP 2: CREATE A GENERIC HOST DIRECTORY
# ---------------------------------------------------------------
# We use 'mktemp' to safely create a unique temporary directory in /tmp 
# on the host. This acts as our "generic volume" root so we don't clutter 
# up your project folders while testing Docker flags.
HOST_TEST_DIR=$(mktemp -d)

echo "[Result] -> $HOST_TEST_DIR" # The folder we are about to mount
echo ""
echo "[Step 2] Running a lightweight Docker container (Busybox)..."

# ---------------------------------------------------------------
# STEP 3: RUN DOCKER AND ATTEMPT THE WRITE
# ---------------------------------------------------------------
# Flags used:
# --rm : Removes the container immediately when it finishes (keeps system clean).
# -w /test : Sets the active working directory inside the container to '/test'.
# -v "$HERE/../tutorials/tests/.":/test : 
#           Mounts the HOST folder into the CONTAINER at '/test'.
# busybox sh -c "..." : Runs a tiny Linux shell that attempts to write a file.

docker run --rm \
    -w /test \
    -v "$HOST_TEST_DIR":/test \
    busybox sh -c "
        echo '  [Inside Docker] Attempting to create a test file...'
        
        # Try to actually create a file in the mounted folder.
        # If this hangs or errors, Docker has denied write permissions.
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
    echo "[RESULT] FAILURE! Docker was denied permission to write your host file." >&2 
    echo ""
    echo "DIAGNOSIS (Read this part):"
    echo "---------------------------------------------"
    echo "1. SELinux (Common on Fedora/RHEL/Enterprise Linux):"
    echo "   You likely see an 'Operation not permitted' error in Docker logs."
    echo "   This means your system blocks writes to host directories by default."
    echo ""
    echo "   THE FIX: Add ':Z' to YOUR docker -v command line like this:"
    echo "      Example fix: docker run --mount '\$HERE/data:/var/lib/postgresql/data:Z'"
    echo "   This tells SELinux to allow *this specific* container to write."
    echo ""
    echo "2. Permissions Mismatch (Root vs User):"
    echo "   Docker writes files as 'root' inside the container. If your host folder is owned"
    echo "   differently, you may get a standard Linux permission error." 
    echo "   Try running on your host first: chmod -R a+w $HOST_TEST_DIR"
fi

# Cleanup of test dir (optional but good practice)
rm -rf "$HOST_TEST_DIR"
echo ""
echo "Temporary test folder removed automatically."
echo "--------------------------------------------------------"
