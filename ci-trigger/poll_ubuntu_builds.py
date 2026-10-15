#!/usr/bin/env python3
"""
Ubuntu ROCm Package Poller via Docker Container

Monitors Ubuntu packages using containerized apt commands.
Pattern aligned with: /home/trix/rocm/rocm-distro-containers/ubuntu/latest/apt/

Usage:
    poll_ubuntu_builds.py [options]

Options:
    -p, --package PKGNAME       Specific package to check (default: hipblas)
    -f, --file STATEFILE        State file location 
    -l, --list-packages         Show all tracked ROCm packages
    -a, --all                   Check all tracked packages (default)

Query Method:
    docker run ubuntu:latest apt-get update && apt-cache show {package}
    
Author: ROCm-Distro-Tester Team
Version: 0.6.0 (Docker-based with apt queries)
"""

import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# ==========================================================================
# CONFIGURATION - ALIGNED WITH USER'S UBUNTU CONTAINER SETUP
# ==========================================================================

TRACKED_UBUNTU_ROCM_PACKAGES = [
    'hipblas',        # HIP Basic Linear Algebra Subroutine (Ubuntu package)
    'rocblas',        # ROC BLAS 
    'rocsolver',      # ROC Solver
    'hipsolver',      # HIP solver
    'hipfft',         # HIP FFT library
    'rocfft',         # ROC FFT library
    'hip',            # HIP toolkit
    'rocm-opencl',    # ROCm OpenCL implementation
]

# Ubuntu Docker images for different releases (matches user's pattern)
UBUNTU_IMAGES = {
    'latest': 'ubuntu:latest',       # Rolling dev release
    'noble':  'ubuntu:noble',        # Ubuntu 24.04 LTS (most current stable)
    'jammy':  'ubuntu:jammy',        # Ubuntu 22.04 LTS (widely used)
    'focal':  'ubuntu:focal',        # Ubuntu 20.04 LTS (legacy support)
}

DEFAULT_UBUNTU_VERSION = 'latest'
DEFAULT_STATE_FILE = Path(__file__).parent / 'results' / 'ubuntu_build_state.json'

# ==========================================================================
# STATE MANAGEMENT FUNCTIONS
# ==========================================================================

def load_build_state(state_file: Path) -> Dict[str, Any]:
    """Load previous Ubuntu package state from file or return empty dict."""
    if not state_file.exists():
        return {}
        
    try:
        with open(state_file, 'r') as f:
            saved = json.load(f)
            if isinstance(saved, list):
                return {pkg.get('name', pkg.get('package', '')): pkg.get('last_version', '') 
                        for pkg in saved if pkg}
            elif isinstance(saved, dict):
                return saved
            return {}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Warning: Could not parse Ubuntu state file {state_file}: {e}")
        return {}


def save_build_state(state_file: Path, new_builds: List[Dict]) -> None:
    """Save updated build state to disk."""
    if not new_builds:
        print("No updates to save.")
        return
        
    raw_existing = load_build_state(state_file)
    
    existing = {}
    for pkg, value in raw_existing.items():
        if isinstance(value, str):
            existing[pkg] = {'package': pkg, 'last_version': value, 'timestamp': None}
        elif isinstance(value, dict):
            existing[pkg] = value
    
    for build in new_builds:
        pkg_name = build['package'].lower()
        existing[pkg_name] = {
            'package': build['package'],
            'last_version': str(build.get('last_version', '')),
            'timestamp': build.get('timestamp', datetime.now().isoformat()),
        }
    
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, 'w') as f:
        json.dump(list(existing.values()), f, indent=2)
    
    print(f"Saved Ubuntu package build state to {state_file}")

# ==========================================================================
# QUERY FUNCTION - APT CONTAINER QUERY (USER'S PATTERN)  
# ==========================================================================

def query_ubuntu_package(package_name: str, release: str = DEFAULT_UBUNTU_VERSION):
    """
    Query Ubuntu ROCm package info using Docker container with apt.
    
    Pattern matches: /home/trix/rocm/rocm-distro-containers/ubuntu/latest/apt/test.sh
    
    Usage inside container: 
        apt-get update                       # Refresh package database
        apt-cache show {package}             # Show details (includes version)
        
    Args:
        package_name: Name of the package to query
        release: Ubuntu release name (latest, noble, jammy, focal)
        
    Returns:
        Dict with package metadata including version/info,
        or None if package not found or error occurs.
    """
    
    docker_image = UBUNTU_IMAGES.get(release, 'ubuntu:latest')
    
    try:
        # Pattern exactly from user's test.sh approach - update then query
        cmd = f'apt-get update >/dev/null 2>&1 && apt-cache show "{package_name}"'
        
        result = subprocess.run(
            ['docker', 'run', '--rm', docker_image, 'sh', '-c', cmd],
            capture_output=True,
            text=True,
            timeout=300  # Long timeout for apt update + query
        )
        
        if result.returncode == 0 and package_name.lower() in result.stdout.lower():
            output = result.stdout
            
            # Parse apt-cache show output format (similar to dnf/pacman):
            # Package: hipblas
            # Version: 12.3.4-5ubuntu1
            # Architecture: amd64
            # ... etc
            
            version = pkg_name = None
            for line in output.splitlines():
                if ':' in line.strip():
                    key, val = line.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    
                    if key == 'package':
                        pkg_name = val
                    elif key == 'version':
                        version = val
            
            if version and pkg_name:
                return {
                    'package': pkg_name,
                    'last_version': version,              # Version as state identifier
                    'ubuntu_release': release,
                    'timestamp': datetime.now().isoformat(),
                    'source': f'Ubuntu {release}',
                }
        
        if result.returncode != 0:
            print(f"Package '{package_name}' not found via apt-cache")
            return None
        
        print(f"Package '{package_name}' query returned empty output")
        return None
        
    except subprocess.TimeoutExpired:
        print(f"  Timeout querying {package_name}")
        return None
    except FileNotFoundError:
        print("  Error: Docker not available")
        return None
    except Exception as e:
        print(f"  Error query: {e}")
        return None


# ==========================================================================
# MAIN EXECUTION FUNCTION
# ==========================================================================

def get_parser() -> argparse.ArgumentParser:
    """Configure argument parser."""
    parser = argparse.ArgumentParser(
        prog='poll_ubuntu_builds.py',
        description='Poll Ubuntu ROCm packages using apt queries in containers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Workflow (matching your container setup):
  # Container build (your pattern)
  cd /home/trix/rocm/rocm-distro-containers/ubuntu/latest/apt && ./run.sh
  
  # Query packages programmatically
  python3 poll_ubuntu_builds.py -p hipblas                 # Poll Ubuntu (default)
  python3 poll_ubuntu_builds.py --release noble -p rocblas # Specific release""")

    parser.add_argument('-p', '--package', type=str, default='hipblas',
                        help='Specific package to check (default: hipblas)')
    parser.add_argument('-l', '--list-packages', action='store_true', 
                        help='List all tracked Ubuntu ROCm packages')
    parser.add_argument('-f', '--file', type=str, default=None,
                        help='Custom state file path'),
    parser.add_argument('-r', '--release', choices=['latest', 'noble', 'jammy', 'focal'], 
                        type=str, default='latest',
                        help='Ubuntu release version: latest, noble, jammy, focal (default: latest)'),
    parser.add_argument('-a', '--all', action='store_true',
                        help='Check all tracked packages (default behavior)')

    return parser


def main() -> int:
    """
    Main entry point for package build tracking.
    
    Follows pattern from /home/trix/rocm/rocm-distro-containers/ubuntu/latest/apt/
    - Uses ubuntu:{release} Docker containers (your method)
    - Uses apt-get update && apt-cache show queries (your method)
    """
    args = get_parser().parse_args()
    
    state_file = Path(args.file) if args.file else DEFAULT_STATE_FILE
    
    print(f"=== Ubuntu ROCm Package Poller ===")
    print(f"Ubuntu release: {args.release}")
    print(f"Docker image: {UBUNTU_IMAGES[args.release]}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"State file: {state_file}")
    
    # Show package list if requested
    if args.list_packages:
        print("\n✓ Tracked ROCm packages on Ubuntu:")
        for pkg in TRACKED_UBUNTU_ROCM_PACKAGES:
            print(f"   - {pkg}")
        return 0
    
    saved_raw = load_build_state(state_file)
    saved = {}
    for pkg, data in saved_raw.items():
        if isinstance(data, dict):
            saved[pkg] = data.get('last_version', '')
        else:
            saved[pkg] = str(data)
    
    queries = [args.package] if args.package else TRACKED_UBUNTU_ROCM_PACKAGES
    
    new_builds_detected = []
    no_changes = True
    
    for pkg_name in queries:
        print(f"\nChecking package: {pkg_name}")
        
        latest = query_ubuntu_package(pkg_name, args.release)
        
        if not latest:
            print(f"  Not found or unavailable")
            continue
        
        last_version = saved.get(pkg_name.lower(), '')
        current_version = latest.get('last_version', '')
        
        print(f"  Last checked: {last_version}")
        print(f"  Current version: {current_version}")
        
        if last_version != current_version:
            new_builds_detected.append(latest)
            no_changes = False
    
    save_build_state(state_file, new_builds_detected)
    
    if no_changes:
        print("\n✅ No Ubuntu package version updates detected.")
        return 0
    else:
        print(f"\n🎉 {len(new_builds_detected)} Ubuntu version(s) detected!")
        for build in new_builds_detected:
            pkg_name = build.get('package', 'unknown')
            ver = build.get('last_version', 'X')
            release = build.get('ubuntu_release', 'latest')
            print(f"   - {pkg_name}: {ver} (Ubuntu {release})")
        return 1


if __name__ == '__main__':
    import sys
    exit_code = main()
    sys.exit(exit_code)
