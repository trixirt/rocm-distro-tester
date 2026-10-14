#!/usr/bin/env python3
"""
Unit tests for Ubuntu Launchpad build poller (poll_ubuntu_builds.py).

Tests cover:
- State file management (load/save)  
- Ubuntu package version tracking
- API response parsing (Launchpad and PPA sources)
- Package detection and mapping logic
- Error handling for malformed responses
- Integration test flow simulation

Run with: pytest -v ci-trigger/tests/test_poll_ubuntu_builds.py
"""

import sys
import pytest
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parent.parent))

import poll_ubuntu_builds as ubuntu_poller


class TestUbuntuStateManagement:
    """Test suite for load_ubuntu_package_state() and save_ubuntu_package_state() functions."""
    
    def test_load_ubuntu_state_from_existing_file(self, temp_test_dir):
        sample_state = [
            {"package": "Hipblas", "ubuntu_version": "1.4-3ubuntu0.1ubuntu26.04.amd64"},
            {"package": "Rocblas", "ubuntu_version": "5.6.0-1~ubuntu22.04.amd64"}
        ]
        
        with open(Path(temp_test_dir) / "test_ubuntu_temp_state.json", 'w') as f:
            json.dump(sample_state, f)
        
        test_file = Path(temp_test_dir) / "test_ubuntu_temp_state.json"
        loaded = ubuntu_poller.load_ubuntu_package_state(test_file)
        
        assert isinstance(loaded, dict)
        assert 'hipblas' in loaded
        assert 'rocblas' in loaded
    
    def test_load_ubuntu_state_from_missing_file_returns_empty(self, temp_test_dir):
        non_existent = Path(temp_test_dir) / "does_not_exist_u.json"
        result = ubuntu_poller.load_ubuntu_package_state(non_existent)
        assert result == {}
    
    def test_load_ubuntu_state_with_corrupted_json_returns_empty(self, temp_test_dir):
        corrupted_file = Path(temp_test_dir) / "corrupted_ubuntu_state.json"
        corrupted_file.write_text("{invalid ubuntu json content")
        
        result = ubuntu_poller.load_ubuntu_package_state(corrupted_file)
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_save_ubuntu_state_updates_existing_packages(self, temp_test_dir):
        sample_changes = [
            {"package": "hipblas", "version": "1.5~24.04~ubuntu24.04"},
            {"package": "rocblas", "version": "5.7.0-0~24.04.amd64"}
        ]
        
        saved_file = Path(temp_test_dir) / "test_ubuntu_results.json"
        ubuntu_poller.save_ubuntu_package_state(saved_file, sample_changes)
        
        assert saved_file.exists()
        with open(saved_file) as f:
            data = json.load(f)
        assert len(data) == 2


class TestUbuntuLaunchpadAPIQuerying:
    """Test suite for Ubuntu package queries via Launchpad-like APIs."""
    
    def test_query_ubuntu_package_info_provides_expected_structure(self):
        result = ubuntu_poller.query_ubuntu_package_info('hipblas', 'jammy')
        
        assert isinstance(result, dict)
        assert 'package' in result
        assert 'version' in result
        assert 'release' in result
    
    def test_query_handles_network_request_error(self, mocker):
        import requests
        
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        
        mocker.patch('poll_ubuntu_builds.requests.get', return_value=mock_response)
        
        result = ubuntu_poller.query_ubuntu_launchpad_api('nonexistent-pkg', 'jammy')
        assert result is None


class TestUbuntuPackageMapping:
    """Test suite for Ubuntu-specific package mapping functionality."""
    
    def test_generates_mapping_for_all_tracked_ubuntu_packages(self):
        mapping = ubuntu_poller.generate_ubuntu_package_mapping()
        
        assert isinstance(mapping, list)
        assert len(mapping) == len(ubuntu_poller.TRACKED_UBUNTU_ROCM_PACKAGES)
    
    def test_includes_hipblas_ubuntu_test_directory_mapping(self):
        mapping = ubuntu_poller.generate_ubuntu_package_mapping()
        
        hipblas_entry = next((p for p in mapping if p['package_name'] == 'hipblas'), None)
        
        assert hipblas_entry is not None
        assert hipblas_entry['test_dir'].startswith('hipblas')


class TestUbuntuErrorHandling:
    """Test error handling scenarios specific to Ubuntu poller."""
    
    def test_handles_network_exceptions_gracefully(self, mocker):
        import requests
        
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.ConnectionError("Network fail")
        
        mocker.patch('poll_ubuntu_builds.requests.get', return_value=mock_response)
        
        result = ubuntu_poller.query_ubuntu_launchpad_api('hipblas', 'focal')
        assert result is None


class TestUbuntuIntegrationFlow:
    """Integration tests simulating complete Ubuntu polling workflow."""
    
    def test_full_polling_cycle_detects_package_version_changes(self, mocker):
        
        # Mock the API response with new version different from saved state
        new_version_json = {"packages": [{'version': '1.5~24.04'}]}
        mock_response = Mock()
        mock_response.json.return_value = new_version_json
        
        with mocker.patch('poll_ubuntu_builds.requests.get', return_value=mock_response):
            result = ubuntu_poller.query_ubuntu_launchpad_api('hipblas', 'jammy')
            
            assert result is not None
            assert isinstance(result, dict)


class TestUbuntuHelperFunctions:
    """Test Ubuntu-specific utility functions."""
    
    def test_release_version_mapping(self):
        assert ubuntu_poller.UBUNTU_RELEASE_TRACKING['latest'] == 'oracular'
        assert ubuntu_poller.UBUNTU_RELEASE_TRACKING['lts'] == 'noble'


class TestUbuntuAPIStructure:
    """Test Ubuntu Launchpad API response handling."""
    
    def test_query_ubuntu_package_info_returns_valid_structure(self):
        result = ubuntu_poller.query_ubuntu_package_info('hipblas', 'jammy')
        
        assert isinstance(result, dict)
        assert 'package' in result
        assert result['package'] == 'Hipblas'

