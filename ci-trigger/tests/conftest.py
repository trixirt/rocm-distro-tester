"""
pytest configuration and shared test fixtures for ROCm-Tester CI module tests.

This file provides pytest fixtures that are automatically available to all
test modules in this directory, including mocked responses and helper utilities
for testing package polling scripts.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta


# =============================================================================
# TEST CONSTANTS - Simulated API Responses
# =============================================================================

# Simulated Fedora Koji API responses
FEDORA_KOJI_PKG_LIST_SUCCESS = [
    {'name': 'hipblas', 'latest_builds': [{'task_id': 123456, 'version': '5.7.0'}]},
    {'name': 'rocblas', 'latest_builds': [{'task_id': 123457, 'version': '6.0.0'}]},
]

FEDORA_KOJI_NO_PACKAGE = []

# Simulated ArchLinux API responses
ARCHLINUX_OFFICIAL_API_SUCCESS = """<html>
<body>
    <a href="/packages/hip">hip</a> (5.7.0-1) (archlinux)
</body>
</html>"""

ARCHLINUX_AUR_API_SUCCESS = {
    "resultcount": 1,
    "results": [{
        "Name": "hip",
        "Version": "5.7.0",
        "NumVotes": "243",
        "LastModified": int((datetime.now() - timedelta(days=1)).timestamp())
    }]
}

ARCHLINUX_NO_PACKAGE = {"resultcount": 0, "results": []}


# =============================================================================
# FIXTURES: Mocked Responses and Paths
# =============================================================================

@pytest.fixture
def temp_test_dir(tmp_path):
    """Create a temporary test directory for state files."""
    return tmp_path


@pytest.fixture
def mock_koji_response():
    """Provide a function that returns mocked Koji API response data."""
    def make_response(status="success", packages=None):
        if packages is None:
            packages = FEDORA_KOJI_PKG_LIST_SUCCESS
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = packages
        return mock_response
    
    return make_response


@pytest.fixture
def mock_arch_official_api():
    """Provide a function for mocking ArchLinux official API responses."""
    def generate_html(package_found=True):
        if package_found:
            return ARCHLINUX_OFFICIAL_API_SUCCESS
        else:
            return "<html><body>No packages found</body></html>"
    
    mock_response = Mock()
    mock_response.text = "test"  # Will be overwritten for each call
    
    def make_response(fallback_text=None, package_ok=True):
        mock_response.text = fallback_text or generate_html(package_ok)
        return mock_response
    
    return make_response


@pytest.fixture
def mock_arch_aur_api():
    """Provide a function for mocking AUR API responses."""
    success_resp = Mock()
    success_resp.json.return_value = ARCHLINUX_AUR_API_SUCCESS
    success_resp.status_code = 200
    
    fail_resp = Mock()
    fail_resp.json.return_value = ARCHLINUX_NO_PACKAGE
    fail_resp.status_code = 200
    
    def make_response(result_type="success"):
        if result_type == "success":
            return success_resp
        else:
            return fail_resp
    
    return make_response


# =============================================================================
# FIXTURES: Test State Files (fedora & archlinux)
# =============================================================================

@pytest.fixture
def test_state_fedora(temp_test_dir):
    """Pre-load federated Koji build state for testing."""
    state_file = temp_test_dir / "fedora_build_state.json"
    
    sample_state = [
        {"name": "hipblas", "last_build_id": "123456"},
        {"name": "rocblas", "last_build_id": "123457"}
    ]
    
    with open(state_file, 'w') as f:
        json.dump(sample_state, f)
    
    return state_file


@pytest.fixture
def test_state_arch(temp_test_dir):
    """Pre-load ArchLinux version state for testing."""
    state_file = temp_test_dir / "arch_build_state.json"
    
    sample_state = [
        {"name": "hip", "last_version": "5.6.0", "repo": "official"},
        {"name": "rocblas", "last_version": "5.9.0", "repo": "AUR"}
    ]
    
    with open(state_file, 'w') as f:
        json.dump(sample_state, f)
    
    return state_file


@pytest.fixture
def empty_state_file(temp_test_dir, state_type="fedora"):
    """Create an empty JSON state file for testing fresh initialization."""
    state_file = temp_test_dir / f"test_{state_type}_state.json"
    
    sample_initial_state = []
    
    with open(state_file, 'w') as f:
        json.dump(sample_initial_state, f)
    
    return state_file


# =============================================================================
# FIXTURES: API Response Mocking Contexts
# =============================================================================

@pytest.fixture
def patched_requests_koji():
    """Context manager that patches requests.get() with mock for Koji API."""
    with patch('poll_fedora_builds.requests.get') as mock_get:
        yield mock_get


@pytest.fixture
def patched_requests_arch_official():
    """Context manager that patches requests.get() with mock for Arch official API."""
    with patch('poll_archlinux_builds.requests.get') as mock_get:
        yield mock_get


@pytest.fixture
def patched_requests_arch_aur():
    """Context manager that patches requests.get() with mock for AUR API."""
    with patch('poll_archlinux_builds.requests.get') as mock_get:
        yield mock_get


# =============================================================================
# FIXTURES: Python Scripts Load
# =============================================================================

@pytest.fixture(autouse=True)
def inject_system_path():
    """Ensure ci-trigger directory is in sys.path for imports."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def fedora_poller_module():
    """Load the fedora poller module for testing imports (without execution)."""
    import importlib.util
    
    spec = importlib.util.spec_from_file_location(
        "poll_fedora_builds", 
        Path(__file__).parent.parent / "poll-fedora-builds.py"
    )
    
    module = importlib.util.module_from_spec(spec)
    # Don't execute yet - we'll handle imports in each test
    
    return module, spec


@pytest.fixture
def arch_poller_module():
    """Load the Arch Linux poller module for testing imports."""
    import importlib.util
    
    spec = importlib.util.spec_from_file_location(
        "poll_archlinux_builds", 
        Path(__file__).parent.parent / "poll-archlinux-builds.py"
    )
    
    module = importlib.util.module_from_spec(spec)
    
    return module, spec


# =============================================================================
# UTILITY FUNCTIONS (for tests)
# =============================================================================

def create_mocked_build_entry(pkg_name, build_id="123999", task_id=123998, version="5.8.0"):
    """Helper to create a mocked Koji build structure."""
    return {
        'name': pkg_name,
        'latest_builds': [{'task_id': task_id, 'version': version}]
    }


def create_mocked_arch_search_html(pkg_name, found=True):
    """Helper to create mocked ArchLinux HTML search result."""
    if found:
        return f"""<html>
<body>
    <a href="/packages/{pkg_name.lower()}">{pkg_name}</a> (5.8.0-1) (archlinux)
</body>
</html>"""
    else:
        return "<html><body>No packages found for this search</body></html>"


# =============================================================================
# PYTEST CONFIGURATION OPTIONS
# =============================================================================

def pytest_configure(config):
    """Override or add custom pytest configuration."""
    # Enable verbose output by default in test runs
    config.option.verbose = True
    config.option.cacheselection = []  # Clear cache between runs
    
    # Register markers for test documentation
    config.addinivalue_line(
        "markers", 
        "integration: mark tests as integration-style (use mocks to simulate API calls)"
    )
    config.addinivalue_line(
        "markers",
        "unit: mark unit-level tests that focus on specific functions"
    )
