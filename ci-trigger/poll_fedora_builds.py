#!/usr/bin/env python3
"""
Fedora Koji Build Poller for ROCm Packages

Monitors Fedora Koji and Launchpad APIs for new package builds of tracked packages.
Records last-checked state to enable efficient incremental polling.

Usage:
    poll-fedora-builds.py [options]

Options:
    --package PKGNAME       Specific package to check (default: hipblas)
    --list-packages         Show all tracked ROCm packages
    -f, --file STATEFILE    State file location (default: ci-trigger/results/build_state.json)
    --all                   Check all tracked packages

Koji API Endpoints Used:
    https://kojipkg.fedoraproject.org/package/{package_name}
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

# Tracked ROCm packages - these are the ones we need to test
TRACKED_ROCM_PACKAGES = [
    'hipblas',      # HIP Basic Linear Algebra Subroutine
    'rocblas',      # ROC BASIC LINEAR ALGEBRA SUBROUTINE
    'hipsolver',    # HIP BLAS solver
    'rocsolver',    # ROC SOLVER library
    'hipfft',       # HIP Fourier Transform Library
    'rocfft',       # ROC Fourier Transform Library
    'hipsparse',    # HIP Sparse BLAS
    'rocsparse',    # ROC Sparse library
    'rccl',         # ROCm Communication Collectives
    'miopen',       # MIOpen - deep learning primitives
    'rocrand',      # Random number generation for GPUs
]

# Base Koji API URLs
KOJI_PKG_LIST_URL = "https://kojipkg.fedoraproject.org/packages"

# State tracking file (stores last build ID per package)
DEFAULT_STATE_FILE = Path(__file__).parent / 'results' / 'build_state.json'


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_build_state(state_file: Path) -> Dict[str, str]:
    """Load previous build state from file or return empty dict."""
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                saved_state = json.load(f)
                # Extract just the latest build_id per package
                return {
                    pkg['name']: pkg.get('last_build_id', '') 
                    for pkg in saved_state
                }
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse state file, starting fresh: {e}")
    return {}


def save_build_state(state_file: Path, new_builds: List[Dict]):
    """Save updated build state to disk."""
    state_list = []
    
    # Keep all existing tracked packages
    existing_ids = set()
    for package in TRACKED_ROCM_PACKAGES:
        existing_ids.add(package.lower())
    
    # Update with new builds, preserving previous state for unmodified packages
    updated_state = {}
    
    if state_file.exists():
        try:
            saved_state = load_build_state(state_file)
        except:
            saved_state = {}
        
        updated_state = dict(saved_state)
    
    # Update with new build data
    for build in new_builds:
        pkg_name = build['package'].lower()
        updated_state[pkg_name] = {
            'package': build['package'],
            'last_build_id': build['build_id'],
            'build_timestamp': build.get('timestamp', ''),
        }
    
    # Only write if we have new builds to record
    if new_builds:
        with open(state_file, 'w') as f:
            json.dump(list(updated_state.values()), f, indent=2)
            save_file = state_file
    
    print(f"Saved build state to {state_file}")


def query_fedora_koji_api(package_name: str) -> Optional[Dict]:
    """Query Fedora Koji API for latest package information."""
    try:
        # Get list of all packages with their latest build IDs
        response = requests.get(KOJI_PKG_LIST_URL, timeout=10)
        response.raise_for_status()
        
        pkg_list_data = response.json()
        
        for entry in pkg_list_data.get('packages', []):
            if isinstance(entry, dict):
                # Handle modern format: {"name": "...", "latest_builds": [...]}
                name = entry.get('name', '')
                builds = entry.get('latest_builds', [])
                
                if name.upper() == package_name.upper():
                    if builds:
                        latest = builds[0] or {}
                        return {
                            'package': name,
                            'build_id': latest.get('task_id', latest.get('id', '')),
                            'timestamp': str(datetime.now()),
                            'available_version': latest.get('version', 'unknown')
                        }
                    return None
            
            elif isinstance(entry, list) and len(entry) >= 2:
                # Handle legacy format: ['name', build_id]
                name = entry[0]
                build_id = entry[1]
                
                if name.upper() == package_name.upper():
                    return {
                        'package': name,
                        'build_id': str(build_id),
                        'timestamp': str(datetime.now()),
                        'available_version': None
                    }
        
        print(f"No build found for package: {package_name}")
        return None
        
    except requests.RequestException as e:
        print(f"Error querying Koji API: {e}")
        return None


def generate_package_matrix() -> List[Dict]:
    """Generate mapping between tracked packages and test directories."""
    matrix = []
    
    # Define package to test directory mappings
    package_config = {
        'hipblas': 'hipblas',
        'rocblas': 'rocblas', 
        'hipsolver': 'hipsolver',
        'rocsolver': 'rocsolver',
        'hipfft': 'hipfft',
        'rocfft': 'rocfft',
        'hipsparse': 'hipsparse',
        'rocsparse': 'rocsparse',
        'rccl': 'rccl',
        'miopen': 'miopen',
        'rocrand': 'rocrand',
        # Add more mappings as packages are added
    }
    
    for pkg in TRACKED_ROCM_PACKAGES:
        matrix.append({
            'package_name': pkg.lower(),
            'package_display': pkg.capitalize(),
            'test_dir': package_config.get(pkg, pkg),
            'status': 'pending',  # Will be updated by test runner
        })
    
    return matrix


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def get_parser():
    """Get the argument parser for Fedora build polling."""
    parser = argparse.ArgumentParser(
        prog='poll_fedora_builds.py',
        description='Poll Fedora Koji for ROCm package builds',
        epilog='Example: python3 poll_fedora_builds.py --package hipblas'
    )
    parser.add_argument('-p', '--package', type=str, help='Specific package to check')
    parser.add_argument('-l', '--list-packages', action='store_true', help='List all tracked packages')
    parser.add_argument('-a', '--all', action='store_true', help='Check all packages (default)')
    parser.add_argument('-f', '--file', type=str, default=None, help='State file path')
    parser.add_argument('-r', '--reset', '--force-reset', action='store_true', dest='force_reset', help='Reset build tracking state')
    return parser

def main():
    """Main entry point for package build tracking and test triggering.
    
    This script monitors Fedora Koji for ROCm package updates and can trigger
    automated testing when new builds are detected.
    """
    args = get_parser().parse_args()
    
    # Initialize paths
    state_file = args.file or DEFAULT_STATE_FILE
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load previous state
    saved_state = load_build_state(state_file) if not args.force_reset else {}
    
    print(f"=== Fedora Koji Build Poller ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"State file: {state_file}")
    
    # Check packages to monitor
    check_list = []
    
    if args.package:
        check_list = [args.package]
    elif args.all or True:  # Default: check all
        check_list = TRACKED_ROCM_PACKAGES
    
    new_builds_detected = []
    no_changes = True
    
    for pkg_name in check_list:
        print(f"\nChecking package: {pkg_name}")
        
        latest = query_fedora_koji_api(pkg_name)
        
        if not latest:
            continue
        
        # Check against previously saved build ID
        last_build_id = saved_state.get(pkg_name, {}).get('last_build_id', '')
        current_build_id = latest.get('build_id', '')
        
        print(f"  Last checked: {last_build_id}")
        print(f"  Current build: {current_build_id}")
        
        # If builds differ, this is a new update
        if last_build_id != current_build_id:
            new_builds_detected.append(latest)
            no_changes = False
            
            # Map to appropriate test directory
            for config in generate_package_matrix():
                if config['package_name'] == pkg_name.lower():
                    latest['test_dir'] = config['test_dir']
                    print(f"  Test directory: {config['test_dir']}")
                    break
    
    # Save state with any new builds detected
    save_build_state(state_file, new_builds_detected)
    
    # Report results
    if no_changes:
        print("\n✅ No new build changes detected for tracked packages.")
        return 0
    else:
        print(f"\n🎉 {len(new_builds_detected)} new build(s) detected!")
        for build in new_builds_detected:
            print(f"   - {build['package']}: #{build['build_id']} ({build.get('available_version', 'unknown')})")
        
        # Exit with success but signal that work needs to be done
        return 1  # Non-zero indicates new builds need processing


if __name__ == '__main__':
    import argparse
    main()
