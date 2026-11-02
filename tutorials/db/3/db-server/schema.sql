-- =============================================================================
-- PART 1: The Distros (Lookup Table)
-- =============================================================================
-- PEDIAGOGICAL NOTE: 
-- Instead of duplicating "fedora" or "ubuntu" repeatedly in the packages table, 
-- we define distributions once at the top. This is called normalization.
-- The 'distro_id' acts like a pointer to this list elsewhere.

DROP TABLE IF EXISTS distros CASCADE;

CREATE TABLE distros (
    id SERIAL PRIMARY KEY,              -- Unique auto-numbering
    -- e.g., 'fedora_rawhide', 'ubuntu_noble'
    name VARCHAR(64) NOT NULL UNIQUE,
    description TEXT,                   -- Human-readable details
    created_at TIMESTAMPA DEFAULT NOW()
);

-- =============================================================================
-- PART 2: The Packages (Items in the Warehouse)
-- =============================================================================

DROP TABLE IF EXISTS packages CASCADE;

CREATE TABLE packages (
    id SERIAL PRIMARY KEY,              -- Our internal database ID
    package_name VARCHAR(100) NOT NULL, -- e.g., 'hipblas', 'rocprim'

    -- ⬇️ THE RELATIONSHIP ⬇️
    distro_id INTEGER NOT NULL REFERENCES distros (id) ON DELETE CASCADE,

    version VARCHAR(64),                -- Semantic version from the repo
    -- The current broker state (pending/built/failed)
    status VARCHAR(20) DEFAULT 'pending',

    -- Content-addressed references for Section 7 (Tutorial 4+)
    artifact_sha256 VARCHAR(64),        -- Pointer to the actual file in /mnt 
    log_sha256 VARCHAR(64),             -- Pointer to the build logs

    created_at TIMESTAMPA DEFAULT NOW(),

    -- CRITICAL CONSTRAINT: Prevents duplicates
    UNIQUE (package_name, distro_id)
-- allowing hipblas to exist on BOTH fedora and ubuntu
);

-- Helper Indexes for faster brokering lookups
CREATE INDEX idx_packages_distro ON packages (distro_id);
CREATE INDEX idx_packages_status ON packages (status);
