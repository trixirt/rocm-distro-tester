#!/usr/bin/env python3
"""
Fedora ROCm Package Poller

Monitors Fedora packages for updates using a local container approach.
Supports multiple Fedora releases (rawhide, f45, f44, f43) with state persistence per release.

Usage:
    poll_fedora_builds.py [options]

Options:
    -p, --package PKGNAME       Specific package to check (default: hipblas)
    -r, --release RELEASE       Fedora release version (rawhide, f45, f44, f43; default: rawhide)
    -l, --list-packages         Show all tracked ROCm packages
    -f, --file STATEFILE        State file location (default: results/build_state_<release>.json)
    -a, --all                   Check all tracked packages (default) 
    
Query Methods:
    1. Docker-based per Fedora release (preferred via fedora:rawhide/f45/f44/f43 containers)
    
Author: ROCm-Distro-Tester Team  
Version: 0.3.0 (Release-aware)
"""

import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# ==========================================================================
# CONFIGURATION
# ==========================================================================

TRACKED_ROCM_PACKAGES = [
    'hipblas', 
    'rocblas', 
    'hipsolver', 
    'rocsolver',
    'hipfft',   
    'rocfft',
    'hipsparse', 
    'rocsparse',
    'rccl',       
    'miopen',     
    'rocrand',
]

# Fedora releases and their corresponding Docker images
RELEASE_IMAGES = {
    'rawhide': 'fedora:rawhide',
    'f45': 'fedora:45',
    'f44': 'fedora:44', 
    'f43': 'fedora:43',
}

DEFAULT_STATE_FILE = Path(__file__).parent / 'results' / '{release}_build_state.json'

# Package-to-test-directory mappings for test orchestration
PACKAGE_TEST_DIRS = {
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
}

# ==========================================================================
# STATE MANAGEMENT FUNCTIONS
# ==========================================================================

def get_state_file(release: str) -> Path:
    """Get state file path for a specific release."""
    return DEFAULT_STATE_FILE.parent / f"{release}_build_state.json"


def load_build_state(state_file: Path) -> Dict[str, Any]:
    """Load previous build state from file or return empty dict.
    
    Handles both legacy dict format {pkg: build_id_str} and list format 
    [{package: ..., build_id: ...}, ...] for backward compatibility.
    """
    if not state_file.exists():
        return {}
        
    try:
        with open(state_file, 'r') as f:
            saved = json.load(f)
            # Handle both formats
            if isinstance(saved, list):
                return {pkg.get('name', pkg.get('package', '')): pkg.get('build_id', '') for pkg in saved if pkg}
            elif isinstance(saved, dict):
                # Already a dict mapping pkg->build_id
                return saved
            return {}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Warning: Could not parse state file {state_file}: {e}, starting fresh")
        return {}


def save_build_state(state_file: Path, new_builds: List[Dict]) -> None:
    """Save updated build state to disk in list format for consistency."""
    if not new_builds:
        print("No updates to save.")
        return
        
    # Load existing state (may be dict {pkg: build_id} or dict of full objects)
    raw_existing = load_build_state(state_file)
    
    # Normalize to unified dict format: {package_name_lower: {package, build_id, timestamp}}
    existing = {}
    for pkg, value in raw_existing.items():
        if isinstance(value, str):
            existing[pkg] = {
                'package': pkg,
                'build_id': value,
                'timestamp': None
            }
        elif isinstance(value, dict):
            existing[pkg] = value
        else:
            continue
    
    # Merge with new builds (update existing, add new)
    for build in new_builds:
        pkg_name = build['package'].lower()
        existing[pkg_name] = {
            'package': build['package'],
            'build_id': str(build.get('build_id', '')),
            'timestamp': build.get('timestamp', datetime.now().isoformat()),
        }
    
    # Ensure parent directory exists
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write as list of objects for consistency and future extensibility
    with open(state_file, 'w') as f:
        json.dump(list(existing.values()), f, indent=2)
    
    print(f"Saved build state to {state_file}")

# ==========================================================================
# QUERY FUNCTIONS - DOCKER-BASED PER RELEASE  
# ==========================================================================

def docker_query(package_name: str, release: str = "rawhide") -> Optional[Dict[str, Any]]:
    """
    Query Fedora package info using Docker container for specific release.
    
    Args:
        package_name: Name of the package to query
        release: Fedora release (rawhide, f45, f44, etc.)
        
    Returns:
        Dict with package metadata including build_id,
        or None if package not found or error occurs.
    """
    # Get docker image for this release
    docker_image = RELEASE_IMAGES.get(release, f"fedora:{release}")
    
    try:
        # Run dnf info inside specified Fedora release container
        cmd = [
            'docker', 'run', '--rm', docker_image,
            'sh', '-c', f'dnf -y info "{package_name}" 2>&1'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            return None
            
        # Parse output for version and release fields
        version = release_ver = None
        for line in result.stdout.splitlines():
            parts = line.split(':', 1)
            if len(parts) == 2:
                key, val = parts[0].strip(), parts[1].strip()
                if key == 'Version':
                    version = val
                elif key == 'Release':
                    release_ver = val
        
        if version and release_ver:
            return {
                'package': package_name,
                'build_id': f"{version}-{release_ver}",
                'available_version': version,
                'source_rpm': f"{package_name}-{version}-{release_ver}.src.rpm",
                'timestamp': datetime.now().isoformat(),
            }
        
        return None
        
    except subprocess.TimeoutExpired:
        print(f"  Timeout querying {package_name} on {docker_image}")
        return None
    except FileNotFoundError:
        print("  Error: Docker not found")
        return None
    except Exception as e:
        print(f"  Error querying docker for {package_name}: {e}")
        return None


def local_dnf_query(package_name: str) -> Optional[Dict[str, Any]]:
    """
    Query Fedora package using local dnf installation as fallback.
    
    Tries dnf5 first (newer Fedora), falls back to dnf4.
    """
    for dnf_cmd in ['dnf5', 'dnf']:
        try:
            cmd = [dnf_cmd, 'info', package_name]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                continue
            
            version = release_ver = None
            for line in result.stdout.splitlines():
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key, val = parts[0].strip(), parts[1].strip()
                    if key == 'Version':
                        version = val
                    elif key == 'Release':
                        release_ver = val
            
            if version and release_ver:
                return {
                    'package': package_name,
                    'build_id': f"{version}-{release_ver}",
                    'available_version': version,
                    'source_rpm': f"{package_name}-{version}-{release_ver}.src.rpm",
                    'timestamp': datetime.now().isoformat(),
                }
            
        except subprocess.TimeoutExpired:
            continue
        except FileNotFoundError:
            continue
    
    return None


def query_package(package_name: str, release: str = "rawhide") -> Optional[Dict[str, Any]]:
    """
    Query package using release-specific docker container.
    
    Args:
        package_name: Name of the package to query
        release: Fedora release version
        
    Returns:
        Dict with build info or None if not found.
    """
    return docker_query(package_name, release)

# ==========================================================================
# PACKAGE MATRIX & HELPER FUNCTIONS  
# ==========================================================================

def generate_package_matrix() -> List[Dict[str, str]]:
    """Generate mapping between tracked packages and test directories."""
    return [
        {
            'package_name': pkg.lower(),
            'package_display': pkg.capitalize(),
            'test_dir': PACKAGE_TEST_DIRS.get(pkg, pkg),
            'status': 'pending',
        }
        for pkg in TRACKED_ROCM_PACKAGES
    ]


def list_tracked_packages() -> None:
    """Print list of all tracked ROCm packages."""
    print("\nTracked ROCm Packages:")
    print("-" * 40)
    for row in generate_package_matrix():
        print(f"  {row['package_name']}: -> {row['test_dir']}")

# ==========================================================================
# MAIN EXECUTION FUNCTION
# ==========================================================================

def get_parser() -> argparse.ArgumentParser:
    """Configure and return argument parser."""
    parser = argparse.ArgumentParser(
        prog='poll_fedora_builds.py',
        description='Poll Fedora release for ROCm package builds using Docker containers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 poll_fedora_builds.py -p hipblas              # Poll rawhide (default)
  python3 poll_fedora_builds.py --release f44           # Poll Fedora 44
  python3 poll_fedora_builds.py --all                   # Check all packages on release""")

    parser.add_argument('-p', '--package', type=str, default='hipblas',
                        help='Specific package to check (default: hipblas)')
    parser.add_argument('-r', '--release', choices=['rawhide', 'f45', 'f44', 'f43'], 
                        type=str, default='rawhide',
                        help='Fedora release version: rawhide, f45, f44, f43 (default: rawhide)')
    parser.add_argument('-l', '--list-packages', action='store_true', 
                        help='List all tracked ROCm packages')
    parser.add_argument('-f', '--file', type=str, default=None,
                        help='Custom state file path'),
    parser.add_argument('-a', '--all', action='store_true',
                        help='Check all tracked packages (this is the default behavior)')

    return parser


def main() -> int:
    """
    Main entry point for package build tracking per Fedora release.
    
    Returns:
        Exit code: 0 = no new changes, 1 = new builds detected (trigger tests)
    """
    args = get_parser().parse_args()
    
    # Determine state file path based on release
    if args.file:
        state_file = Path(args.file)
    else:
        state_file = get_state_file(args.release)
    
    print(f"=== Fedora ROCm Package Poller ===")
    print(f"Release: {args.release}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"State file: {state_file}")
    
    # Load saved state
    saved_raw = load_build_state(state_file)
    saved = {}
    for pkg, data in saved_raw.items():
        if isinstance(data, dict):
            saved[pkg] = data.get('build_id', '')
        else:
            saved[pkg] = str(data)
    
    # Determine which packages to check
    queries = [args.package] if args.package else TRACKED_ROCM_PACKAGES
    
    new_builds_detected = []
    no_changes = True
    
    for pkg_name in queries:
        print(f"\nChecking package: {pkg_name}")
        
        latest = query_package(pkg_name, args.release)
        if not latest:
            print(f"  Package not found or unavailable")
            continue
        
        # Compare with saved state
        last_build_id = saved.get(pkg_name.lower(), '')
        current_build_id = latest.get('build_id', '')
        
        print(f"  Last checked: {last_build_id}")
        print(f"  Current build: {current_build_id}")
        
        if last_build_id != current_build_id:
            new_builds_detected.append(latest)
            no_changes = False
            
            # Map to test directory
            for config in generate_package_matrix():
                if config['package_name'] == pkg_name.lower():
                    latest['test_dir'] = config['test_dir']
                    print(f"  Test directory: {config['test_dir']}")
                    break
    
    save_build_state(state_file, new_builds_detected)
    
    if no_changes:
        print("\n✅ No new build changes detected.")
        return 0
    else:
        print(f"\n🎉 {len(new_builds_detected)} new version(s) detected!")
        for build in new_builds_detected:
            print(f"   - {build['package']}: {build.get('available_version', 'X')} ({build.get('build_id', '')})")
        return 1


if __name__ == '__main__':
    import sys
    exit_code = main()
    sys.exit(exit_code)
