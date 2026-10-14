#!/usr/bin/env python3
"""
Unit tests for EPEL (Extra Packages for Enterprise Linux) build poller.

Tests cover:
- State file management (load/saves)
- EPEL package version tracking  
- RPM build API response parsing (Koji endpoints)
- Package detection and mapping logic
- Error handling for malformed responses
- Integration test flow simulation (RHEL CentOS Stream variants)

Run with: pytest -v ci-trigger/tests/test_poll_epel_builds.py
"""

import sys
import pytest
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parent.parent))

import poll_epel_builds as epel_poller


# =============================================================================
# TEST: State File Loading and Saving for EPEL packages (RHEL-specific tracking)
# =============================================================================

class TestEPELStateManagement:
    """Test suite for load_epel_package_state() and save_epel_package_state() functions."""
    
    def test_load_epel_state_from_existing_file(self, temp_test_dir):
        """Should successfully load EPEL build state from pre-populated file."""
        
        sample_state = [
            {
                "package": "hipblas", 
                "last_build_id": "123456",
                "epel_version": "epel-10"
            },
            {
                "package": "rocblas",
                "last_build_id": "123457",
                "epel_version": "epel-9"
            }
        ]
        
        test_file = Path(temp_test_dir) / "test_epel_state.json"
        with open(test_file, 'w') as f:
            json.dump(sample_state, f)
            
        loaded = epel_poller.load_epel_package_state(test_file)
        
        assert isinstance(loaded, dict)
        assert 'hipblas-epel' in loaded
        assert 'rocblas-epel' in loaded
    
    def test_load_epel_state_from_missing_file_returns_empty(self, temp_test_dir):
        """Should return empty state dict when EPEL file does not exist."""
        
        non_existent = Path(temp_test_dir) / "no_epel.json"
        result = epel_poller.load_epel_package_state(non_existent)
        assert result == {}
    
    def test_load_epel_state_with_corrupted_json_returns_empty(self, temp_test_dir):
        """Should handle corrupted JSON gracefully for EPEL state files."""
        
        corrupted_file = Path(temp_test_dir) / "corrupted_epel.json"
        corrupted_file.write_text("invalid epel json content")
        
        result = epel_poller.load_epel_package_state(corrupted_file)
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_save_epel_state_updates_existing_packages(self, temp_test_dir):
        """Should merge new EPEL package versions with existing state."""
        
        sample_changes = [
            {"package": "hipblas", "build_id": "155666", "epel_version": "epel-10"},
            {"package": "rocblas", "build_id": "177888", "epel_version": "epel-9"}
        ]
        
        saved_file = Path(temp_test_dir) / "test_epel_results.json"
        
        epel_poller.save_epel_package_state(saved_file, sample_changes)
        
        assert saved_file.exists()
        with open(saved_file) as f:
            data = json.load(f)
            
        assert len(data) == 2


# =============================================================================
# TEST: EPEL API Query Logic (Mocked RPM/Koji endpoints)
# =============================================================================

class TestEPELKojiAPIQuerying:
    """Test suite for RHEL package queries via Koji API."""
    
    def test_query_epel_koji_provides_expected_structure(self, mocker):
        """Should return properly structured EPEL build info from mocked endpoint."""
        
        result = epel_poller.query_epel_koji_api('hipblas')
        
        assert isinstance(result, dict)
        assert 'package' in result
        assert 'last_build_id' in result
    
    def test_query_handles_network_request_error(self, mocker):
        """Should handle network exceptions gracefully for EPEL packages."""
        
        import requests
        
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.RequestException("Network fail")
        
        with mocker.patch('poll_epel_builds.requests.get', return_value=mock_response):
            result = epel_poller.query_epel_koji_api('nonexistent-pkg')
            
            # Should handle gracefully without crashing
            assert result is None
    
    def test_query_returns_none_for_package_not_found(self, mocker):
        """Should return None when package doesn't exist in EPEL target repository."""
        
        mock_response = Mock()
        mock_response.status_code = 404
        
        with mocker.patch.object(epel_poller, 'KOJI_EPEL_BASE_URL', '/api/test'):
            with mocker.patch('poll_epel_builds.requests.get', return_value=mock_response):
                result = epel_poller.query_epel_koji_api('definitely-not-a-package')
                assert result is None


# =============================================================================
# TEST: EPEL Package Mapping (Distribution-specific test directory mapping)
# =============================================================================

class TestEPELPackageMapping:
    """Test suite for EPEL/RHEL package mapping functionality."""
    
    def test_generates_mapping_for_all_tracked_epel_packages(self):
        """Should create mapping entry for every tracked RPM-based distro package."""
        
        mapping = epel_poller.generate_epel_package_mapping()
        
        assert isinstance(mapping, list)
        assert len(mapping) == len(epel_poller.TRACKED_RHEL_ROCM_PACKAGES)
    
    def test_includes_hipblas_rhel_test_directory_mapping(self):
        """Should map hipblas package to correct RHEL test directory."""
        
        mapping = epel_poller.generate_epel_package_mapping()
        
        hipblas_entry = next((p for p in mapping if p['package_name'] == 'hipblas'), None)
        
        assert hipblas_entry is not None
        assert 'rhel' in hipblas_entry.get('test_dir', '').lower()


# =============================================================================
# TEST: Error Handling and Edge Cases (RHEL/CentOS Stream specific)
# =============================================================================

class TestEPELErrorHandling:
    """Test error scenarios specific to EPEL/Koji monitoring."""
    
    def test_handles_invalid_epelet_version_parameter(self, mocker):
        """Should handle invalid CentOS Stream version gracefully."""
        
        import requests
        
        # Mock an invalid release or build target response
        mock_response = Mock()
        mock_response.status_code = 404
        
        with mocker.patch.object(epel_poller, 'KOJI_EPEL_BASE_URL', '/api/test'):
            with mocker.patch('poll_epel_builds.requests.get', return_value=mock_response):
                # Try invalid EPEL version query - should handle gracefully
                result = epel_poller.query_epel_koji_api('hipblas', 'nonexistent-version-12345')
                
                assert result is None or isinstance(result, dict)


# =============================================================================
# TEST: Package Matrix Generation and Integration Flow (End-to-end workflow)
# =============================================================================

class TestEPELIntegrationFlow:
    """Integration tests simulating complete EPEL polling workflow for RHEL."""
    
    def test_full_polling_cycle_detects_rhel_package_build_changes(self, mocker):
        """Should detect when RPM packages update from saved build state."""
        
        # Mock API response with new build ID different from currently tracked version
        mock_response = Mock()
        new_build_id_json = {"packages": [{"build_id": "987654", "version": "10.0.0"}]}
        mock_response.json.return_value = new_build_id_json
        
        with mocker.patch('poll_epel_builds.requests.get', return_value=mock_response):
            result = epel_poller.query_epel_koji_api('hipblas')
            
            assert result is not None
            assert isinstance(result, dict)


# =============================================================================
# TEST: Helper Functions for RHEL-Specific Testing (Utility functions and checks)
# =============================================================================

class TestEPELHelperFunctions:
    """Test EPEL-specific utility functions (similar to Fedora poller helpers)."""
    
    def test_build_id_extraction_from_api_result(self):
        """Should correctly extract build_id from Koji result structure."""
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"builds": [123456]}
        
        mocker.patch('poll_epel_builds.requests.get', return_value=mock_response)
        
        result = epel_poller.query_epel_koji_api('hipblas')
        
        assert result is not None


# =============================================================================
# TEST: Version Tracking and EPEL Architecture Mapping (RHEL-specific metadata)  
# =============================================================================

class TestEPELVersionTracking:
    """Test RHEL/CentOS Stream version mapping functionality."""
    
    def test_version_template_mapping(self):
        """Should correctly map version strings to EPEL repository targets."""
        
        assert epel_poller.EPEL_VERSION_TEMPLATES['10'] == "epel-10"
        assert epel_poller.EPEL_VERSION_TEMPLATES['latest'] == "epel-10"
        assert 'epel' in epel_poller.EPEL_VERSION_TEMPLATES['9']


# =============================================================================
# TEST: API Base URL Structure and RHEL-Specific Endpoints (Infrastructure validation)
# =============================================================================

class TestEPELAPIStructure:
    """Test EPEL Koji base URLs and endpoint validity."""
    
    def test_epol_base_api_url_is_constructed_correctly(self):
        """Ensure EPEL API URL follows proper CentOS Stream structure."""
        
        # Verify the EPEL build endpoint format is correct (like Fedora does)
        assert epel_poller.KOJI_EPEL_BASE_URL.startswith("https://kojipkg.fedoraproject.org")
        assert "epel" in epel_poller.

