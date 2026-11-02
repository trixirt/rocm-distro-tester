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
# MASTER CLEANUP (Universal Sweep)
# ----------------------------
echo "[Step 1/3] Cleaning up environment and ensuring a fresh start..."

# We now perform a 'Master Sweep' to ensure that running this script leaves a 
# completely clean slate, regardless of whether Tutorials 2 or 3 were run prior.
docker rm -f db-tutor-db db-tutor-2 db-server rocm-poller >/dev/null 2>&1 || true
docker network rm rocm-net >/dev/null 2>&1 || true
docker rmi db-tutor db-tutor-2 >/dev/null 2>&1 || true

# ----------------------------
# STEP 1: THE BUILD (Baking the Cake)
# ----------------------------
echo "[Step 2/3] Building our tutorial image..."
if ! docker image inspect db-tutor >/dev/null 2>&1; then
    docker build -t db-tutor .
fi

# ----------------------------
# STEP 2: THE RUN (Eating the Cake)
# ----------------------------
echo "[Step 3/3] Starting your database office..."

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
