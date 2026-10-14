#!/usr/bin/env python3
"""
EPEL (Extra Packages for Enterprise Linux) Build Poller for RHEL ROCm Packages

Monitors EPEL repository and Fedora RPM repositories for new package builds of tracked ROCm packages.
Records last-checked version to enable efficient incremental polling.

For CentOS Stream/RHEL 10, ROCm packages are sourced from:
- Fedora Koji (shared ecosystem with CentOS)
- EPEL repository (RHEL-specific package variants)

Usage:
    poll-epel-builds.py [options]

Options:
    --package PKGNAME       Specific package to check (default: hipblas)
    --list-packages         Show all tracked ROCm packages  
    -f, --file STATEFILE    State file location (default: ci-trigger/results/epel_build_state.json)
    --all                   Check all tracked packages
    --epel-version VERSION  EPEL version to track (10=latest, or specific branch)

EPEL API Endpoints Used:
    https://kojipkg.fedoraproject.org/repos/epel-10/latest/x86_64/packages/  # EPEL 10 package listing
    https://src.fedoraproject.org/rpms/hipblas  # RPM source repository
    https://docs.fedoraproject.org/en-US/fedora/doxygen/api/index.html      # Koji API endpoints
"""

import requests
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# =============================================================================
# CONFIGURATION: EPEL/RHEL Package Tracking  
# Same packages as Fedora but with RHEL-specific naming and versions
# =============================================================================

# Tracked RHEL/CentOS Stream ROCm packages - matches Fedora package list
TRACKED_RHEL_ROCM_PACKAGES = [
    'hipblas',          # HIP Basic Linear Algebra Subroutine
    'rocblas',          # ROC BASIC LINEAR ALGEBRA SUBROUTINE (RHEL variant)
    'hipsolver',        # HIP BLAS solver
    'rocsolver',        # ROC SOLVER library
    'hipfft',           # HIP Fourier Transform Library  
    'rocfft',           # ROC Fourier Transform Library
    'hipsparse',        # HIP Sparse BLAS
    'rocsparse',        # ROC Sparse library
    'rccl',             # ROCm Communication Collectives
]

# EPEL version tracking for CentOS Stream equivalents
EPEL_VERSION_TEMPLATES = {
    '10':           f"epel-10",              # CentOS Stream 10 (newest) 
    '9':            f"epel-9",               # Older EPEL variant
    'latest':       f"epel-10",              # Current rolling equivalent
}

DEFAULT_EPEL_VERSION = EPEL_VERSION_TEMPLATES['latest']

# Koji API URL for EPEL package builds (Fedora/Koji shared infrastructure)  
KOJI_EPEL_BASE_URL = "https://kojipkg.fedoraproject.org/repos/epel"
EPEL_API_ENDPOINTS = {
    'epel-10': "https://kojipkg.fedoraproject.org/repos/epel-10/latest/builds",  # CentOS Stream 10 equivalent
}

# State tracking file (stores last build_id per package for incremental checking)
DEFAULT_STATE_FILE = Path(__file__).parent / 'results' / 'epel_build_state.json'


# =============================================================================
# HELPER FUNCTIONS: Load and Save EPEL Build State (matches Fedora patterns)
# Same structure as Fedora poller but with EPEL-specific version tracking  
# =============================================================================

def load_epel_package_state(state_file: Path) -> Dict[str, str]:
    """Load previous EPEL package build state from file or return empty dict."""
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                saved_state = json.load(f)
                # Extract just the latest build_id per package for incremental checking
                return {
                    pkg['package']: pkg.get('last_build_id', '') 
                    for pkg in saved_state
                }
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse EPEL state file, starting fresh: {e}")
    return {}


def save_epel_package_state(state_file: Path, new_builds: List[Dict]):
    """Save updated build state to disk for next polling cycle."""
    if not new_builds:
        # No changes detected, preserve existing state for efficient cycling
        saved_state = load_epel_package_state(state_file)
        with open(state_file, 'w') as f:
            json.dump(list(saved_state.values()), f, indent=2)
        return
    
    updated_state = {}
    
    if state_file.exists():
        try:
            saved_state = load_epel_package_state(state_file)
        except:
            saved_state = {}
        
        # Merge with new changes while preserving old state
        updated_state = dict(saved_state)
    
    # Update with new build data for each package detected
    for build in new_builds:
        pkg_name_lower = f"{build['package'].lower()}-epel"
        updated_state[pkg_name_lower] = {
            'package': build['package'],
            'last_build_id': str(build.get('build_id', '')),
            'epel_version': build.get('epel_version', DEFAULT_EPEL_VERSION),
            'timestamp': build.get('timestamp', ''),
            'repository': build.get('repository', 'epel')
        }
    
    with open(state_file, 'w') as f:
        json.dump(list(updated_state.values()), f, indent=2)


# =============================================================================
# Query EPEL/Fedora Koji API for Package Information (RHEL/RPM specific)
# Uses same APIs as Fedora but focuses on CentOS Stream compatible builds
# =============================================================================

def query_epel_koji_api(package_name: str, epelet_version: str = DEFAULT_EPEL_VERSION) -> Optional[Dict]:
    """Query Koji API for EPEL package information matching CentOS Stream requirements."""
    
    # EPEL packages share infrastructure with Fedora (RPM ecosystem integration)
    # This enables unified tracking across both distributions
    
    api_endpoint = None
    
    # Determine proper build target URL based on EPEL version requested
    if epelet_version == '10':
        # CentOS Stream 10 equivalent - uses epel-10 repository
        api_url = f"{KOJI_EPEL_BASE_URL}/epel-10/latest/x86_64/packages/{package_name}"
    
    elif epelet_version.startswith('epel-'):
        # Generic EPEL version tracking  
        base_epel_ver = epelet_version.replace('epel-', '')
        api_url = f"{KOJI_EPEL_BASE_URL}/epel-{base_epel_ver}/latest/x86_64/packages/{package_name}"
    
    else:
        # Default to latest available builds for the package
        api_endpoint = "https://kojipkg.fedoraproject.org/package" + "/" + f"{package_name}"
        return {
            'package': package_name.capitalize(),
            'last_build_id': str(datetime.now().timestamp()),
            'epel_version': DEFAULT_EPEL_VERSION,
            'repository': 'fedora-epel-shared',
            'available_version': 'unknown'  # Will be filled by Koji API response parsing
        }
    
    try:
        import requests
        response = requests.get(api_url, timeout=15)
        
        # Check for package availability in requested EPEL version
        if response.status_code == 200:
            data = response.json()
            
            if 'packages' in data and len(data['packages']) > 0:
                pkg_info = data['packages'][0]
                
                return {
                    'package': package_name.capitalize(),
                    'last_build_id': str(pkg_info.get('build_id', '')),
                    'epel_version': epelet_version, 
                    'repository': f"epel-{epelet_version}" if '-epel' in api_url else "fedora-external",
                    'available_version': pkg_info.get('version', 'unknown'),
                    'timestamp': str(datetime.now()),
                    'architecture': 'x86_64'  # Standard RHEL architecture tracking
                }
        
        # No build found for requested package/version combination
        if response.status_code == 404:
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error querying EPEL Koji API for {package_name}: {e}")
    
    return None


# =============================================================================
# Package Matrix Generation for RHEL/CentOS (similar to Fedora mapping)
# Maps tracked packages to their CentOS Stream-compatible test directories  
# =============================================================================

def generate_epel_package_mapping() -> List[Dict]:
    """Generate mapping between tracked packages and test directories for EPEL/RHEL."""
    
    # Define EPEL-to-test directory mappings (similar to Fedora's generation logic)
    epel_package_config = {
        'hipblas': ('hipblas', 'hipblas-rhel-test'),
        'rocblas': ('rocblas', 'rocblas-rhel-test'),  
        'hipsolver': ('hipsolver', 'hipsolver-rhel-test'),
        'rocsolver': ('rocsolver', 'rocsolver-rhel-test'),
        'hipfft': ('hipfft', 'hipfft-rhel-test'),
        'rocfft': ('rocfft', 'rocfft-rhel-test'),
    }
    
    mapping_list = []
    
    for pkg in TRACKED_RHEL_ROCM_PACKAGES:
        mapping_list.append({
            'package_name': pkg.lower(),
            'package_display': pkg.capitalize(),
            'test_dir': epel_package_config.get(pkg, (pkg, f'{pkg}-rhel-test'))[-1],
            # EPEL-specific metadata for RHEL environment tracking  
            'arch_type': 'x86_64',  # Standard RHEL architecture
            'rpm_format': True      # Indicates RPM-based package packaging
        })
    
    return mapping_list


# =============================================================================
# Main Execution: Poller Orchestrator (matches Fedora pattern logic)  
# Handles EPEL-specific version checks and builds detection for CentOS Stream systems
# =============================================================================

def main():
    """Main entry point for EPEL ROCm package build tracking."""
    
    parser = argparse.ArgumentParser(
        description='Poll EPEL repositories for RHEL/CentOS Stream ROCm package updates'
    )
    
    parser.add_argument(
        '--package', 
        action='store',
        help='Specific package to check (default: all tracked packages)'
    )
    parser.add_argument(
        '--list-packages', '-l', 
        action='store_true',
        default=False,
        help='Show all tracked EPEL/RHEL ROCm packages'
    )
    parser.add_argument(
        '--file', '-f', 
        type=Path, 
        default=DEFAULT_STATE_FILE,
        help=f'State file location (default: {DEFAULT_STATE_FILE})'
    )
    parser.add_argument(
        '--version', '-v',
        type=str,
        default='10',  # CentOS Stream 10 = latest EPEL equivalent
        choices=['10', '9', 'latest'],
        help=f'EPEL version to check (default: 10=CentOS Stream 10)'
    )
    
    args = parser.parse_args()
    
    # Determine actual EPEL version string for use in API queries
    epelet_ver = f"epel-{args.version}" if args.version != 'latest' else None
    epelet_name = args.version
    
    print(f"=== EPEL/RHEL ROCm Package Build Poller ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"EPEL version target: {epelet_ver or epelet_name}")
    print(f"State file: {args.file}")
    
    # Determine which packages to check from tracked list
    check_list = []
    
    if args.package:
        check_list = [args.package]
    elif args.list_packages:
        check_list = TRACKED_RHEL_ROCM_PACKAGES
    else:
        check_list = TRACKED_RHEL_ROCM_PACKAGES
    
    # Show package list if requested for confirmation
    if any([True for c in ['--list-packages', '--all'] if c in args]):
        print(f"\n✓ Tracked EPEL/CentOS Stream ROCm packages:")
        for pkg in check_list:
            print(f"   - {pkg}")
            print(f"     -> Test directory: {generate_epel_package_mapping()[-1]['test_dir']}")
    
    # Poll for package updates matching CentOS Stream requirements
    new_updates_detected = []
    no_changes_detected = True
    
    for pkg in check_list:
        print(f"\nChecking EPEL package: {pkg} version:{epelet_ver or epelet_name}")
        
        latest_build = query_epel_koji_api(pkg, epelet_ver)
        
        if not latest_build:
            continue
        
        # Compare against previously saved build ID to detect changes
        prev_state = load_epel_package_state(args.file) or {}
        last_build_id = prev_state.get(f"{pkg.lower()}-epel", {}).get('last_build_id', '')
        current_build_id = latest_build.get('last_build_id', '0')
        
        print(f"  Previously checked (EPEL build): {str(last_build_id)[:10]}...")
        print(f"  Current build ID: {current_build_id}")
        print(f"  Version available: {latest_build.get('available_version', 'unknown')}")
        print(f"  Repository source: {latest_build.get('repository', 'unknown')}")
        
        # If build IDs differ, this is a new update detected in EPEL repo
        if str(last_build_id) != current_build_id and current_build_id != '' and int(current_build_id) > 0:
            new_updates_detected.append(latest_build)
            no_changes_detected = False
            
            # Map to appropriate test directory for RHEL-specific testing
            for config in generate_epel_package_mapping():
                if config['package_name'].lower() == pkg.lower():
                    latest_build['rhel_test_dir'] = config.get('test_dir', f'{pkg}-rhel-test')
                    print(f"  📁 CentOS Stream test directory: {config.get('test_dir')}")
                    break
    
    # Save state with any new EPEL updates detected
    save_epel_package_state(args.file, new_updates_detected)
    
    # Report final status to user or CI pipeline
    if no_changes_detected:
        print("\n✅ No EPEL package version updates detected for tracked packages.")
        return 0
    
    count = len(new_updates_detected)
    print(f"\n🎉 {count} EPEL/RHEL package update(s) detected!")
    
    for build in new_updates_detected:
        repo_name = build.get('repository', 'unknown')[:30]
        pkg_name = build['package']
        arch = build.get('architecture', 'x86_64')
        ver = build.get('available_version', 'N/A')
        
        print(f"   - {pkg_name}: Build #{build['last_build_id']} ({repo_name}) on epel-{ver} → Test: {build['rhel_test_dir']}")
    
    return 1  # Signal that new builds detected and need CI processing


if __name__ == '__main__':
    main()
