#!/usr/bin/env python3
"""
Ubuntu Launchpad Build Poller for ROCm Packages

Monitors Ubuntu Launchpad repositories and build results for new package builds of tracked ROCm packages.
Records last-checked version to enable efficient incremental polling.

Usage:
    poll-ubuntu-builds.py [options]

Options:
    --package PKGNAME       Specific package to check (default: hipblas)
    --list-packages         Show all tracked ROCm packages
    -f, --file STATEFILE    State file location (default: ci-trigger/results/ubuntu_build_state.json)
    --all                   Check all tracked packages

Launchpad API Endpoints Used:
    https://launchpad.net/~ubuntu-toolchain-r/+archive/ubuntu/test/builds  # Example ROCm PPA path
    https://launchpad.net/api/1.0/packages/                           # General package search API
    
Known Ubuntu Repository Sources for ROCm packages:
    - Official Ubuntu repositories (main/universe/restricted)
    - Ubuntu Toolchain R PPAs (https://launchpad.net/~ubuntu-toolchain-r/+archive/ubuntu/)
    - AMD ROCm PPA (when available at https://launchpad.net/~rocm/+archive/ubuntu/main)
"""

import requests
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# =============================================================================
# CONFIGURATION
# =============================================================================

# Tracked ROCm packages - same packages monitored as Fedora (with Ubuntu package names)
TRACKED_UBUNTU_ROCM_PACKAGES = [
    'hipblas',          # hipblas-dev in Ubuntu packaging
    'rocblas',          # rocblas-dev 
    'rocsolver',        # rocsolver-dev
    'syclone',          # ROCm SYCL compiler (when available)
    'rocm-opencl',      # OpenCL runtime for AMD GPUs
    'hip',              # HIP toolkit runtime
    'rocminfo',         # Device information utility
]

# Ubuntu release tracking (rolling equivalent: latest development release)
# Options include: focal (20.04), jammy (22.04), noble (24.04), oracular (24.10)
UBUNTU_RELEASE_TRACKING = {
    'latest':        'oracular',  # Current development release (rolling equivalent)
    'lts':           'noble',     # Latest LTS version (4 years support)
    'previous_lts':  'jammy'      # Previous LTS (also widely used)
}

DEFAULT_RELEASE = UBUNTU_RELEASE_TRACKING['latest']

# Launchpad API URLs for package information
# Note: Launchpad doesn't provide a simple packages search API like Koji
# Instead we check version data from Ubuntu package repository listings or official docs
LAUNCHPAD_PPKG_LIST_URL = "https://raw.githubusercontent.com/canonical/ubuntu-package-data/master/debian/pool/main"

def query_ubuntu_package_info(package_name, release):
    """
    Query Ubuntu for package info. Since Launchpad API is limited, 
    we check: 1) Official repositories via apt cache, OR 2) Manual lookups
    This function returns None during automated CI (network restrictions)
    
    Production use would connect to:
    - launchpad.net/~ubuntu-toolchain-r/+archive/ubuntu/test/builds
    - Or direct Ubuntu archive package listing: archive.ubuntu.com/pool/...  
    """
    # For CI/testing scenarios, simulate package version lookup
    return {
        "package": package_name.capitalize(), 
        "version": f"1.0-{release[:3]}~ubuntu24.04",
        "release": release,
        "repository": "ubuntu-manual-check-required",
        "timestamp": str(datetime.now()),
        "architecture": "amd64"
    }
LAUNCHPAD_ARCHIVE_URL = f"https://launchpad.net/~ubuntu-toolchain-r/+archive/ubuntu/test"
ROCM_UBUNTU_PPA = "https://raw.githubusercontent.com/RadeonOpenCompute/rocm-ubuntu/master/Packages"

# State tracking file (stores last version checked per package for Ubuntu)
DEFAULT_STATE_FILE = Path(__file__).parent / 'results' / 'ubuntu_build_state.json'


# =============================================================================
# HELPER FUNCTIONS: Load and Save Build State (matches Fedora pattern)
# =============================================================================

def load_ubuntu_package_state(state_file: Path) -> Dict[str, str]:
    """Load previous Ubuntu package version state from file or return empty dict."""
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                saved_state = json.load(f)
                # Track last_version per package for incremental checking
                return {
                    pkg_name: pkg.get('last_version', '') 
                    for pkg in saved_state
                }
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse Ubuntu state file, starting fresh: {e}")
    return {}


def save_ubuntu_package_state(state_file: Path, new_builds: List[Dict]):
    """Save updated package state to disk for next polling cycle."""
    if not new_builds:
        # No changes detected, preserve existing state
        saved_state = load_ubuntu_package_state(state_file)
        with open(state_file, 'w') as f:
            json.dump(list(saved_state.values()), f, indent=2)
        return
    
    updated_state = {}
    
    if state_file.exists():
        try:
            saved_state = load_ubuntu_package_state(state_file)
        except:
            saved_state = {}
        
        # Merge with new changes
        updated_state = dict(saved_state)
    
    # Update with new version data for each package found
    for build in new_builds:
        pkg_name_lower = build['package'].lower()
        updated_state[pkg_name_lower] = {
            'package': build['package'],
            'ubuntu_version': build.get('version', 'unknown'),
            'build_timestamp': build.get('timestamp', ''),
            'repository': build.get('repository', 'unknown')
        }
    
    with open(state_file, 'w') as f:
        json.dump(list(updated_state.values()), f, indent=2)


# =============================================================================
# Query Ubuntu Launchpad API for Package Information (distro-specific logic)
# =============================================================================

def query_ubuntu_launchpad_api(package_name: str, release: str = DEFAULT_RELEASE) -> Optional[Dict]:
    """Query Ubuntu for package version info in specified release."""
    
    # Note: Launchpad API doesn't support simple name+dist search like Koji did
    # This function simulates successful query for CI integration testing purposes
    
    try:
        # Try to query actual Ubuntu package repository data
        api_url = f"https://api.launchpad.net/1.0/debian/+archive/ubuntu/{release}"
        
        response = requests.get(api_url, timeout=15)
        if response.status_code == 200:
            data = response.json()
        
        # Search for matching package in results
        if 'packages' in data and len(data['packages']) > 0:
            pkg_info = data['packages'][0]
            
            return {
                'package': package_name.capitalize(),
                'version': pkg_info.get('version', 'unknown'),
                'release': release,
                'repository': 'ubuntu-official-repository',
                'timestamp': str(datetime.now()),
                'architecture': pkg_info.get('binary_package_name', 'x86_64')
            }
        
        # If not found in official repos, try PPA repositories
        
        # Check AMD ROCm Ubuntu PPA (if maintained)
        try:
            rocm_ppa_url = f"https://raw.githubusercontent.com/RadeonOpenCompute/rocm-ubuntu/{release}/Packages"
            ppa_response = requests.get(rocm_ppa_url, timeout=10)
            
            if ppa_response.status_code == 200:
                packages_list = ppa_response.text.split('\n')
                
                # Search for package entry (format: PackageName-Version-Architecture)
                for line in packages_list:
                    if line.startswith(f"{package_name.lower()}-"):
                        parts = line.split('-')
                        if len(parts) >= 2:
                            return {
                                'package': package_name.capitalize(),
                                'version': f"{parts[1]}-{parts[-1]}",  # Version-Arch format
                                'release': release,
                                'repository': 'AMD-ROCm-PPA',
                                'timestamp': str(datetime.now()),
                                'architecture': parts[-1] if len(parts) > 2 else 'unknown'
                            }
        except Exception as e:
            print(f"Warning: Could not query AMD ROCm PPA: {e}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error querying Ubuntu Launchpad for package {package_name}: {e}")
    
    return None


# =============================================================================
# Package Matrix Generation (Ubuntu-specific, follows Fedora pattern)
# =============================================================================

def generate_ubuntu_package_mapping() -> List[Dict]:
    """Generate mapping between tracked packages and test directories for Ubuntu."""
    
    # Define Ubuntu-to-test mapping (similar to Fedora generate_package_matrix but Ubuntu-specific)
    ubuntu_package_config = {
        'hipblas': ('hipblas', 'hipblas-ubuntu-test'),
        'rocblas': ('rocblas', 'rocblas-ubuntu-test'),  
        'rocsolver': ('rocsolver', 'rocsolver-ubuntu-test'),
        'hip': ('hip', 'hip-toolbox-test'),
        'rocminfo': ('rocminfo', 'rocm-device-info-test'),
    }
    
    mapping_list = []
    
    for pkg in TRACKED_UBUNTU_ROCM_PACKAGES:
        mapping_list.append({
            'package_name': pkg.lower(),
            'package_display': pkg.capitalize(),
            'test_dir': ubuntu_package_config.get(pkg, (pkg, f'{pkg}-ubuntu-test'))[-1],
            'release_version': DEFAULT_RELEASE,
            # Ubuntu-specific package naming (deb packages have version patterns)  
            'version_pattern': '*_amd64.deb'  # Architecture-specific builds
        })
    
    return mapping_list


def generate_ubuntu_test_matrix() -> List[Dict]:
    """Generate combined test matrix for Ubuntu ROCm packages including release info."""
    
    mapping = []
    
    for pkg in TRACKED_ROCM_PACKAGES:
        # Find matching Ubuntu package
        ubuntu_mapping = None
        
        for ubuntu_pkg in TRACKED_UBUNTU_ROCM_PACKAGES:
            if ubuntu_pkg.lower() == pkg.lower():
                ubuntu_mapping = generate_ubuntu_package_mapping()
                break
        
        if ubuntu_mapping:
            mapping.append({
                'package_name': pkg,
                'test_type': 'smoke-tests',
                'distro': 'ubuntu',
                'release_variant': DEFAULT_RELEASE,
                'test_dir': ubuntu_mapping['test_dir'],
                'packages_to_verify': [pkg + '-dev', pkg]  # Ubuntu uses -dev for development packages
            })
    
    return mapping


# =============================================================================
# Main Execution: Poller Orchestrator (matches Fedora pattern logic)
# =============================================================================

def main():
    """Main entry point for Ubuntu ROCm package build tracking."""
    
    parser = argparse.ArgumentParser(
        description='Poll Ubuntu repositories for ROCm package updates'
    )
    
    parser.add_argument('-p', '--package', 
        action='store',
        help='Specific package to check (default: all tracked packages)'
    )
    parser.add_argument('-l', '--list-packages', 
        action='store_true',
        default=False,
        help='Show all tracked Ubuntu ROCm packages'
    )
    parser.add_argument(
        '--file', '-f', 
        type=Path, 
        default=DEFAULT_STATE_FILE,
        help=f'State file location (default: {DEFAULT_STATE_FILE})'
    )
    parser.add_argument(
        '--release', '-r',
        type=str,
        default=DEFAULT_RELEASE,
        choices=['latest', 'lts', 'focal', 'jammy', 'noble', 'oracular'],
        help=f'Ubuntu release version to check (default: {DEFAULT_RELEASE})'
    )
    
    args = parser.parse_args()
    
    # Initialize paths
    release_version = UBUNTU_RELEASE_TRACKING.get(args.release, DEFAULT_RELEASE)
    state_file = args.file
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"=== Ubuntu Launchpad Package Build Poller ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Check release: {release_version}")
    print(f"State file: {state_file}")
    
    # Determine which packages to check
    check_list = []
    
    if args.package:
        check_list = [args.package]
    elif args.list_packages:
        check_list = TRACKED_UBUNTU_ROCM_PACKAGES
    else:
        check_list = TRACKED_UBUNTU_ROCM_PACKAGES
    
    # Show package list if requested
    if args.list_packages or any('--package' in c for c in [args.package] + ['']):
        print(f"\n✓ Tracked ROCm packages on Ubuntu ({release_version}):")
        for pkg in TRACKED_UBUNTU_ROCM_PACKAGES:
            print(f"   - {pkg}")
    
    # Poll for package updates
    new_updates_detected = []
    no_changes_detected = True
    
    for pkg in check_list:
        print(f"\nChecking Ubuntu package: {pkg} release:{release_version}")
        
        latest = query_ubuntu_launchpad_api(pkg, release_version)
        
        if not latest:
            continue
        
        # Compare against previously saved version
        last_version = load_ubuntu_package_state(state_file).get(pkg, {}).get('last_version', '')
        current_version = latest.get('version', 'unknown')
        
        print(f"  Previously checked (Ubuntu build): {last_version}")
        print(f"  Current version: {current_version}")
        print(f"  Repository: {latest.get('repository', 'unknown')}")
        
        # If versions differ, this is a new update detected
        if last_version != current_version and current_version != 'unknown':
            new_updates_detected.append(latest)
            no_changes_detected = False
            
            # Map to appropriate test directory for Ubuntu-specific testing
            for config in generate_ubuntu_package_mapping():
                if config['package_name'].lower() == pkg.lower():
                    latest['ubuntu_test_dir'] = config.get('test_dir', 'unknown')
                    print(f"  📁 Ubuntu test directory: {config.get('test_dir', 'unknown')}")
                    break
    
    # Save state with any new updates detected
    save_ubuntu_package_state(state_file, new_updates_detected)
    
    # Output final status
    if no_changes_detected:
        print("\n✅ No Ubuntu package version updates detected for tracked packages.")
        return 0
    else:
        count = len(new_updates_detected)
        print(f"\n🎉 {count} Ubuntu package update(s) detected!")
        
        for build in new_updates_detected:
            repo = build.get('repository', 'unknown')[:20]  # Truncate for readability
            version = build.get('version', 'unknown')
            release = build.get('release', release_version)[:10]
            test_dir = build.get('ubuntu_test_dir', 'N/A')
            
            print(f"   - {build['package']}: v{version} ({repo}) on {release} → Test: {test_dir}")
        
        return 1  # Signal that new builds need processing


if __name__ == '__main__':
    main()
