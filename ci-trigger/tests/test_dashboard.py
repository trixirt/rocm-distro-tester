#!/usr/bin/env python3
# =============================================================================
# ROCm-Tester: Test Results Dashboard Unit Tests (v0.1)  
# pytest test suite for Flask-based dashboard application
# Covers route, API endpoint, and data processing functionality
#
# Usage: pytest ci-trigger/tests/test_dashboard.py -v --cov=ci-trigger/dashboard/app.py
# =============================================================================

import pytest
import json
import os
import tempfile
from pathlib import Path
from io import StringIO
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import dashboard.app as dashboard


class TestDashboardInitialization:
    """Test suite for Flask application initialization and configuration."""
    
    def test_app_creation_success(self):
        """Should create Flask app instance with correct configuration."""
        
        assert dashboard.app is not None
        assert isinstance(dashboard.app, dashboard.Flask)
        
        # Check that debug mode defaults to False (safe default)  
        assert dashboard.app.config.get('DEBUG') == False
    
    def test_results_dir_default_value(self):
        """Should use correct default value for results directory."""
        
        expected_path = '/var/rocm-tester/results'
        current_dir = dashboard.RESULTS_DIR
        
        # The path should be constructed correctly even if env variable not set
        assert str(current_dir).endswith(expected_path) or 'results' in str(current_dir), \
            f"Results dir {current_dir} does not match expected structure"


class TestLoadAllResults:
    """Test suite for result file loading logic."""
    
    def test_load_results_from_existing_directory(self, temp_test_dir):
        """Should successfully load all JSON results from directory with valid files."""
        
        # Create sample result files in temp directory
        sample_result_1 = {
            'distro': 'fedora',
            'package_name': 'hipblas', 
            'status': 'PASSED',
            'timestamp': str(datetime.now()),
            'execution_time_seconds': 100
        }
        
        sample_result_2 = {
            'distro': 'ubuntu',
            'package_name': 'hipsolver',
            'status': 'FAILED',  
            'timestamp': str(datetime.now() - timedelta(hours=1)),
            'execution_time_seconds': 50
        }
        
        test_file_dir = temp_test_dir / "test_results"
        test_file_dir.mkdir(parents=True)
        
        # Write JSON result files
        json_file_1 = test_file_dir / "fedora-hipblas-result.json"
        with open(json_file_1, 'w') as f:
            json.dump(sample_result_1, f)
            
        json_file_2 = test_file_dir / "ubuntu-hipsolver-result.json"  
        with open(json_file_2, 'w') as f:
            json.dump(sample_result_2, f)
        
        # Temporarily patch RESULTS_DIR for the function to read from correct location
        original_results_dir = dashboard.RESULTS_DIR
        
        try:
            dashboard.RESULTS_DIR = test_file_dir
            
            loaded_results = dashboard.load_all_results()
            
            assert len(loaded_results) == 2, f"Expected 2 results, got {len(loaded_results)}"
            
            # Verify both records are returned
            distros = [r['distro'] for r in loaded_results]
            assert 'fedora' in distros and 'ubuntu' in distros
            
            # Results should be sorted by timestamp (newest first)
            assert loaded_results[0]['package_name'] == 'hipblas'
            
        finally:
            dashboard.RESULTS_DIR = original_results_dir
    
    def test_load_returns_empty_list_for_nonexistent_dir(self):
        """Should return empty list when directory does not exist."""
        
        original_dir = dashboard.RESULTS_DIR
        
        try:
            dashboard.RESULTS_DIR = Path('/nonexistent/directory/path')
            
            results = dashboard.load_all_results()
            
            assert len(results) == 0, "Should return empty list for missing directory"
            assert isinstance(results, list), "Should always return list type"
            
        finally:
            dashboard.RESULTS_DIR = original_dir
    
    def test_load_filters_by_specified_distros(self):
        """Should correctly filter results when distro parameter is provided."""
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock result files for different distros  
            sample_fedora_data = [
                {'distro': 'fedora', 'package_name': 'hipblas', 'status': 'PASSED'},
                {'distro': 'fedora', 'package_name': 'rocblas', 'status': 'PASSED'}
            ]
            
            sample_ubuntu_data = [
                {'distro': 'ubuntu', 'package_name': 'hipsolver', 'status': 'FAILED'}
            ]
            
            # Write result files  
            test_dir = Path(temp_dir) / "filtered_test_results"
            test_dir.mkdir()
            
            for i, data in enumerate(sample_fedora_data * 2):
                json_file = test_dir / f"fedora-{data['package_name']}-{i}.json"
                with open(json_file, 'w') as f:
                    data['timestamp'] = datetime.now().isoformat()
                    json.dump(data, f)
            
            for data in sample_ubuntu_data:
                data['timestamp'] = (datetime.now() + timedelta(seconds=i)).isoformat()
                json_file = test_dir / "ubuntu-hipsolver.json"
                with open(json_file, 'w') as f:
                    json.dump(data, f)
            
            original_dir = dashboard.RESULTS_DIR
            
            try:
                dashboard.RESULTS_DIR = test_dir
                
                # Test loading only Fedora results
                fedora_results = dashboard.load_all_results(distros=['fedora'])
                
                assert len(fedora_results) > 0, "Should load Fedora filtered results"
                
                distros_loaded = [r['distro'] for r in fedora_results]
                assert all(distro == 'fedora' for distro in distros_loaded), \
                    "All returned distros should be Fedora when filtered"
                    
            finally:
                dashboard.RESULTS_DIR = original_dir


class TestIndexRoute:
    """Test suite for index page route functionality."""
    
    def test_returns_correct_html_structure(self, client):
        """Should return valid HTML with expected structure and data."""
        
        response = client.get('/')
        
        assert response.status_code == 200
        assert 'ROCm-Tester' in response.data.decode()
        assert '<h3>📊 Test Results Overview</h3>' in response.data.decode()


class TestResultsRoute:
    """Test suite for main results page with filtering."""
    
    def test_results_page_with_all_filters(self, client, temp_test_dir):
        """Should display filtered results correctly on results page."""  
        
        # Mock some results data
        mock_results = [
            {'distro': 'fedora', 'package_name': 'hipblas', 'status': 'PASSED'}
        ]
        
        response = client.get('/results?days=7')
        
        assert response.status_code == 200
        assert b'Test Details' in response.data
        
    def test_results_apply_distro_filter(self, client): 
        """Should apply distro filtering when parameter provided."""
        
        response = client.get('/results?distro=fedora')
        html = response.data.decode()
        
        # Even if no filtered content exists (empty fixture), the HTML should render without error
        assert 'Test Details' in html


class TestAPIDataRoutes:
    """Test suite for API endpoints returning JSON data."""
    
    def test_api_summary_returns_valid_statistics(self, client):
        """Should return accurate summary statistics from all loaded results."""
        
        response = client.get('/api/summary')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'statistics' in data
        assert 'by_distro' in data
        assert isinstance(data['statistics']['total_results'], int)
    
    def test_api_latest_results_returns_formatted_json(self, client):
        """Should return latest results data properly formatted."""
        
        response = client.get('/api/latest-results/10')
        
        assert response.status_code == 200
        json_data = json.loads(response.data)
        
        assert 'count' in json_data
        assert 'results' in json_data
        assert isinstance(json_data['count'], int)


class TestDateTimeHandling:
    """Test suite for datetime parsing and formatting functionality."""
    
    def test_load_all_results_sorts_by_timestamp_descending(self, temp_test_dir):
        """Should load results sorted with newest first based on timestamp field."""
        
        # Create timestamp order: oldest first to newest last
            
        old_result = {
            'package_name': 'hipblas', 
            'timestamp': (datetime.now() - timedelta(days=2)).isoformat(),
            'status': 'PASSED'
        }
        
        new_result = {
            'package_name': 'rocblas',
            'timestamp': datetime.now().isoformat(),  # Newest timestamp
            
            'status': 'FAILED'
        }
        
        test_dir = temp_test_dir / "timestamp_sorted_results"
        test_dir.mkdir(parents=True)
        
        json_file_old = test_dir / "hipblas-old.json"
        with open(json_file_old, 'w') as f:
            json.dump(old_result, f)
        
        json_file_new = test_dir / "rocblas-new.json"
        with open(json_file_new, 'w') as f: 
            json.dump(new_result, f)
            
        original_dir = dashboard.RESULTS_DIR
        
        try:
            dashboard.RESULTS_DIR = test_dir
            
            results = dashboard.load_all_results()
            
            assert len(results) == 2, "Should load both result files"
            assert results[0]['package_name'] == 'rocblas', \
                "Newest timestamp should appear first in sorted list"
            
        finally:
            dashboard.RESULTS_DIR = original_dir


class TestErrorHandling:
    """Test suite for robustness against malformed data."""
    
    def test_load_all_results_handles_malformed_json_gracefully(self, temp_test_dir):
        """Should skip corrupted files without crashing the loading process."""
        
        import json as json_lib
        
        # Create a directory with mixed valid and invalid JSON files
        test_dir = temp_test_dir / "malformed_results"
        test_dir.mkdir(parents=True)
        
        json_file_invalid = test_dir / "bad-result.json"
        with open(json_file_invalid, 'w') as f:
            f.write("{ this is not valid json content ")  # Intentionally invalid JSON
        
        sample_valid_result = {
            'distro': 'fedora', 
            'package_name': 'hipblas',
            'timestamp': datetime.now().isoformat(),
            'status': 'PASSED'
        }
        
        json_file_valid = test_dir / "good-result.json"
        with open(json_file_valid, 'w') as f:
            json_lib.dump(sample_valid_result, f)
            
        original_dir = dashboard.RESULTS_DIR
        
        try:
            dashboard.RESULTS_DIR = test_dir
            
            # Should gracefully skip invalid JSON files and load only valid ones
            results = dashboard.load_all_results()
            
            assert len(results) == 1, "Should skip corrupted file, but still process valid one"
            assert results[0]['package_name'] == 'hipblas', "Loaded result should be from valid file"
            
        finally:
            dashboard.RESULTS_DIR = original_dir


class TestDockerContainerization:
    """Test suite verifying Docker configuration is correct and containerizable."""
    
    def test_dockerfile_exists(self):
        """Should have Dockerfile in docker directory for build context."""
        
        project_root = Path(__file__).parent.parent.parent
        
        expected_file = project_root / "ci-trigger/docker/Dockerflake.dashboard"
        
        assert expected_file.exists(), f"Dockerfile dashboard not found at: {expected_file}"
        
    def get_expected_healthcheck_from_dockerfile(self):
        """Should extract and verify health check configuration from Dockerfile."""
        
        dockerfile_path = Path(__file__).parent.parent.parent / "ci-trigger/docker/Dockerfile.dashboard"
        
        with open(dockerfile_path, 'r') as f:
            content = f.read()
            
        assert '--interval=30s' in content, "Healthcheck interval not specified correctly"
        assert 'curl -f http://localhost:5001/api/summary' in content, \
            "Health check should query /api/summary endpoint"


# =============================================================================
# TEST FIXTURES (Auto-loaded by pytest) 
# =============================================================================

@pytest.fixture(autouse=True)
def temp_test_dir(tmp_path):
    """pytest temp directory fixture for test file creation."""
    import dashboard.app as app
    
    # Temporarily set results dir to use temp directory for all tests
    original_results_dir = app.RESULTS_DIR
    
    try:
        os.environ['RESULTS_DIR'] = str(tmp_path)
        yield tmp_path
        
        app.RESULTS_DIR = original_results_dir
        
    finally:
        if 'RESULTS_DIR' in os.environ:
            del os.environ['RESULTS_DIR']


@pytest.fixture
def client(app):
    """Flask test client fixture for route testing."""
    
    with app.app.test_client() as client:
        yield client


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

