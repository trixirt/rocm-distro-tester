#!/usr/bin/env python3
# =============================================================================
# Poller Script: Simulates a remote distro poller detecting an update and 
# writing it back to the DB server.
# =============================================================================

import sys # Used for system-level actions like exiting with specific codes (e.g., if network fails)

# =============================================================================
# THE DATABASE DRIVER: Why psycopg2?
# =============================================================================
import psycopg2

# In production environments (specifically Section 7 of our ROCm State Stack),
# we choose psycopg2 over the newer psycopg3 for three key reasons:
#
# 1. Maturity & Stability: psycopg2 has been the industry standard since 2006. 
#    Its C-level connection pooling and error handling are battle-tested, which is critical
#    for high-frequency polling in a CI/CD environment where crashes have to be avoided.
#
# 2. Ecosystem Support: Most major scientific Python packages (like pandas or Scikit-learn) 
#    use sqlalchemy under the hood, and their backends currently prioritize psycopg2 support.
#
# 3. Minimal Configuration: It provides a direct, "no-bells-and-whistles" connection to the wire,
#    making it easier to learn how databases work on the network level before adding abstraction layers like ORM.


# =============================================================================
# CONFIGURATION
# =============================================================================
# We use the Container Hostname `db-server` because we attached both containers
# to the same Docker network bridge in our run.sh script.

DB_CONFIG = {
    'host': 'db-server',      # The "address book" entry for our database on the network.
    'port': 5432,             # The industry-standard port for PostgreSQL services.
    'dbname': 'rocm_production_sim', # The specific database room we are opening.
    'user': 'mydbuser'        # The ID card used to enter that room.
}

def check_status():
    try:
        # connect() reaches out over the network to 'db-server:5432'.
        conn = psycopg2.connect(**DB_CONFIG)
        
        # A cursor is like a "pointer" in your filing cabinet; it helps you navigate and extract 
        # specific rows one by one without loading the whole database into memory.
        cur = conn.cursor()

        print("[Poller] Connecting to `db-server`... OK")
        
        # 1. Read current state via network query
        print("[Poller] Querying 'hipblas' from `db-server`...")
        # The %s placeholder ensures the data is escaped safely (prevents SQL injection)
        cur.execute("SELECT package_name, current_version, status FROM packages WHERE name = %s;", ('hipblas',))
        row = cur.fetchone() # Fetch only the very first result (our target package)

        if not row:
            print("[ERROR] Package 'hipblas' not found in DB!")
            sys.exit(1)

        pkg_name, current_ver, status = row
        print(f"  -> Found: {pkg_name} ({current_ver}) - Status: {status}")

        # 2. Simulate detecting a NEW version (e.g., from Launchpad/Koji API)
        new_version = "10.3.5" 

        if status == 'pending' and new_version != current_ver:
            print(f"[Poller] UPSTREAM UPDATE DETECTED! New version: {new_version}")
            print("[Poller] Writing update back to `db-server`...")

            # 3. Write update (Simulating "Package built successfully on lab node")
            cur.execute("""
                UPDATE packages 
                SET current_version = %s, status = 'updated', last_updated = now()
                WHERE package_name = %s;
            """, (new_version, pkg_name))
            
            # In a real network transaction, if we update two rows and the second fails, 
            # we want to "undo" the first one. This ensures our data stays consistent.
            conn.commit() 

            print("[Poller] SUCCESS! Database updated via network.")
        else:
            print("[Poller] No updates detected for this run. Database is current.")

        cur.close()
        conn.close()

    except Exception as e:
        # Catching the specific "cannot connect" error helps us diagnose if it's a 
        # code issue or a network/Docker issue (e.g., container wasn't started).
        print(f"\n[CRITICAL ERROR] Could not communicate with `db-server`: {e}")
        print("  -> Did you run './run.sh' first to start the Docker environment?")
        sys.exit(1)

if __name__ == "__main__":
    check_status()
