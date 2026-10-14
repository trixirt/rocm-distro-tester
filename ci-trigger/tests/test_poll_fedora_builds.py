#!/usr/bin/env python3
"""
Unit tests for fedora package build poller (poll_fedora_builds.py).

Tests cover:
- State file management (load/save)  
- Koji API response parsing
- Package detection and tracking logic
- Error handling for malformed responses
- Integration test flow simulation

Run with: pytest -v ci-trigger/tests/test_poll_fedora_builds.py
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parent.parent))

import poll_fedora_builds as fedora_poller


class TestBuildStateManagement:
    """Test suite for load_build_state() and save_build_state() functions."""
    
    def test_load_state_from_existing_file(self, temp_test_dir):
        """Should successfully load state from a pre-populated file."""
        sample_state = [{"name": "hipblas", "last_build_id": "123456"}]
        
        with open(Path(temp_test_dir) / "test_state.json", 'w') as f:
            json.dump(sample_state, f)
        
        loaded = fedora_poller.load_build_state(Path(temp_test_dir) / "test_state.json")
            
        assert isinstance(loaded, dict)
        assert 'hipblas' in loaded
    
    def test_load_state_from_missing_file_returns_empty(self, temp_test_dir):
        """Should return empty dict when state file does not exist."""
        non_existent = Path(temp_test_dir) / "does_not_exist.json"
        
        result = fedora_poller.load_build_state(non_existent)
        assert result == {}
    
    def test_load_state_with_corrupted_json_returns_empty(self, temp_test_dir):
        """Should handle corrupted JSON gracefully."""
        corrupted_file = Path(temp_test_dir) / "corrupted.json"
        
        with open(corrupted_file, 'w') as f:
            f.write("{invalid json content")
        
        result = fedora_poller.load_build_state(corrupted_file)
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_save_state_to_file(self, temp_test_dir):
        """Should successfully save build state to disk."""
        sample_builds = [
            {'package': 'hipblas', 'last_build_id': '555666'},
            {'package': 'rocblas', 'last_build_id': '777888'}
        ]
        
        fedora_poller.DEFAULT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state_path = Path(temp_test_dir) / "saved.json"
        
        from pathlib import Path as P
        fedora_poller.save_build_state(state_path, sample_builds)
        
        assert state_path.exists()
        with open(state_path) as f:
            data = json.load(f)
        
        assert len(data) == 2


class TestKojiAPIQuerying:
    """Test suite for query_fedora_koji_api() function."""
    
    def test_query_finds_package_name_exact_match(self, mocker):
        """Should identify package when name matches exactly."""
        mock_response = Mock()
        mock_response.status_code = 200
        # API returns dict with "packages" key containing the list
        mock_response.json.return_value = {
            'packages': [
                {'name': 'hipblas', 'latest_builds': [{'task_id': 123456, 'version': '5.7.0'}]}
            ]
        }
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result = fedora_poller.query_fedora_koji_api('hipblas')
        
        assert result is not None
        assert result['package'] == 'hipblas'
        assert str(result['build_id']) == '123456'
    
    def test_query_handles_package_not_found(self, mocker):
        """Should return None when package does not exist in Koji."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'packages': []}
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result = fedora_poller.query_fedora_koji_api('nonexistent_pkg')
        assert result is None
    
    def test_query_handles_network_error(self, mocker):
        """Should handle network request exceptions gracefully."""
        import requests
        
        mocker.patch('poll_fedora_builds.requests.get', side_effect=requests.exceptions.ConnectionError())
        
        result = fedora_poller.query_fedora_koji_api('hipblas')
        assert result is None
    
    def test_query_handles_empty_latest_builds(self, mocker):
        """Should handle packages with no builds (edge case)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'packages': [
                {'name': 'rocblas', 'latest_builds': []}
            ]
        }
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result = fedora_poller.query_fedora_koji_api('rocblas')
        assert result is None
    
    def test_query_differentiates_legacy_and_new_format(self, mocker):
        """Should handle both new dict format and legacy list format."""
        mock_response = Mock()
        mock_response.status_code = 200
        # Simulate legacy format being returned in packages array
        legacy_data = [
            {'name': 'rocblas', 'latest_builds': [{'task_id': 999888}]},
            {'name': 'hipfft', 'latest_builds': [{'task_id': 777666}]}
        ]
        mock_response.json.return_value = {'packages': legacy_data}
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result = fedora_poller.query_fedora_koji_api('rocblas')
        
        assert result is not None
        assert str(result['build_id']) == '999888'


class TestPackageMatrixGeneration:
    """Test suite for generate_package_mapping() function."""
    
    def test_generates_mapping_for_all_tracked_packages(self):
        """Should create mapping entry for every tracked package."""
        matrix = fedora_poller.generate_package_matrix()
        
        assert isinstance(matrix, list)
        assert len(matrix) == len(fedora_poller.TRACKED_ROCM_PACKAGES)
    
    def test_includes_hipblas_test_directory_mapping(self):
        """Should map hipblas package to correct test directory."""
        matrix = fedora_poller.generate_package_matrix()
        
        hipblas_entry = next((p for p in matrix if p['package_name'] == 'hipblas'), None)
        
        assert hipblas_entry is not None
        assert hipblas_entry['test_dir'] == 'hipblas'
    
    def test_all_entries_have_required_fields(self):
        """Each package mapping should have expected structure."""
        matrix = fedora_poller.generate_package_matrix()
        
        required_fields = {'package_name', 'package_display', 'test_dir'}
        
        for entry in matrix:
            assert set(entry.keys()).issuperset(required_fields)


class TestErrorHandling:
    """Test error handling scenarios across the poller module."""
    
    def test_handles_missing_koji_endpoint(self, mocker):
        """Should handle Koji API endpoint changes gracefully."""
        import requests
        
        # Use raises to simulate exception properly
        mock_request = Mock(side_effect=requests.exceptions.RequestException("Endpoint not found"))
        
        with patch.object(fedora_poller.requests, 'get', mock_request):
            result = fedora_poller.query_fedora_koji_api('hipblas')
            assert result is None
    
    def test_handles_malformed_builds_field(self, mocker):
        """Should handle missing or malformed latest_builds field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'packages': [{'name': 'hipfft'}]}
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result = fedora_poller.query_fedora_koji_api('hipfft')
        assert result is None
    
    def test_handles_none_in_latest_builds(self, mocker):
        """Should handle None values in builds array gracefully."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'packages': [
                {'name': 'rocrand', 'latest_builds': [None]}
            ]
        }
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result = fedora_poller.query_fedora_koji_api('rocrand')
        assert result is None


class TestAPIParsingDetails:
    """Test specific parsing behavior of Koji response formats."""
    
    def test_parses_version_from_modern_format(self, mocker):
        """Should correctly extract version from modern build format."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'packages': [
                {'name': 'rokprime', 'latest_builds': [{'task_id': 555666, 'version': '9.0.0'}]}
            ]
        }
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result = fedora_poller.query_fedora_koji_api('rokprime')
        assert result['version'] == '9.0.0'
    
    def test_normalizes_package_names_case_insensitive(self, mocker):
        """Should match packages regardless of case."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'packages': [
                {'name': 'HIPBLAS', 'latest_builds': [{'task_id': 111222, 'version': '5.7.0'}]}
            ]
        }
        
        mocker.patch('poll_fedora_builds.requests.get', return_value=mock_response)
        
        result_lower = fedora_poller.query_fedora_koji_api('hipblas')
        result_upper = fedora_poller.query_fedora_koji_api('HIPBLAS')
        
        assert result_lower['build_id'] == '111222'
        assert result_upper['build_id'] == '111222'


FEDED_STATE_PATH = fedora_poller.DEFAULT_STATE_FILE

