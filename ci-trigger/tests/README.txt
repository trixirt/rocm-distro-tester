ROCm-Distro-Tester Python Unit Tests
=====================================

Directory: ci-trigger/tests/

Purpose
-------
Comprehensive pytest unit tests for all Python CI components in the rocm-distro-tester project.

Test Files
----------
1. test_poll_fedora_builds.py
   - Tests the Fedora Koji poller (poll_fedora_builds.py)
   - 17 test functions covering state management, API querying, error handling
   - Uses pytest-mock for comprehensive mocking of external dependencies

2. test_poll_archlinux_builds.py
   - Tests the ArchLinux poller (poll_archlinux_builds.py)  
   - 14+ test functions covering state management, official repo + AUR queries
   - Mock handling for both Arch official repositories and AUR API responses

3. conftest.py
   - pytest configuration file with shared fixtures
   - Provides mock response factories, temp directories, and import path injection
   - Auto-loaded by pytest for all test modules in this directory

Running Tests (from repository root)
------------------------------------
cd rocm-distro-tester

# Run all tests with verbose output
python3 -m pytest ci-trigger/tests/ -v

# Run specific module only
python3 -m pytest ci-trigger/tests/test_poll_fedora_builds.py -v

# With test coverage (requires pytest-cov)
python3 -m pytest ci-trigger/tests/ --cov=ci-trigger/poll_fedora_builds.py --cov-report=html

# Quick sanity check on just the package matrix tests
python3 -m pytest ci-trigger/tests/test_poll_fedora_builds.py::TestPackageMatrixGeneration -v

Test Structure Pattern
----------------------
All tests follow standard pytest patterns:
- Use class-based test organization with descriptive class names (e.g., TestFooAPIQuerying)
- Individual test methods start with "test_" prefix
- Fixtures injected via function arguments (mocker, temp_test_dir, etc.)
- Mock objects replace external service calls (Koji API, ArchLinux search URLs)

Dependencies
------------
pytest >= 8.0 (tested with 9.1.1)
pytest-mock (pytest plugin for mocking)
pytest-cov (optional, for coverage reports)

Test Execution Time
-------------------
Typical full test run: < 1 second
Per-module individual runs: < 0.5 seconds
