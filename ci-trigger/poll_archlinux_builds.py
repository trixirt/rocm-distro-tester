#!/usr/bin/env python3
"""
ArchLinux ROCm Package Poller via Docker Container

Monitors ArchLinux packages using containerized pacman queries.
Pattern aligned with: /home/trix/rocm/rocm-distro-containers/archlinux/pacman/

Usage:
    poll_archlinux_builds.py [options]

Options:
    -p, --package PKGNAME       Specific package to check (default: hip)
    -f, --file STATEFILE        State file location 
    -l, --list-packages         Show all tracked ROCm packages
    -a, --all                   Check all tracked packages (default)

Query Method:
    docker run archlinux:latest pacman -Si {package}
    
Author: ROCm-Distro-Tester Team
Version: 0.6.0 (Docker-based with pacman queries)
"""

import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# ==========================================================================
# CONFIGURATION - ALIGNED WITH USER'S ARCH LINUX SETUP
# ==========================================================================

TRACKED_ARCH_ROCM_PACKAGES = [
    'hip',           # HIP toolkit
    'rocminfo',      # ROCm information tool
    'rocm-opencl',   # ROCm OpenCL implementation  
    'hipblas',       # HIP BLAS
    'rocblas',       # ROC BLAS
]

# Arch Linux base Docker image (matches user's example)
ARCH_DOCKER_IMAGE = 'archlinux:latest'

DEFAULT_STATE_FILE = Path(__file__).parent / 'results' / 'arch_build_state.json'

# ==========================================================================
# STATE MANAGEMENT FUNCTIONS
# ==========================================================================

def load_build_state(state_file: Path) -> Dict[str, Any]:
    """Load previous ArchLinux package state from file or return empty dict."""
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
        print(f"Warning: Could not parse ArchLinux state file {state_file}: {e}")
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
    
    print(f"Saved ArchLinux build state to {state_file}")

# ==========================================================================
# QUERY FUNCTION - PACMAN CONTAINER QUERY (USER'S PATTERN)
# ==========================================================================

def query_archlinux_package(package_name: str) -> Optional[Dict[str, Any]]:
    """
    Query ArchLinux package info using Docker container with pacman.
    
    Pattern matches: /home/trix/rocm/rocm-distro-containers/archlinux/pacman/test.sh
    
    Usage inside container: 
        pacman -Sy                         # Update database
        pacman -Si {package_name}          # Show package info in detail
        
    Args:
        package_name: Name of the package to query
        
    Returns:
        Dict with package metadata including version/info,
        or None if package not found or error occurs.
    """
    try:
        # Pattern exactly from user's test.sh approach - minimal setup needed
        # pacman -Si outputs detailed package information in human-readable format
        cmd = f'pacman -Sy > /dev/null 2>&1 && pacman -Si "{package_name}"'
        
        result = subprocess.run(
            ['docker', 'run', '--rm', ARCH_DOCKER_IMAGE, 'sh', '-c', cmd],
            capture_output=True,
            text=True,
            timeout=300  # Long timeout for pacman sync and query
        )
        
        if result.returncode == 0 and package_name.lower() in result.stdout.lower():
            output = result.stdout
            
            # Parse pacman -Si output format (similar to dnf):
            # Package Name           : hip
            # Version                : 5.6.0-1
            # Description            : Heterogeneous-Computing Interface for Precomputers
            # ... etc
            
            version = pkg_name = pkg_desc = available_on_system = None
            in_package_section = False
            
            for line in output.splitlines():
                if ':' in line.strip():
                    key, val = line.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    
                    if key == 'package name':
                        pkg_name = val
                    elif key == 'version':
                        version = val
                    elif key == 'description':
                        pkg_desc = val
            
            if version and pkg_name:
                return {
                    'package': pkg_name,
                    'last_version': version,              # Version as state identifier
                    'available_on_system': True,          # Found in repo (synced)
                    'version_raw': version,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'Arch Linux official repository',
                }
        
        print(f"Package '{package_name}' not found via pacman")
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
        prog='poll_archlinux_builds.py',
        description='Poll ArchLinux ROCm packages using DNF repoquery in containers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Workflow (matching your container setup):
  # Container build (your pattern)
  cd /home/trix/rocm/rocm-distro-containers/archlinux/pacman && ./run.sh
  
  # Query packages programmatically
  python3 poll_archlinux_builds.py -p hip                  # Poll Arch Linux
  python3 poll_archlinux_builds.py --all                   # Check all packages""")

    parser.add_argument('-p', '--package', type=str, default='hip',
                        help='Specific package to check (default: hip)')
    parser.add_argument('-l', '--list-packages', action='store_true', 
                        help='List all tracked Arch Linux ROCm packages')
    parser.add_argument('-f', '--file', type=str, default=None,
                        help='Custom state file path'),
    parser.add_argument('-a', '--all', action='store_true',
                        help='Check all tracked packages (default behavior)')

    return parser


def main() -> int:
    """
    Main entry point for package build tracking.
    
    Follows pattern from /home/trix/rocm/rocm-distro-containers/archlinux/pacman/
    - Uses archlinux:latest Docker container (your method)
    - Uses pacman -Si queries (your method)
    """
    args = get_parser().parse_args()
    
    state_file = Path(args.file) if args.file else DEFAULT_STATE_FILE
    
    print(f"=== ArchLinux ROCm Package Poller ===")
    print(f"Container: {ARCH_DOCKER_IMAGE}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"State file: {state_file}")
    
    # Show package list if requested
    if args.list_packages:
        print("\n✓ Tracked ROCm packages on ArchLinux:")
        for pkg in TRACKED_ARCH_ROCM_PACKAGES:
            print(f"   - {pkg}")
        return 0
    
    # Load saved state for Arch Linux version tracking
    saved_raw = load_build_state(state_file)
    saved = {}
    for pkg, data in saved_raw.items():
        if isinstance(data, dict):
            saved[pkg] = data.get('last_version', '')
        else:
            saved[pkg] = str(data)
    
    # Determine which packages to check
    queries = [args.package] if args.package else TRACKED_ARCH_ROCM_PACKAGES
    
    new_builds_detected = []
    no_changes = True
    
    for pkg_name in queries:
        print(f"\nChecking package: {pkg_name}")
        
        latest = query_archlinux_package(pkg_name)
        
        if not latest:
            print(f"  Not found")
            continue
        
        last_version = saved.get(pkg_name.lower(), '')
        current_version = latest.get('last_version', '')
        
        print(f"  Last checked: {last_version}")
        print(f"  Current version: {current_version}")
        print(f"  Available on system: {latest.get('available_on_system', False)}")
        
        if last_version != current_version:
            new_builds_detected.append(latest)
            no_changes = False
    
    save_build_state(state_file, new_builds_detected)
    
    if no_changes:
        print("\n✅ No Arch Linux package version updates detected.")
        return 0
    else:
        print(f"\n🎉 {len(new_builds_detected)} Arch Linux version(s) detected!")
        for build in new_builds_detected:
            pkg_name = build.get('package', 'unknown')
            ver = build.get('last_version', 'X')
            print(f"   - {pkg_name}: {ver} (Arch official repo)")
        return 1


if __name__ == '__main__':
    import sys
    exit_code = main()
    sys.exit(exit_code)
