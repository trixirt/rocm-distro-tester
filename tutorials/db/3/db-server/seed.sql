-- =============================================================================
-- /tutorials/db/3/seeds/seed.sql
-- =============================================================================

-- 1. Define the Environments (Parent Table)
INSERT INTO distros (name, description) VALUES 
    ('fedora_rawhide', 'Fedora Rawhide Development'),
    ('ubuntu_noble',   'Ubuntu 24.04 LTS Noble');

-- 2. Populate Packages (Child Table) using programmatic linking
-- ===========================================================================
-- PEDIAGOGICAL NOTE:
-- Instead of using literal IDs (1, 2), we use subqueries like 
-- `(SELECT id FROM distros WHERE name = 'fedora_rawhide')`.
-- This decouples our data from the specific row numbers. If you add a new 
-- distro to this file later, these package rows will automatically find their 
-- correct parent without needing manual ID updates.

INSERT INTO 
    packages (package_name, distro_id, version, status) 
VALUES 
    ('hipblas',
        (SELECT id FROM distros WHERE name = 'fedora_rawhide'), -- Decoupled lookup
        '5.7.0-rc3', 'pending');

    ('hipblas',
        (SELECT id FROM distros WHERE name = 'ubuntu_noble'),   -- Decoupled lookup
        '6.1.2-beta', 'pending');
