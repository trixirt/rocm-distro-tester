#!/bin/bash

# =============================================================================
# run.sh - Tutorial 2: The "One-Click" Script
# Purpose: Manage the lifecycle of our database, including mounting local files.
# =============================================================================

echo "========================================================================="
echo " ROCm Database Tutor (Tut 2): Bootstrapping & Import"
echo "-------------------------------------------------------------------------"

CONTAINER_NAME="db-tutor-2" 
IMAGE_TAG="db-tutor-2"

# This pattern determines the script's own directory. It is essential for
# robust path resolution so volumes are mounted relative to the script's
# location and not the current working directory where it is invoked from.
HERE="$(cd "$(dirname "$0")" && pwd)"

# =============================================================================
# CLEANUP PHASE (Targeted Cleanup)
# =============================================================================
echo "[Step 1/3] Cleaning up environment for this tutorial only..."

# We intentionally only clean up the resources *this specific* script owns.
# This prevents us from accidentally killing simulations running in Tutorial 1 or 3.
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[Cleanup] Removing previous ${CONTAINER_NAME} session..."
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 
fi

# Optional: Clean up the specific build image for this tutorial to save space.
if docker images --format '{{.Repository}}' | grep -q "^${IMAGE_TAG}$"; then
    docker rmi "${IMAGE_TAG}" >/dev/null 2>&1 || true
fi

# =============================================================================
# STEP 1: BUILD PHASE
# =============================================================================
echo "[Step 1/3] Building our tutorial image (the 'recipe')..."
# Note we use '.' for the build context because the Dockerfile is in the script's directory.
docker build -t "${IMAGE_TAG}" .
if [ $? != 0 ]; then
    exit 1
fi


# =============================================================================
# STEP 2: RUN PHASE (Starting the server)
# =============================================================================
echo "[Step 2/3] Starting your database office (with mounted tools)..."

# We use 'docker run' to spin up a live process. Here is the breakdown of the flags:

# '-d' (Detached): Runs the container in the background so you can continue using this terminal.
# '--name "${CONTAINER_NAME}"': Assigns a human-readable name to the container for easy management.
# 
# '-p 5432:5432' (Port Mapping): This creates a bridge between your computer and the container.
# Syntax is [Host Port]:[Container Port]. We chose '5432' because it is the industry-standard 
# default port assigned to the PostgreSQL database system. By mapping it, any program on your host 
# can access the database simply by connecting to localhost:5432.

# '-v "${HERE}/db-server":/mnt/db-server:Z' (Volume Mounting): Connects the local folder containing 
# our SQL schema and seed data into the container.
# ':Z' is added to handle SELinux contexts on Fedora/RHEL where mounted files are often read-only by default.

docker run -d --name ${CONTAINER_NAME} \
       -p 5432:5432                    \
       -v "${HERE}/db-server":/mnt/db-server:Z \ 
       ${IMAGE_TAG} postgres 

# If there is a problem.. 
# docker run --name ${CONTAINER_NAME} -it ${IMAGE_TAG}

echo " -> Waiting for Postgres to initialize files..."
# Database engines like PostgreSQL have a startup phase where they load internal logs. 
# Without this pause, the container might be running but won't be ready to accept queries yet.
sleep 8

# =============================================================================
# STEP 3: CONNECT PHASE (Opening the Door)
# =============================================================================
echo " -> Ready! Use psql commands like:"
echo "   psql -U mydbuser rocm_production_sim -f /mnt/schema.sql"

docker exec -it "${CONTAINER_NAME}" psql -U mydbuser rocm_production_sim
