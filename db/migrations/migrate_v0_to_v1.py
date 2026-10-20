import psycopg2
from pathlib import Path
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_SCHEMA_NAME = "rocm_tester"
SCHEMA_VERSION_FILE = Path("db/schema/current_version.txt")

# --- Configuration (from poll_fedora_builds.py logic) ---
TRACKED_ROCM_PACKAGES = [
    'hipblas', 'rocblas', 'hipsolver', 'rocsolver',
    'hipfft',   'rocfft',  'hipsparse','rocsparse',
    'rccl',     'miopen',  'rocrand'
]

RELEASE_IMAGES = {
    'rawhide': 'fedora:rawhide',
    'f45':     'fedora:45',
    'f44':     'fedora:44',
    'f43':     'fedora:43',
}

def get_db_connection():
    """Connect to the database using environment variables or defaults."""
    host = os.getenv("DB_HOST", "state-db")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER", "rocmtest")
    pwd  = os.getenv("DB_PASSWORD", "")
    
    try:
        conn = psycopg2.connect(
            host=host, port=port, database="rocmtest", 
            user=user, password=pwd
        )
        logger.info(f"[migrate_db] Connected to PostgreSQL at {host}:{port}")
        return conn
    except Exception as e:
        logger.error(f"Could not connect. Ensure DB is running. Error: {e}")
        sys.exit(1)

def get_current_schema_version(conn):
    """Check the current schema version from the config table or assume 0 if missing."""
    with conn.cursor() as cur:
        # Check if the table exists; if not, we are at v0
        cur.execute(""" 
            SELECT EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'db_version'
            ) 
        """)
        version_exists = cur.fetchone()[0]
        
        if not version_exists:
            logger.info("[migrate_db] No prior schema version found. Starting fresh migration.")
            return 0
        
        cur.execute("SELECT version_key, version_value FROM db_version WHERE category='schema'")
        row = cur.fetchone()
        if row:
            return int(row[1])
        return 0

def apply_migration_v1(conn):
    """Apply v1 schema and seed initial data."""
    schema_file = Path("db/schema/v1_fedora_packages.sql")
    
    sql_content = schema_file.read_text()
    
    with conn.cursor() as cur:
        logger.info(f"[migrate_db] Executing Schema from {schema_file.name}...")
        
        # 1. Create DB_VERSION tracking table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS db_version (
                category TEXT PRIMARY KEY, 
                version_key TEXT, 
                version_value TEXT
            )
        """)
        
        # Execute the SQL statements
        conn.commit()
    from psycopg2.extras import execute_batch
    
    statements = []
    for stmt in sql_content.split(";"):
        stmt = stmt.strip()
        if stmt:
            statements.append(stmt)
            
    # Split out the INSERTs to handle them separately as seed data
    ddl_statements = [s for s in statements if not s.startswith("INSERT")]
    seed_statements = [s + ";" for s in statements if s.startswith("INSERT")]

    with conn.cursor() as cur:
        logger.info("[migrate_db] Applying DDL tables and views...")
        for stmt in ddl_statements:
            try:
                cur.execute(stmt)
            except Exception as e:
                # Ignore duplicate object errors (idempotent safety)
                if "already exists" not in str(e).lower():
                    raise

        logger.info("[migrate_db] Applying Seed Data...")
        for stmt in seed_statements:
            cur.execute(stmt)

    conn.commit()

def update_schema_version(conn, version):
    """Update the DB_VERSION table to reflect current migration."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO db_version (category, version_key, version_value)
            VALUES ('schema', 'current', %s)
            ON CONFLICT (category) DO UPDATE SET version_value = EXCLUDED.version_value;
        """, [str(version)])
    conn.commit()

def main():
    logger.info("="*60)
    logger.info("Starting ROCm-DB Migration Process")
    logger.info("="*60)

    conn = get_db_connection()
    
    current_version = get_current_schema_version(conn)
    logger.info(f"[migrate_db] Current Schema Version: {current_version}")

    if current_version == 0:
        apply_migration_v1(conn)
        update_schema_version(conn, 1)
        SCHEMA_VERSION_FILE.write_text("1")
        logger.warning("[migrate_db] Success! Database initialized at v1.")
        logger.warning("[migrate_db] Note: This migration populated seed data based on hardcoded poller packages.")
    else:
        logger.info(f"[migrate_db] No migration needed. Already at v{current_version}.")

    conn.close()

if __name__ == "__main__":
    main()
