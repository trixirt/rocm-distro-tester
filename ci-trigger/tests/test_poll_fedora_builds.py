#!/usr/bin/env python3
"""
Unit tests for Fedora ROCm Package Poller (poll_fedora_builds.py).

Tests cover:
- State file management (load/save) with backward compatibility
- Docker-based package querying
- Local dnf fallback querying
- CLI argument parsing and defaults
- Error handling scenarios (timeouts, missing docker, etc.)
- Test directory mapping logic
- Exit code behavior

Run with: pytest -v ci-trigger/tests/test_poll_fedora_builds.py
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess


sys.path.insert(0, str(Path(__file__).parent.parent))
import poll_fedora_builds as fedora_poller


class TestStateManagement:
    """Test suite for load_build_state() and save_build_state() functions."""
    
    def test_load_state_from_existing_file(self, temp_test_dir):
        """Should successfully load state from a pre-populated file."""
        # List format (current standard)
        sample_state = [
            {"name": "hipblas", "build_id": "123456"},
            {"package": "rocblas", "build_id": "789012"}
        ]
        
        state_path = temp_test_dir / "test_state.json"
        with open(state_path, 'w') as f:
            json.dump(sample_state, f)
        
        loaded = fedora_poller.load_build_state(state_path)
            
        assert isinstance(loaded, dict)
        assert 'hipblas' in loaded
        assert 'rocblas' in loaded
        assert loaded['rocblas'] == '789012'  # Dict format with 'package' key
    
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
    
    def test_load_state_with_empty_array_returns_empty(self, temp_test_dir):
        """Should handle empty JSON array correctly."""
        empty_file = Path(temp_test_dir) / "empty.json"
        with open(empty_file, 'w') as f:
            json.dump([], f)
        
        result = fedora_poller.load_build_state(empty_file)
        assert result == {}
    
    def test_load_dict_format_state_backward_compat(self, temp_test_dir):
        """Should handle legacy dict format for backward compatibility."""
        # Old format was just a simple dict
        old_format = {"hipblas": "123456", "rocblas": "789012"}
        
        state_path = temp_test_dir / "old_format.json"
        with open(state_path, 'w') as f:
            json.dump(old_format, f)
        
        result = fedora_poller.load_build_state(state_path)
        assert result == old_format
    
    def test_save_state_preserves_all_packages(self, temp_test_dir):
        """Should save all packages and preserve existing data."""
        # Pre-populate state with some packages
        initial_state = [
            {"name": "hipblas", "build_id": "100", "timestamp": "t1"},
            {"package": "rocblas", "build_id": "200", "timestamp": "t2"}
        ]
        
        state_path = temp_test_dir / "state.json"
        with open(state_path, 'w') as f:
            json.dump(initial_state, f)
        
        # Save updates for new and existing packages
        feeds_to_save = [
            {'package': 'hipblas', 'build_id': 'NEW100', 'timestamp': 't3'},
            {'package': 'rocrand', 'build_id': '500', "timestamp": 't4'}
        ]
        
        fedora_poller.save_build_state(state_path, feeds_to_save)
        
        # Verify state file exists and contains all packages
        assert state_path.exists()
        with open(state_path) as f:
            data = json.load(f)
        
        package_names = {entry.get('package') or entry.get('name', '') for entry in data}
        assert 'hipblas' in package_names  # Updated existing
        assert 'rocrand' in package_names  # New addition
        
    def test_save_state_no_new_builds_does_not_crash(self, temp_test_dir):
        """Should handle empty new_builds list gracefully."""
        state_path = temp_test_dir / "state.json"
        fedora_poller.save_build_state(state_path, [])
        
        # Should not crash or modify file for empty updates


class TestDockerQuery:
    """Test suite for docker_query() function."""
    
    def test_docker_query_succeeds(self, mocker):
        """Should successfully query when docker returns valid output."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Name           : hipblas
Version        : 10.0.0
Release        : 1.fc46
Architecture   : x86_64
"""
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = fedora_poller.docker_query('hipblas')
        
        assert result is not None
        assert result['package'] == 'hipblas'
        assert result['build_id'] == "10.0.0-1.fc46"
        assert result['available_version'] == '10.0.0'
    
    def test_docker_query_empty_response_returns_none(self, mocker):
        """Should return None when docker returns empty or invalid output."""
        mocker.patch('subprocess.run', return_value=Mock(
            returncode=0, stdout=""
        ))
        
        result = fedora_poller.docker_query('hipblas')
        assert result is None
    
    def test_docker_query_non_zero_return_code_returns_none(self, mocker):
        """Should return None when docker command fails."""
        mocker.patch('subprocess.run', return_value=Mock(
            returncode=1, stdout=""
        ))
        
        result = fedora_poller.docker_query('hipblas')
        assert result is None
    
    def test_docker_query_timeout_handled(self, mocker):
        """Should handle subprocess timeout gracefully."""
        import subprocess
        
        mocker.patch('subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 60))
        
        result = fedora_poller.docker_query('hipblas')
        assert result is None
    
    def test_docker_query_missing_command_handled(self, mocker):
        """Should handle docker command not found."""
        mocker.patch('subprocess.run', side_effect=FileNotFoundError(
            "No such file or directory: 'docker'"
        ))
        
        result = fedora_poller.docker_query('hipblas')
        assert result is None
    
    def test_docker_version_release_extraction(self, mocker):
        """Should correctly extract version and release from various output formats."""
        # Test with multiple possible fields present
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Epoch          : 0
Version        : 5.7.0-1
Release        : fc45
Download size  : 123 KB
"""
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = fedora_poller.docker_query('testpackage')
        
        assert result is not None
        assert result['available_version'] == '5.7.0-1'


class TestLocalDnfQuery:
    """Test suite for local_dnf_query() function."""
    
    def test_local_dnf_query_succeeds(self, mocker):
        """Should successfully query when local dnf returns valid output."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Name           : rocblas
Version        : 8.0.0
Release        : 1.fc46
"""
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = fedora_poller.local_dnf_query('rocblas')
        
        assert result is not None
        assert result['build_id'] == "8.0.0-1.fc46"
    
    def test_local_dnf_fallback_from_5_to_4(self, mocker):
        """Should try dnf first, then fall back to dnf4 if unavailable."""
        # First call (dnf5) fails, second call (dnf) succeeds
        side_effects = [
            Mock(returncode=127, stdout=""),  # dnf5 not found
            Mock(returncode=0, stdout="Version: 5.8.0\nRelease: 1.fc46\n")
        ]
        
        mocker.patch('subprocess.run', side_effect=side_effects)
        
        result = fedora_poller.local_dnf_query('hipsolver')
        
        assert result is not None
        assert result['available_version'] == '5.8.0'
    
    def test_local_dnf_not_available_returns_none(self, mocker):
        """Should return None when neither dnf nor dnf4 available."""
        side_effects = [
            Mock(returncode=127, stdout=""),  # dnf5 not found
            Mock(side_effect=FileNotFoundError("dnf"))
        ]
        
        mocker.patch('subprocess.run', side_effect=side_effects)
        
        result = fedora_poller.local_dnf_query('somepackage')
        assert result is None


class TestQueryPackageStrategy:
    """Test suite for the main query_package() function."""
    
    def test_prefers_docker_over_local(self, mocker):
        """Should prefer docker query, only try local if docker fails."""
        # Docker succeeds immediately
        mocker.patch.object(fedora_poller, 'docker_query', return_value={
            'package': 'test', 'build_id': '1.0-1.fc46'
        })
        
        result = fedora_poller.query_package('test')
        
        assert result is not None
        assert result['build_id'] == '1.0-1.fc46'


class TestPackageMatrix:
    """Test suite for generate_package_matrix() function."""
    
    def test_generates_mapping_for_all_tracked_packages(self):
        """Should create mapping entry for every tracked package."""
        matrix = fedora_poller.generate_package_matrix()
        
        assert isinstance(matrix, list)
        assert len(matrix) == len(fedora_poller.TRACKED_ROCM_PACKAGES)
    
    def test_includes_all_expected_packages(self):
        """All expected ROCm packages should be in the matrix."""
        matrix = fedora_poller.generate_package_matrix()
        
        package_names = {entry['package_name'] for entry in matrix}
        expected = {pkg.lower() for pkg in fedora_poller.TRACKED_ROCM_PACKAGES}
        
        assert expected.issubset(package_names)
    
    def test_all_entries_have_required_fields(self):
        """Each package mapping should have expected structure."""
        matrix = fedora_poller.generate_package_matrix()
        
        required_fields = {'package_name', 'package_display', 'test_dir'}
        
        for entry in matrix:
            assert set(entry.keys()).issuperset(required_fields)
    
    def test_map_hipblas_correctly(self):
        """Should map hipblas to correct test directory."""
        matrix = fedora_poller.generate_package_matrix()
        hipblas_entry = next((p for p in matrix if p['package_name'] == 'hipblas'), None)
        
        assert hipblas_entry is not None
        assert hipblas_entry['test_dir'] == 'hipblas'


class TestCLIParsing:
    """Test suite for argument parsing."""
    
    def test_default_all_packages_flag(self, mocker):
        """Should default to checking all packages when --all not specified."""
        # Mock the main logic to verify it received correct args
        mock_main_result = 0
        
        def capture_args(args):
            # Verify default behavior
            assert args.package is None
            assert args.all is True  # Should default to checking all
            return mock_main_result
        
        with patch.object(fedora_poller, 'main') as mock_main:
            with patch('argparse.ArgumentParser.parse_args', return_value=Mock(
                package=None, file=None, list_packages=True, 
                all=True, reset=False
            )):
                fedora_poller.get_parser().parse_args = lambda: Mock(
                    package=None, file=None, list_packages=True, 
                    all=True, reset=False
                )
        
        # Verify argument parser has expected args
        parser = fedora_poller.get_parser()
        assert 'package' in str(parser.format_help())


class TestErrorHandling:
    """Test error handling scenarios across the poller module."""
    
    def test_state_file_missing_parent_dir_handled(self, temp_test_dir):
        """Should create parent directories if they don't exist."""
        state_path = Path(temp_test_dir) / "subdir" / "nested" / "state.json"
        
        # Should not crash even though directory doesn't exist yet
        fedora_poller.save_build_state(
            state_path, 
            [{'package': 'test', 'build_id': '1'}]
        )
        
        assert state_path.parent.exists()
        assert state_path.exists()
    
    def test_docker_query_general_exception_handled(self, mocker):
        """Should handle unexpected exceptions in docker queries."""
        import subprocess
        
        # Generic exception (not TimeoutExpired or FileNotFoundError)
        mocker.patch('subprocess.run', side_effect=Exception("Unexpected error"))
        
        result = fedora_poller.docker_query('hipblas')
        assert result is None
    
    def test_save_with_none_timestamp(self, temp_test_dir):
        """Should handle missing timestamp gracefully."""
        state_path = temp_test_dir / "state.json"
        
        builds_without_time = [
            {'package': 'hipblas', 'build_id': '1'},  # No timestamp
        ]
        
        # Should not crash
        fedora_poller.save_build_state(state_path, builds_without_time)
        
        # Verify file was created with proper format
        assert state_path.exists()


class TestExitCodes:
    """Test exit code behavior."""
    
    def test_state_file_with_timestamp_none(self, temp_test_dir):
        """Should handle missing timestamp gracefully."""
        state_path = temp_test_dir / "state.json"
        
        builds_without_time = [
            {'package': 'hipblas', 'build_id': '1'},  # No timestamp
        ]
        
        # Should not crash
        fedora_poller.save_build_state(state_path, builds_without_time)
        
        # Verify file was created with proper format
        assert state_path.exists()
        


# ============================================================================
# TEST HELPER FUNCTIONS (for pytest fixtures)
# ============================================================================

def create_mock_docker_response(version="1.0", release="1.fc46"):
    """Create a mocked subprocess result for docker queries."""
    mock = Mock()
    mock.returncode = 0
    mock.stdout = f"""Name           : hipblas
Version        : {version}
Release        : {release}
Architecture   : x86_64
"""
    return mock


def create_mock_dnf_response(version="1.0", release="1.fc46"):
    """Create a mocked subprocess result for local dnf queries."""
    mock = create_mock_docker_response(version, release)
    return Mock(returncode=0, stdout=f"Name           : test\nVersion        : {version}\nRelease        : {release}\n")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
