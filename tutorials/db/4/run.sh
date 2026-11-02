#!/bin/bash
set -e

echo "========================================================================="
echo " ROCm Database Simulator: Artifacts & References (SECTION 7)"
echo "-------------------------------------------------------------------------"

# Determine the script's own directory based on its location ('$0'), regardless of where it is invoked from.
HERE="$(cd "$(dirname "$0")" && pwd)"

STATE_CONTAINER="state-store-db"   # The hostname for our persistent data broker.
ARTIFACT_NET="rocm-artifact-net"    # Isolated network for this simulation.
RUNNER_CONTAINER="test-runner"      # The worker container writing results back.

# =============================================================================
# CLEANUP PHASE
# =============================================================================
echo "[Step 1/4] Cleaning up environment..."
docker network rm ${ARTIFACT_NET} > /dev/null 2>&1 || true
docker rm -f ${STATE_CONTAINER} >/dev/null 2>&1 || true
docker rm -f ${RUNNER_CONTAINER} >/dev/null 2>&1 || true

# =============================================================================
# NETWORK PHASE: The "Private Switch"
# =============================================================================
echo "[Step 1/4] Creating the artifact network..."

# Key behaviors of a Docker Bridge (VLAN) for future Section 7 production awareness:
# 1. Virtual Wiring: Containers can talk to each other's IPs as if they were on a physical switch.
docker network create ${ARTIFACT_NET}

# =============================================================================
# STEP 2: Start State Store (The Broker)
# =============================================================================
echo "[Step 2/4] Starting `state-store-db` (Persistent State)..."

# In Section 7, our state node is the sole authority for all run receipts.
docker run -d --name ${STATE_CONTAINER} \
    --network ${ARTIFACT_NET} \
    -p 5432:5432 \
    -e POSTGRES_DB=artifact_state \
    -e POSTGRES_USER=mydbuser \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    postgres:16

for i in {1..10}; do
    if docker exec ${STATE_CONTAINER} pg_isready; then break; fi
    sleep 1
done
echo " -> `state-store-db` is Ready!"

# =============================================================================
# STEP 3: Bootstrap Schema & Mock Artifacts
# =============================================================================
echo "[Step 3/4] Defining the artifacts table..."

# In Section 7, we don't store massive files directly in Postgres (it bloats the DB). 
# Instead, we keep file contents in a mount and only store metadata (SHA-256, paths) in the DB.
docker exec ${STATE_CONTAINER} psql -U mydbuser artifact_state << 'DBEOF'
CREATE TABLE IF NOT EXISTS run_receipts (
    job_id text PRIMARY KEY,
    status text CHECK (status IN ('passed', 'failed')),
    log_sha256 text,       -- The unique ID for the stored file
    log_path text,         -- The local path where the runner saved it
    node_reported_at timestamptz DEFAULT now()
);

-- Seed a "previous" run that this worker will be compared against later by the dashboard
INSERT INTO run_receipts (job_id, status, log_sha256, log_path) VALUES 
('test-f44-legacy-001', 'passed', 'a87ff679a2f3e71d9181a67b7542122c', '/mnt/artifacts/legacy_log.txt');
DBEOF

echo " -> State store initialized with schema and legacy baseline."

# =============================================================================
# STEP 4: The Runner (Pushing Results back to the DB)
# =============================================================================
echo "[Step 4/4] Executing `test-runner` against upstream..."

# In a real lab, this container would be built once (`Dockerfile.runner`) and 
# deployed to any GPU machine. Here it runs in our isolated sandbox network.
docker run --name ${RUNNER_CONTAINER} \
    --network ${ARTIFACT_NET} \
    -v "${HERE}/runner":/mnt \  # Mounts local files directly into the runner's /mnt folder
    python:3.9-slim \
    bash -c "sleep 2 && python /mnt/scripts/write_receipt.py ${STATE_CONTAINER}"

# =============================================================================
# STEP 5: The Dashboard (Viewing Results without downloading files)
# =============================================================================
echo "-> [Dashboard] Querying the 'run-receipt' for the current wave..."

# A dashboard only needs metadata to display a status or trend line. It never 
# downloads the raw log file unless a user specifically clicks "Download".
docker run --rm \
    --network ${ARTIFACT_NET} \
    python:3.9-slim \
    bash -c "python /dev/stdin << 'DASHEOF'
import os, sys
import psycopg2

# 1. The dashboard reads from the state store only to see the job status
conn = psycopg2.connect(host='state-store-db', dbname='artifact_state', user='mydbuser')
cur = conn.cursor()
print('>>> Dashboard Querying Run Receipts...')
cur.execute(\"\"\" 
    SELECT job_id, status, node_reported_at FROM run_receipts ORDER BY node_reported_at DESC; 
\"\"\")
for row in cur.fetchall():
    print(f'  [Result] Job: {row[0]} -> Status: {row[1]} (Logged at: {row[2].strftime(\"%H:%M\")})')

print('\\n[Notice]: The dashboard does NOT show raw file contents here.')
print('[Notice]: It only serves as a read-only view of the brokered state.')
DASHEOF"

echo ""
echo "========================================================================="
echo " SIMULATION COMPLETE: The Runner pushed metadata; Dashboard read it."
echo "========================================================================="
