-- =============================================================================
-- BOOTSTRAP SCRIPT: v1 Schema (Reference from db/schema/v1_fedora_packages.sql)
-- Purpose: Creates the core tables we expect to use in production.
-- =============================================================================

-- Drop existing tables if they exist (make this file idempotent)
DROP TABLE IF EXISTS packages;
DROP TABLE IF EXISTS distros;

-- -----------------------
-- 1. The Distro Environment Table
-- -----------------------
CREATE TABLE distros (
    id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(32) NOT NULL     -- e.g., 'fedora'
);

-- -----------------------
-- 2. The Packages Table
-- -----------------------
CREATE TABLE packages (
    id           int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    package_name text NOT NULL UNIQUE     
);
