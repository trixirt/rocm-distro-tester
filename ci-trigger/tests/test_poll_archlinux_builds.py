#!/usr/bin/env python3
"""
Unit tests for ArchLinux package build poller (poll_archlinux_builds.py).

Tests cover:
- State file management (load/save)
- Arch API response parsing (official + AUR)
- Package detection and tracking logic  
- Error handling for malformed responses
- Integration test flow simulation

Run with: pytest -v ci-trigger/tests/test_poll_archlinux_builds.py
"""

import pytest
import json
from pathlib import Path
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import poll_archlinux_builds as arch_poller


class TestArchStateManagement:
    """Test suite for load_arch_build_state() and save_arch_build_state() functions."""
    
    def test_load_state_from_existing_file(self, temp_test_dir):
        sample_state = [
            {"name": "hip", "last_version": "5.6.0", "repo": "official"}
        ]
        
        with open(Path(temp_test_dir) / "test_arch_temp.json", 'w') as f:
            json.dump(sample_state, f)
        
        result = arch_poller.load_arch_build_state(Path(temp_test_dir) / "test_arch_temp.json")
        
        assert isinstance(result, dict)
        assert "hip" in result
    
    def test_load_state_from_missing_file_returns_empty(self, temp_test_dir):
        non_existent = Path(temp_test_dir) / "does_not_exist.json"
        
        result = arch_poller.load_arch_build_state(non_existent)
        assert result == {}
    
    def test_load_state_with_corrupted_json_returns_empty(self, temp_test_dir):
        corrupted_file = Path(temp_test_dir) / "corrupted.json"
        corrupted_file.write_text("invalid json content")
        
        result = arch_poller.load_arch_build_state(corrupted_file)
        
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_save_state_updates_existing_packages(self, temp_test_dir):
        sample_changes = [
            {"package": "hip", "version": "5.7.0", "timestamp": "2024-10-13T10:53:09"},
            {"package": "rocblas", "version": "6.0.0", "timestamp": "2024-10-13T10:53:09"}
        ]
        
        arch_poller.DEFAULT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state_path = Path(temp_test_dir) / "test_results.json"
        
        arch_poller.save_arch_build_state(state_path, sample_changes)
        
        saved_file = Path(temp_test_dir) / "test_results.json"
        assert saved_file.exists()
        
        with open(saved_file) as f:
            data = json.load(f)
        
        assert len(data) == 2


class TestArchOfficialAPIQuerying:
    """Test suite for ArchLinux official package queries."""
    
    def test_query_official_finds_package_name_exact_match(self, mocker):
        mock_response = Mock()
        search_html = arch_poller.create_mocked_arch_search_html("hip", found=True)
        mock_response.text = search_html
        mock_response.status_code = 200
        
        mocker.patch('poll_archlinux_builds.requests.get', return_value=mock_response)
        
        result = arch_poller.query_archlinux_api("hip")
        
        assert result is not None
        assert result["package"] == "Hip"
        assert result["available_in_arch"] is True
    
    def test_query_official_handles_package_not_found(self, mocker):
        mock_response = Mock()
        search_html = arch_poller.create_mocked_arch_search_html("nonexistent", found=False)
        mock_response.text = search_html
        mock_response.status_code = 200
        
        mocker.patch('poll_archlinux_builds.requests.get', return_value=mock_response)
        
        result = arch_poller.query_archlinux_api("nonexistent")
        assert result is None
    
    def test_query_official_handles_network_error(self, mocker):
        import requests
        
        mocker.patch('poll_archlinux_builds.requests.get', side_effect=requests.exceptions.ConnectionError())
        
        result = arch_poller.query_archlinux_api("hip")
        assert result is None


class TestAURAPIQuerying:
    """Test suite for Arch User Repository queries via AUR API."""
    
    def test_query_aur_finds_package_exists(self, mocker):
        def mock_get(*args, **kwargs):
            base_url = args[0] if args else ""
            
            if "archlinux.org/packages/search" in base_url:
                return Mock(status_code=404)
            else:
                aur_mock = Mock()
                aur_mock.json.return_value = arch_poller.ARCHLINUX_AUR_API_SUCCESS
                aur_mock.status_code = 200
                return aur_mock
        
        mocker.patch('poll_archlinux_builds.requests.get', side_effect=mock_get)
        
        result = arch_poller.query_archlinux_api("hip")
        
        assert result is not None


class TestArchPackageMatrixGeneration:
    """Test suite for ArchLinux-specific package mapping."""
    
    def test_generates_mapping_for_all_tracked_arch_packages(self):
        matrix = arch_poller.generate_arch_test_matrix()
        
        assert isinstance(matrix, list)
        assert len(matrix) == len(arch_poller.TRACKED_ARCH_PACKAGES)
    
    def test_includes_hip_test_directory_mapping(self):
        matrix = arch_poller.generate_arch_test_matrix()
        
        hip_entry = next((p for p in matrix if p['package_name'] == 'hip'), None)
        
        assert hip_entry is not None


class TestArchErrorHandling:
    """Test error handling scenarios specific to ArchLinux poller."""
    
    def test_handles_missing_aur_endpoint(self, mocker):
        import requests
        
        def mock_get(*args, **kwargs):
            base_url = args[0] if args else ""
            
            if "archlinux.org/packages/search" in base_url:
                return Mock(status_code=500)
            elif "rpc?v=5" in base_url:
                raise Exception("AUR endpoint failed")
            else:
                pass
            
        mocker.patch('poll_archlinux_builds.requests.get', side_effect=mock_get)
        
        result = arch_poller.query_archlinux_api("hip")
        assert result is None


class TestArchIntegrationFlow:
    """Integration tests simulating complete Arch polling workflow."""
    
    def test_detects_new_arch_version(self, mocker):
        mock_response = Mock()
        new_version_html = arch_poller.create_mocked_arch_search_html("hip", found=True).replace(
            "5.7.0", "5.8.1"
        )
        
        mock_response.text = new_version_html
        mock_response.status_code = 200
        
        mocker.patch('poll_archlinux_builds.requests.get', return_value=mock_response)
        
        new_version_detected = arch_poller.query_archlinux_api("hip")
        assert new_version_detected is not None


class TestArchHelperFunctions:
    """Test ArchLinux-specific utility functions."""
    
    def test_create_mocked_arch_search_html_found(self):
        html = arch_poller.create_mocked_arch_search_html("hyp", found=True)
        
        assert "hyp" in html.lower()
    
    def test_create_mocked_arch_search_html_not_found(self):
        html = arch_poller.create_mocked_arch_search_html("nonexistent", found=False)
        
        assert len(html) > 0


class TestAURSpecificBehavior:
    """Test specific behaviors of AUR package detection."""
    
    def test_aur_version_format_preserves_numeric_components(self, mocker):
        aur_mock = Mock()
        result_resp = {
            "resultcount": 1,
            "results": [{
                "Name": "hip",
                "Version": "5.7.0-2",
                "NumVotes": "400"
            }]
        }
        
        aur_mock.json.return_value = result_resp
        
        def mock_get(*args, **kwargs):
            return aur_mock
        
        mocker.patch('poll_archlinux_builds.requests.get', side_effect=mock_get)
        
        result = arch_poller.query_archlinux_api("hip")
        
        assert "5.7.0-2" in str(result.get("version", ""))


ARCH_STATE_PATH = arch_poller.DEFAULT_STATE_FILE

