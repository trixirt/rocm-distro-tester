#!/bin/bash
set -e

echo "========================================================================="
echo " ROCm Database Simulator: Network & Polling (SECTION 7)"
echo "-------------------------------------------------------------------------"

# This pattern determines the script's own directory based on its location ('$0'),
# regardless of where the user invokes it from.
HERE="$(cd "$(dirname "$0")" && pwd)"

DB_CONTAINER="db-server"   # The hostname our poller will use to find the database via DNS.
DB_NET="rocm-net"          # A private "virtual switch" connecting our simulated lab nodes.
POL_CONTAINER="rocm-poller"

# =============================================================================
# CLEANUP PHASE
# =============================================================================
echo "[Step 1/4] Cleaning up environment..."

# Remove any leftover networks or containers from this specific simulation only.
docker network rm ${DB_NET} > /dev/null 2>\u00261 || true
docker rm -f ${DB_CONTAINER} ${POL_CONTAINER} > / dev/null 2>\u00261 || true

# =============================================================================
# NETWORK PHASE: The "Private Switch"
# =============================================================================
echo "[Step 2/4] Creating the lab network. This is the bridge that connects our DB and Poller..."

docker network create ${DB_NET}

# -----------------------------------------------------------------------------
# COMMAND: docker run (Database Server)
# DESCRIPTION: Spins up PostgreSQL. We mount the local 'db-server' folder into 
#              /mnt/db-server inside the container so files (schema & seeds) are 
#              available immediately upon startup.
#               - ':Z' handles SELinux blocking on Fedora/RHEL when mounting host dirs.
# -----------------------------------------------------------------------------

docker run -d --name ${DB_CONTAINER} \
    --network ${DB_NET} \
    -p 5432:5432 \
    -v "${HERE}/db-server":/mnt/db-server:Z \
    -e POSTGRES_DB=rocm_production_sim \
    -e POSTGRES_USER=mydbuser \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    postgres:16

# Wait for Postgres to be ready (health check) because 'docker run' returns instantly, 
# but the database process needs time to load its internal files.
for i in {1..10}; do
    if docker exec ${DB_CONTAINER} pg_isready; then break; fi
    sleep 1
done
echo " -> `db-server` is Ready!"

# =============================================================================
# STEP 3: Bootstrap Schema & Data (The Filing Cabinet)
# =============================================================================
echo "[Step 3/4] Bootstrapping Table Structure and Seed Data via 'mounts'..."

# -----------------------------------------------------------------------------
# COMMAND: docker exec & psql
# DESCRIPTION: "Logs in" to the running container to run our SQL files.
# KEY CHANGES FROM EARLIER TUTORIALS:
#   1. We use `schema.sql` to define tables and Foreign Keys.
#   2. We now load `seed.sql` using pure SQL. 
#      (We removed the fragile CSV/COPY method in favor of semantic subqueries).
# -----------------------------------------------------------------------------

docker exec ${DB_CONTAINER} psql -U mydbuser rocm_production_sim -f /mnt/db-server/schema.sql
docker exec ${DB_CONTAINER} psql -U mydbuser rocm_production_sim -f /mnt/db-server/seed.sql

echo " -> DB Structure: 2 Distro Environments | Packages Loaded"

# =============================================================================
# STEP 4: Start Poller (The Worker Node)
# =============================================================================
echo "[Step 4/4] Starting `rocm-poller`... This is a remote GPU tester in our lab..."

# -----------------------------------------------------------------------------
# COMMAND: docker run (Poller Worker)
# DESCRIPTION: Spins up the worker that queries the brokered database.
# KEY CHANGE: Added ':Z' to the mount flag here as well, ensuring your poller 
#             can write logs/artifacts back to the host without SELinux errors.
# -----------------------------------------------------------------------------

docker run --name ${POL_CONTAINER} \
    --network ${DB_NET} \
    -v "${HERE}/poller":/mnt:Z \
    python:3.9-slim \
    bash -c "pip install psycopg2-binary > /dev/null && python /mnt/poll.py"

# Success Message
echo ""
echo "========================================================================="
echo " SIMULATION COMPLETE: Run './run.sh' again to see the updated status!"
echo "========================================================================="
