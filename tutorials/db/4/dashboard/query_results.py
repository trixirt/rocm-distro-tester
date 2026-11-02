#!/usr/bin/env python3
"""
query_results.py (SECTION 7.7: Dashboard as SQL Projection)

Simulates a read-only dashboard querying the State Store broker.
"""

import sys
import psycopg2

if __name__ == "__main__":
    try:
        conn = psycopg2.connect(
            host="state-store-db", dbname="artifact_state", user="mydbuser"
        )

        with conn.cursor() as cur:
            print("\n>>> [Dashboard] Scanning State Store for pending/updated runs...")

            # We query the specific view that the actual dashboard uses to render status bars.
            # In production, this would be a SQL VIEW like 'v_test_queue' or 'v_regressions'.
            cur.execute("""
                SELECT job_id, status, node_reported_at 
                FROM run_receipts 
                ORDER BY node_reported_at DESC;
            """)

            rows = cur.fetchall()

            if not rows:
                print("[Notice] No runs found in the broker.")
            else:
                for row in rows:
                    # The dashboard displays the status and links to logs, but doesn't load them.
                    print(
                        f"  [JOB] {row[0]} -> Status: {row[1]:<8} | Logged at: {row[2]}"
                    )

        conn.close()

    except Exception as e:
        # Broad exception is acceptable here for a simulator/dashboard that wants to
        # catch any environment failure (e.g., network downtime).
        print(f"[CRITICAL ERROR] Dashboard failed to render state: {e}")
        sys.exit(1)
