#!/bin/bash

# =============================================================================
# run.sh - The "One-Click" Tutor Script
# Purpose: To manage the lifecycle of our database "office".
# =============================================================================

echo "========================================================================="
echo " ROCm Database Tutor: Preparing your environment..."
echo "-------------------------------------------------------------------------"

CONTAINER_NAME="db-tutor-db"

# ----------------------------
# PRE-CHECK: Remove any leftover containers
# ----------------------------
# We do this because in a tutorial, we want a fresh start every single time.
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[Cleanup] Removing previous database session..."
    docker rm -f ${CONTAINER_NAME} >/dev/null 2>&1
fi

# ----------------------------
# STEP 1: THE BUILD (Baking the Cake)
# ----------------------------
echo "[Step 1/2] Building our tutorial image..."
if ! docker image inspect db-tutor >/dev/null 2>&1; then
    docker build -t db-tutor .
fi

# ----------------------------
# STEP 2: THE RUN (Eating the Cake)
# ----------------------------
echo "[Step 2/2] Starting your database office..."

# 'docker run' starts a new container. 
# '-d' = Detached (runs in background). 
# '-p 5432:5432' = Exposes the port (good to have if we need to connect from outside).
# db-tutor = Our recipe name.
# postgres = The command we want inside the box. This *overrides* the CMD ["bash"] in your Dockerfile so Postgres actually starts!

docker run -d --name ${CONTAINER_NAME} -p 5432:5432 db-tutor postgres 

echo " -> Waiting 10 seconds for Postgres to initialize its internal files..."
sleep 10

# ----------------------------
# STEP 3: CONNECTING (Opening the Door)
# ----------------------------
echo " -> Connecting you to the terminal..."
docker exec -it ${CONTAINER_NAME} psql -U mydbuser rocm_playground
