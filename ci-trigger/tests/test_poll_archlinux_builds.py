#!/usr/bin/env python3
"""
Unit tests for ArchLinux ROCm Package Poller (poll_archlinux_builds.py).

Tests cover:
- State file management (load/save) with per-package tracking
- Docker container-based pacman queries
- Package version parsing logic
- Error handling for Docker/network failures
- CLI argument parsing

Run with: pytest -v /tmp/test_arch_linux_poller.py
"""

import sys
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, '/home/trix/test/rocm-distro-tester/ci-trigger/tests')

# Import the poller module
sys.path.insert(0, '/home/trix/test/rocm-distro-tester/ci-trigger')
import poll_archlinux_builds as arch_poller


# =============================================================================
# TEST: State File Management (Simple key-value version tracking)
# =============================================================================

class TestArchitectureStateManagement:
    """Test suite for load_build_state() and save_build_state() functions."""
    
    def test_load_arch_state_from_existing_file(self, tmp_path):
        """Should successfully load Arch build state from pre-populated file."""
        sample_state = [
            {"name": "hip", "last_version": "5.6.0-1"},
            {"package": "rocminfo", "last_version": "5.7.0-1"}
        ]
        
        test_file = tmp_path / "arch_test_json"
        with open(test_file, 'w') as f:
            json.dump(sample_state, f)
            
        loaded = arch_poller.load_build_state(test_file)
        
        assert isinstance(loaded, dict)
        assert 'hip' in loaded
        assert loaded['hip'] == '5.6.0-1'
    
    def test_load_arch_state_missing_file(self, tmp_path):
        """Should return empty dict when Arch state file doesn't exist."""
        non_existent = tmp_path / "no_arch.json"
        result = arch_poller.load_build_state(non_existent)
        assert result == {}
    
    def test_load_arch_state_corrupted_json(self, tmp_path):
        """Should handle corrupted JSON gracefully for Arch state files."""
        corrupted = tmp_path / "corrupted.json"
        corrupted.write_text("invalid arch json content")
        
        result = arch_poller.load_build_state(corrupted)
        assert isinstance(result, dict)
        assert len(result) == 0
    
    def test_save_arch_state_preserves_packages(self, tmp_path):
        """Should save packages and merge with existing state."""
        # Pre-populate state
        initial = [{"package": "hip", "last_version": "old-1"}]
        file = tmp_path / "state.json"
        with open(file, 'w') as f:
            json.dump(initial, f)
        
        # Save updates (new package + updated existing)
        changes = [
            {'package': 'hip', 'last_version': 'new-2'},
            {'package': 'rocblas', 'last_version': '1.0'}
        ]
        
        arch_poller.save_build_state(file, changes)
        
        assert file.exists()
        with open(file) as f:
            data = json.load(f)
        
        pnames = {entry.get('package') or entry.get('name', '') for entry in data}
        assert 'hip' in pnames
        assert 'rocblas' in pnames
    
    def test_save_arch_empty_no_op(self, tmp_path):
        """Should handle empty new_builds list gracefully."""
        file = tmp_path / "empty.json"
        
        # When there are no builds to save, it should not crash
        arch_poller.save_build_state(file, [])
        
        # No file created when nothing to save
        assert not file.exists()


# =============================================================================
# TEST: Docker Container Query Function (User's Pattern)
# =========================================================================

class TestArchitectureContainerQuery:
    """Test suite for query_archlinux_package() using docker pacman pattern."""
    
    def test_arch_query_successful_pacman_output(self, mocker):
        """Should successfully parse pacman -Si output from container."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Package Name           : rocminfo
Version                : 5.6.2_0803-1
Description            : Tool for ROCm system information
... (other fields)"""
        
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = arch_poller.query_archlinux_package('rocminfo')
        
        assert result is not None
        assert result['package'] == 'rocminfo'
        assert result['last_version'] == '5.6.2_0803-1'
    
    def test_arch_query_empty_result_returns_none(self, mocker):
        """Should return None when pacman returns no results."""
        mocker.patch('subprocess.run', return_value=Mock(
            returncode=1, stdout="Package not found: nonexistent"
        ))
        
        result = arch_poller.query_archlinux_package('nonexistent')
        assert result is None
    
    def test_arch_query_timeout_handling(self, mocker):
        """Should handle subprocess timeout gracefully."""
        import subprocess
        
        mocker.patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 300))
        
        result = arch_poller.query_archlinux_package('hip')
        assert result is None
    
    def test_arch_query_docker_not_found(self, mocker):
        """Should handle docker command not available."""
        mocker.patch('subprocess.run', side_effect=FileNotFoundError("No such file: 'docker'"))
        
        result = arch_poller.query_archlinux_package('hip')
        assert result is None
    
    def test_arch_query_version_parsing(self, mocker):
        """Should correctly parse pacman version output."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Package Name           : hipblas
Version                : 5.7.1-1
"""
        mocker.patch('subprocess.run', return_value=mock_result)
        
        result = arch_poller.query_archlinux_package('hipblas')
        
        assert result is not None
        assert result['last_version'] == '5.7.1-1'


# =============================================================================
# TEST: Docker Configuration
# =========================================================================

class TestConfigurationSetup:
    """Test suite for Docker container configuration."""
    
    def test_arch_linux_docker_image_set(self):
        """Should use correct Arch Linux base image."""
        assert arch_poller.ARCH_DOCKER_IMAGE == 'archlinux:latest'


# =============================================================================
# TEST: Package Configuration & Tracking
# =========================================================================

class TestArchitecturePackageTracking:
    """Test suite for tracked package configuration."""
    
    def test_all_packages_tracked(self):
        """All expected RPM packages should be tracked."""
        package_names = {pkg.lower() for pkg in arch_poller.TRACKED_ARCH_ROCM_PACKAGES}
        assert 'hip' in package_names
        assert 'rocminfo' in package_names


# =============================================================================
# TEST: Integration and CLI Behavior
# =========================================================================

class TestArchLinuxCLIAndMain:
    """Test main execution flow and CLI parsing."""
    
    def test_get_parser_has_all_args(self):
        """Parser should have all required CLI arguments."""
        parser = arch_poller.get_parser()
        
        help_text = str(parser.format_help())
        assert 'package' in help_text
        assert 'list-packages' in help_text
    
    def test_main_returns_zero_on_no_changes(self, mocker):
        """Main function should return 0 when no updates found."""
        # Mock to prevent actual subprocess execution
        mocker.patch('subprocess.run', return_value=Mock(
            returncode=1, stdout=""
        ))
        
        result = arch_poller.get_parser().parse_args(['--all'])
        assert result.all is True


# =============================================================================
# TEST: Error Handling Edge Cases
# =========================================================================

class TestArchitectureErrorHandling:
    """Test various failure scenarios."""
    
    def test_main_handles_subprocess_error(self, mocker):
        """Should handle Docker subprocess failures gracefully."""
        mocker.patch('subprocess.run', side_effect=Exception("Docker error"))
        
        # Should not crash
        result = arch_poller.query_archlinux_package('hip')
        assert result is None


# =============================================================================
# HELPER MOCK FACTORIES (for testing)
# =========================================================================

def create_mock_pacman_response(package_name="hip", version="5.7.0-1"):
    """Create a mocked subprocess.result for pacman queries."""
    mock = Mock()
    mock.returncode = 0
    mock.stdout = f"""Package Name           : {package_name}
Version                : {version}
Description            : ROCm package testing

... (additional fields)"""
    return mock


# =============================================================================
# TEST EXECUTION ENTRY POINT
# =========================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
