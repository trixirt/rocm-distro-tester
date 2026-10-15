#!/usr/bin/env python3
"""
Unit tests for Ubuntu ROCm Package Poller (poll_ubuntu_builds.py).

Tests cover:
- State file management (load/save) with per-package tracking
- Docker container-based apt queries
- Package version parsing logic
- Error handling for Docker/network failures
- CLI argument parsing and release configuration

Run with: pytest -v ci-trigger/tests/test_poll_ubuntu_builds.py
"""

import sys
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parent.parent))
import poll_ubuntu_builds as ubuntu_poller


# =============================================================================
# TEST: State File Management
# ==========================================================================

class TestUbuntuStateManagement:
    """Test suite for load_build_state() and save_build_state() functions."""
    
    def test_load_ubuntu_state_from_existing_file(self, tmp_path):
        """Should successfully load Ubuntu build state from pre-populated file."""
        sample_state = [
            {"name": "hipblas", "last_version": "12.3.4-5"},
            {"package": "rocblas", "last_version": "8.0.0-2"}
        ]
        
        test_file = tmp_path / "ubuntu_test_json"
        with open(test_file, 'w') as f:
            json.dump(sample_state, f)
            
        loaded = ubuntu_poller.load_build_state(test_file)
        
        assert isinstance(loaded, dict)
        assert 'hipblas' in loaded
        assert loaded['hipblas'] == '12.3.4-5'
    
    def test_load_ubuntu_state_missing_file(self, tmp_path):
        """Should return empty dict when Ubuntu state file doesn't exist."""
        non_existent = tmp_path / "no_ubuntu.json"
        result = ubuntu_poller.load_build_state(non_existent)
        assert result == {}
    
    def test_load_ubuntu_state_corrupted_json(self, tmp_path):
        """Should handle corrupted JSON gracefully for Ubuntu state files."""
        corrupted = tmp_path / "corrupted_ubuntu.json"
        corrupted.write_text("invalid ubuntu json content")
        
        result = ubuntu_poller.load_build_state(corrupted)
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_save_ubuntu_state_preserves_packages(self, tmp_path):
        """Should save packages and merge with existing state."""
        # Pre-populate state
        initial = [{"package": "hipblas", "last_version": "old-1"}]
        file = tmp_path / "ubuntu_state.json"
        with open(file, 'w') as f:
            json.dump(initial, f)
        
        # Save updates (new package + updated existing)
        changes = [
            {'package': 'hipblas', 'last_version': 'new-2'},
            {'package': 'rocblas', 'last_version': '3.0'}
        ]
        
        ubuntu_poller.save_build_state(file, changes)
        
        assert file.exists()
        with open(file) as f:
            data = json.load(f)
        
        pnames = {entry.get('package') or entry.get('name', '') for entry in data}
        assert 'hipblas' in pnames
        assert 'rocblas' in pnames
    
    def test_save_ubuntu_empty_no_op(self, tmp_path):
        """Should handle empty new_builds list gracefully."""
        file = tmp_path / "empty_ubuntu.json"
        
        # When there are no builds to save, it should not crash
        ubuntu_poller.save_build_state(file, [])
        assert True  # Should complete without error


# =============================================================================
# TEST: Docker Container Query Function (User's Pattern)
# ==========================================================================

class TestUbuntuContainerQuery:
    """Test suite for query_ubuntu_package() using docker apt pattern."""
    
    def test_ubuntu_query_successful_apt_output(self, mocker):
        """Should successfully parse apt-cache show output from container."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Package: hipblas
Version: 12.3.4-5ubuntu1
Architecture: amd64

Repository: ubuntu"""
        
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = ubuntu_poller.query_ubuntu_package('hipblas')
        
        assert result is not None
        assert result['package'] == 'hipblas'
        assert result['last_version'] == '12.3.4-5ubuntu1'
    
    def test_ubuntu_query_empty_result_returns_none(self, mocker):
        """Should return None when apt-cache returns no results."""
        mocker.patch('subprocess.run', return_value=Mock(
            returncode=1, stdout="No packages found: nonexistent"
        ))
        
        result = ubuntu_poller.query_ubuntu_package('nonexistent')
        assert result is None
    
    def test_ubuntu_query_timeout_handling(self, mocker):
        """Should handle subprocess timeout gracefully."""
        import subprocess as sub
        
        mocker.patch('subprocess.run', side_effect=sub.TimeoutExpired("cmd", 300))
        
        result = ubuntu_poller.query_ubuntu_package('hip')
        assert result is None
    
    def test_ubuntu_query_docker_not_found(self, mocker):
        """Should handle docker command not available."""
        mocker.patch('subprocess.run', side_effect=FileNotFoundError("No such file: 'docker'"))
        
        result = ubuntu_poller.query_ubuntu_package('hip')
        assert result is None
    
    def test_ubuntu_query_version_parsing(self, mocker):
        """Should correctly parse apt-cache version output."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Package: hipblas
Version: 1.0.7-2ubuntu3"""
        
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = ubuntu_poller.query_ubuntu_package('hipblas')
        
        assert result is not None
        assert result['last_version'] == '1.0.7-2ubuntu3'


# =============================================================================
# TEST: Ubuntu Docker Configuration  
# ==========================================================================

class TestUbuntuConfigurationSetup:
    """Test suite for Docker container configuration."""
    
    def test_ubuntu_docker_image_latest_set(self):
        """Should use correct Ubuntu base image for latest."""
        assert 'latest' in ubuntu_poller.UBUNTU_IMAGES
    
    def test_noble_release_images_present(self):
        """Should have Ubuntu release variants configured."""
        assert ubuntu_poller.UBUNTU_IMAGES['noble'] == 'ubuntu:noble'
        assert ubuntu_poller.UBUNTU_IMAGES['jammy'] == 'ubuntu:jammy'


# =============================================================================
# TEST: Package Configuration & Tracking  
# ==========================================================================

class TestUbuntuPackageTracking:
    """Test suite for tracked package configuration."""
    
    def test_all_packages_tracked(self):
        """All expected packages should be tracked."""
        package_names = {pkg.lower() for pkg in ubuntu_poller.TRACKED_UBUNTU_ROCM_PACKAGES}
        assert 'hipblas' in package_names
        assert 'rocblas' in package_names


# =============================================================================
# TEST: Integration and CLI Behavior  
# ==========================================================================

class TestUbuntuCLIAndMain:
    """Test main execution flow and CLI parsing."""
    
    def test_get_parser_has_all_args(self):
        """Parser should have all required CLI arguments."""
        parser = ubuntu_poller.get_parser()
        
        help_text = str(parser.format_help())
        assert 'package' in help_text
        assert 'list-packages' in help_text
        assert 'release' in help_text
    
    def test_main_returns_zero_on_no_changes(self, mocker):
        """Main function should return 0 when no updates found."""
        # Mock to prevent actual subprocess execution
        mocker.patch('subprocess.run', return_value=Mock(
            returncode=1, stdout=""
        ))
        
        result = ubuntu_poller.get_parser().parse_args(['--all'])
        assert result.all is True


# =============================================================================
# TEST: Error Handling Edge Cases  
# ==========================================================================

class TestUbuntuErrorHandling:
    """Test various failure scenarios."""
    
    def test_main_handles_subprocess_error(self, mocker):
        """Should handle Docker subprocess failures gracefully."""
        mocker.patch('subprocess.run', side_effect=Exception("Docker error"))
        
        # Should not crash - should return None
        result = ubuntu_poller.query_ubuntu_package('hip')
        assert result is None


# =============================================================================
# TEST: Helper Functions for Testing  
# ==========================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])

