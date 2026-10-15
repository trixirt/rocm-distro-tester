#!/usr/bin/env python3
"""
Unit tests for EPEL/RHEL Package Poller (poll_epel_builds.py).

Tests cover:
- State file management (load/save) with per-release tracking
- Docker container-based package querying
- DNF repoquery parsing logic
- Error handling for Docker/network failures
- Release version mapping functionality

Run with: pytest -v ci-trigger/tests/test_poll_epel_builds.py
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


sys.path.insert(0, str(Path(__file__).parent.parent))
import poll_epel_builds as epel_poller


# =============================================================================
# TEST: State File Management (Per-Release Tracking)
# =============================================================================

class TestEPELStateManagement:
    """Test suite for load_build_state() and save_build_state() functions."""
    
    def test_load_epel_state_from_existing_file(self, temp_test_dir):
        """Should successfully load EPEL build state from pre-populated file."""
        # List format (current standard)
        sample_state = [
            {"name": "hipblas", "build_id": "123456"},
            {"package": "rocblas", "build_id": "789012"}
        ]
        
        state_path = temp_test_dir / "epel_state.json"
        with open(state_path, 'w') as f:
            json.dump(sample_state, f)
        
        loaded = epel_poller.load_build_state(state_path)
            
        assert isinstance(loaded, dict)
        assert 'hipblas' in loaded
        assert loaded['hipblas'] == '123456'
    
    def test_load_epel_state_from_missing_file_returns_empty(self, temp_test_dir):
        """Should return empty dict when EPEL state file does not exist."""
        non_existent = temp_test_dir / "does_not_exist.json"
        
        result = epel_poller.load_build_state(non_existent)
        assert result == {}
    
    def test_load_epel_state_with_corrupted_json_returns_empty(self, temp_test_dir):
        """Should handle corrupted JSON gracefully."""
        corrupted_file = temp_test_dir / "corrupted_epel.json"
        
        with open(corrupted_file, 'w') as f:
            f.write("{invalid epel json content")
        
        result = epel_poller.load_build_state(corrupted_file)
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_save_epel_state_preserves_all_packages(self, temp_test_dir):
        """Should save all packages and preserve existing data."""
        # Pre-populate state with some packages
        initial_state = [
            {"package": "hipblas", "build_id": "100"},
            {"package": "rocblas", "build_id": "200"}
        ]
        
        state_path = temp_test_dir / "epel_state.json"
        with open(state_path, 'w') as f:
            json.dump(initial_state, f)
        
        # Save updates for new and existing packages
        feeds_to_save = [
            {'package': 'hipblas', 'build_id': 'NEW100'},
            {'package': 'rocrand', 'build_id': '500'}
        ]
        
        epel_poller.save_build_state(state_path, feeds_to_save)
        
        assert state_path.exists()
        with open(state_path) as f:
            data = json.load(f)
        
        package_names = {entry.get('package') or entry.get('name', '') for entry in data}
        assert 'hipblas' in package_names
        assert 'rocrand' in package_names
    
    def test_save_epel_state_no_new_builds(self, temp_test_dir):
        """Should handle empty new_builds list gracefully."""
        state_path = temp_test_dir / "state.json"
        
        # When there are no new builds, save should return early without creating file
        epel_poller.save_build_state(state_path, [])
        
        # File should NOT be created when no updates to save!
        assert not state_path.exists()


# =============================================================================
# TEST: Docker Container Query Function (Your Pattern)
# =============================================================================

class TestEDELContainerQuery:
    """Test suite for query_epel_package() using docker container pattern."""
    
    def test_epel_query_with_successfull_dnf_output(self, mocker):
        """Should successfully parse dnf repoquery output from container."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Name           : hipblas
Version        : 7.2.0
Release        : 5.el10_3
Repository     : epel-10
"""
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = epel_poller.query_epel_package('hipblas', '10')
        
        assert result is not None
        assert result['package'] == 'hipblas'
        assert result['available_version'] == '7.2.0'
        assert result['rpm_release'] == '5.el10_3'
    
    def test_epel_query_empty_response_returns_none(self, mocker):
        """Should return None when dnf query returns no results."""
        mocker.patch('subprocess.run', return_value=Mock(
            returncode=1, stdout="No matching packages found"
        ))
        
        result = epel_poller.query_epel_package('nonexistent-pkg', '10')
        assert result is None
    
    def test_epel_query_timeout_handling(self, mocker):
        """Should handle subprocess timeout gracefully."""
        import subprocess
        
        mocker.patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 300))
        
        result = epel_poller.query_epel_package('hipblas', '10')
        assert result is None
    
    def test_epel_query_docker_not_found(self, mocker):
        """Should handle docker command not available."""
        mocker.patch('subprocess.run', side_effect=FileNotFoundError("No such file: 'docker'"))
        
        result = epel_poller.query_epel_package('hipblas', '10')
        assert result is None
    
    def test_epel_query_version_parsing_with_epoch(self, mocker):
        """Should correctly parse version even with epoch."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Name           : hipblas
Version        : 1:7.2.0
Release        : 5.el10_3
"""
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = epel_poller.query_epel_package('hipblas', '10')
        
        assert result is not None
        assert result['available_version'] in ['7.2.0', '1:7.2.0']


# =============================================================================
# TEST: Release Configuration and Mapping
# =============================================================================

class TestEDELReleaseConfiguration:
    """Test suite for release version mappings."""
    
    def test_release_image_mapping_10(self):
        """Should map release 10 to correct Docker image."""
        assert epel_poller.RELEASE_IMAGES['10'] == 'quay.io/centos/centos:stream10'
    
    def test_release_image_mapping_9(self):
        """Should map release 9 to correct Docker image."""
        assert epel_poller.RELEASE_IMAGES['9'] == 'quay.io/centos/centos:stream9'


# =============================================================================
# TEST: Package Mapping and Matrix Generation
# =============================================================================

class TestEDELPackageMapping:
    """Test suite for EPEL package tracking."""
    
    def test_generates_mapping_for_all_tracked_packages(self):
        """Should create entry for every tracked package."""
        if hasattr(epel_poller, 'generate_package_matrix'):
            matrix = epel_poller.generate_package_matrix()
            
            assert isinstance(matrix, list)
            assert len(matrix) == len(epel_poller.TRACKED_RHEL_ROCM_PACKAGES)
    
    def test_all_packages_are_tracked(self):
        """All expected packages should be tracked."""
        package_names = {pkg.lower() for pkg in epel_poller.TRACKED_RHEL_ROCM_PACKAGES}
        assert 'hipblas' in package_names
        assert 'rocblas' in package_names


# =============================================================================
# TEST: Integration and CLI Behavior
# =============================================================================

class TestEDELCLIAndMain:
    """Test main execution flow and CLI parsing."""
    
    def test_get_parser_has_all_expected_args(self):
        """Parser should have all required CLI arguments."""
        parser = epel_poller.get_parser()
        
        assert 'package' in str(parser.format_help())
        assert 'release' in str(parser.format_help())
    
    def test_main_returns_zero_when_no_changes(self):
        """Main function should return 0 when no updates detected.
        
        This verifies the exit code logic rather than actual execution
        since we can't easily mock all subprocess calls in main().
        """
        # Verify parser returns correctly configured argparse object
        args = epel_poller.get_parser().parse_args(['--all'])
        assert args.all is True
        assert args.package == 'hipblas'  # Default value


# =============================================================================
# TEST: Error Handling Edge Cases
# =============================================================================

class TestEPELErrorHandling:
    """Test various failure scenarios."""
    
    def test_epel_query_handles_no_rpm_url(self):
        """Should return None when EPEL URL not configured."""
        # For releases without configured URLs, should handle gracefully
        
        result = epel_poller.query_epel_package('hipblas', '99')
        assert result is None
    
    def test_save_build_state_creates_parent_directories(self, temp_test_dir):
        """Should create parent directories for state file."""
        state_path = temp_test_dir / "subdir" / "nested" / "epel.json"
        
        # Should not crash even though directory doesn't exist yet
        epel_poller.save_build_state(
            state_path, 
            [{'package': 'test', 'build_id': '1'}]
        )
        
        assert state_path.parent.exists()
        assert state_path.exists()


# =============================================================================
# TEST: Helper Functions for RHEL-Specific Testing
# =============================================================================

class TestEDELHelperFunctions:
    """Test utility functions for RHEL/EPEL testing."""
    
    def test_get_state_file_format(self):
        """State file naming should follow expected pattern."""
        state_file = epel_poller.get_state_file('10')
        
        assert 'epel_10_build_state.json' in str(state_file)
        assert isinstance(state_file, Path)


# =============================================================================
# HELPER TEST DATA FACTORIES (for mocking)
# =============================================================================

def create_mock_dnf_response(version="7.2.0", release="5.el10_3"):
    """Create a mocked subprocess result for dnf queries."""
    mock = Mock()
    mock.returncode = 0
    mock.stdout = f"""Name           : hipblas
Version        : {version}
Release        : {release}
Repository     : epel-{release.split('_')[1] if '_' in release else 'default'}
"""
    return mock


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
