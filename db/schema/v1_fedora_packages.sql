-- db/schema/v1_fedora_packages.sql
-- Schema Version: v1
-- Purpose: Tracks package versions, release targets, and build states.
-- Replaces: ci-trigger/poll_fedora_builds.py internal state management.

BEGIN;

-- ============================================================================
-- 1. Package Definitions (Canonical list of ROCm packages)
--    Replaces: TRACKED_ROCM_PACKAGES in poll_fedora_builds.py
-- ============================================================================
CREATE TABLE IF NOT EXISTS packages (
    id SERIAL PRIMARY KEY, -- PK is not exposed to application logic via the query builder
    name TEXT UNIQUE NOT NULL CHECK (length(trim(name)) > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'staging')),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE packages IS 'Canonical list of tracked ROCm packages.';
COMMENT ON COLUMN packages.status IS 'Lifecycle status: active (polling enabled), archived (legacy), or staging (testing).';

-- ============================================================================
-- 2. Release Environments (Target distributions and container images)
--    Replaces: RELEASE_IMAGES in poll_fedora_builds.py and similar pollers
-- ============================================================================
CREATE TABLE IF NOT EXISTS releases (
    id SERIAL PRIMARY KEY,
    release_target TEXT UNIQUE NOT NULL CHECK (length(trim(release_target)) > 0), -- e.g., rawhide, f45, jammy
    docker_image_ref TEXT NOT NULL,                                                -- The base image needed to run the poller logic
    
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'eol')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE releases IS 'Available distributions and their containerized environments used for querying.';
COMMENT ON COLUMN releases.release_target IS 'Identifier used by package managers to target a specific version (e.g., "rawhide" or "noble").';
COMMENT ON COLUMN releases.docker_image_ref IS 'The full Docker tag required to run the distro-specific polling commands (dnf, apt, pacman).';

-- ============================================================================
-- 3. Build Tracking State (Current status of every package on every target)
--    Replaces: *_build_state.json files in results/ directory
-- ============================================================================
CREATE TABLE IF NOT EXISTS build_state (
    pkg_id INT NOT NULL REFERENCES packages(id),
    release_id INT NOT NULL REFERENCES releases(id),
    
    -- The actual state data tracked by the pollers
    last_check_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    latest_build_id TEXT,          -- e.g., a Koji build ID or Launchpad revision
    
    CONSTRAINT pk_build_state PRIMARY KEY (pkg_id, release_id)
);

COMMENT ON TABLE build_state IS 'Tracks the last known state of every ROCm package across all target distributions.';
COMMENT ON COLUMN build_state.latest_build_id IS 'The unique identifier for the most recent found version in the respective distro repository.';

-- ============================================================================
-- Seed Data: Initialize with defaults from current poller scripts
-- ============================================================================

-- Release Targets (Fedora, EPEL, Archlinux, Ubuntu)
INSERT INTO releases (release_target, docker_image_ref) VALUES 
('rawhide','fedora:rawhide'), ('f45','fedora:45'), ('f44','fedora:44')
ON CONFLICT (release_target) DO NOTHING;

-- ROCm Packages (From TRACKED_ROCM_PACKAGES in poll_fedora_builds.py)
INSERT INTO packages (name) VALUES 
('hipblas'), ('rocblas'), ('hipsolver'), ('rocsolver'), 
('hipfft'), ('rocfft'), ('rccl'), ('miopen'), ('rocrand')
ON CONFLICT (name) DO NOTHING;

COMMIT;
