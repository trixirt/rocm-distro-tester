#!/usr/bin/env python3
"""
EPEL/RHEL ROCm Package Poller via Docker Container

Pattern aligned with /home/trix/rocm/rocm-distro-containers/rhel/10/dnf/
- Uses direct EPEL RPM installation 
- Uses dnf repoquery -i for detailed package metadata

Usage:
    poll_epel_builds.py [options]

Options:
    -p, --package PKGNAME       Specific package to check (default: hipblas)
    -r, --release RELEASE       Release version (10 or 9)
    -l, --list-packages         Show all tracked EPEL ROCm packages
    -f, --file STATEFILE        State file location 
    -a, --all                   Check all tracked packages (default)

Query Method:
    docker run quay.io/centos/centos:stream{release} \
        dnf repoquery -i {package_name}
    
Author: ROCm-Distro-Tester Team
Version: 0.5.0 (Aligned with user example pattern)
"""

import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Configuration - matches /home/trix/rocm structure exactly
TRACKED_RHEL_ROCM_PACKAGES = [
    'hipblas', 'rocblas', 'hipsolver', 'rocsolver',
    'hipfft', 'rocfft', 'hipsparse', 'rocsparse', 'rccl'
]

RELEASE_IMAGES = {
    '10': 'quay.io/centos/centos:stream10',
    '9':  'quay.io/centos/centos:stream9',
}

EPEL_RELEASE_URLS = {
    '10': 'https://dl.fedoraproject.org/pub/epel/epel-release-latest-10.noarch.rpm',
    '9':  'https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm',
}

DEFAULT_STATE_FILE = Path(__file__).parent / 'results'

# State management functions (same as before)
def get_state_file(release: str) -> Path:
    return DEFAULT_STATE_FILE / f"epel_{release}_build_state.json"


def load_build_state(state_file: Path):
    if not state_file.exists():
        return {}
    try:
        with open(state_file, 'r') as f:
            saved = json.load(f)
            if isinstance(saved, list):
                return {pkg.get('name', pkg.get('package', '')): pkg.get('build_id', '') for pkg in saved if pkg}
            elif isinstance(saved, dict):
                return saved
        return {}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Warning: Could not parse EPEL state file {state_file}: {e}")
        return {}


def save_build_state(state_file: Path, new_builds: List[Dict]):
    if not new_builds:
        print("No updates to save.")
        return
        
    raw_existing = load_build_state(state_file)
    
    existing = {}
    for pkg, value in raw_existing.items():
        if isinstance(value, str):
            existing[pkg] = {'package': pkg, 'build_id': value, 'timestamp': None}
        elif isinstance(value, dict):
            existing[pkg] = value
    
    for build in new_builds:
        pkg_name = build['package'].lower()
        existing[pkg_name] = {
            'package': build['package'],
            'build_id': str(build.get('build_id', '')),
            'timestamp': build.get('timestamp', datetime.now().isoformat()),
        }
    
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, 'w') as f:
        json.dump(list(existing.values()), f, indent=2)
    
    print(f"Saved build state to {state_file}")

# Query function matching user's test.sh pattern exactly
def query_epel_package(package_name: str, release: str = "10"):
    """
    Query RHEL EPEL package using dnf repoquery -i.
    Pattern: Matches /home/trix/rocm/rocm-distro-containers/rhel/10/dnf/test.sh
    
    Usage inside container: dnf repoquery -i {package_name}
    First installs epel-release rpm, then queries for package details
    """
    
    docker_image = RELEASE_IMAGES.get(release, f"quay.io/centos/centos:stream{release}")
    epel_rpm_url = EPEL_RELEASE_URLS.get(str(release))
    
    if not epel_rpm_url:
        print(f"  No EPEL URL defined for release {release}")
        return None
    
    try:
        # Match your exact pattern - install EPEL, then query with repoquery
        cmd = f'dnf update -y >/dev/null 2>&1 && dnf install -y {epel_rpm_url} || true && dnf repoquery -i "{package_name}"'
        
        result = subprocess.run(
            ['docker', 'run', '--rm', docker_image, 'sh', '-c', cmd],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0 and package_name in result.stdout:
            output = result.stdout
            
            # Parse dnf repoquery -i format (same as user's approach)
            version = release_ver = None
            for line in output.splitlines():
                if ':' in line.strip():
                    key, val = line.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    
                    if key == 'version':
                        version = val
                    elif key == 'release':
                        release_ver = val
            
            if version and release_ver:
                return {
                    'package': package_name,
                    'build_id': f"{version}",
                    'available_version': version,
                    'rpm_release': release_ver,
                    'timestamp': datetime.now().isoformat(),
                    'distro': f"RHEL/CentOS Stream {release_ver or release}",
                }
        
        print(f"Package '{package_name}' not found via dnf repoquery")
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


# Main execution
def get_parser():
    parser = argparse.ArgumentParser(
        prog='poll_epel_builds.py',
        description='Poll EPEL/RHEL for ROCm packages using DNF repoquery (user pattern)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Workflow matching your Docker setup:
  # Container build (your method)
  cd /home/trix/rocm/rocm-distro-containers/rhel/10/dnf && ./run.sh
  
  # Programmatic queries
  python3 poll_epel_builds.py -p hipblas              # Poll RHEL 10
  python3 poll_epel_builds.py --release 9             # Poll RHEL 9""")

    parser.add_argument('-p', '--package', type=str, default='hipblas')
    parser.add_argument('-r', '--release', choices=['10', '9'], 
                        type=str, default='10')
    parser.add_argument('-l', '--list-packages', action='store_true')
    parser.add_argument('-f', '--file', type=str, default=None)
    parser.add_argument('-a', '--all', action='store_true')

    return parser


def main():
    args = get_parser().parse_args()
    
    state_file = Path(args.file) if args.file else get_state_file(args.release)
    
    print(f"=== EPEL/RHEL ROCm Package Poller ===")
    print(f"Release: {args.release}")
    print(f"Container: {RELEASE_IMAGES[args.release]}")
    print(f"EPEL RPM: {EPEL_RELEASE_URLS[args.release]}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"State file: {state_file}")
    
    saved_raw = load_build_state(state_file)
    saved = {}
    for pkg, data in saved_raw.items():
        if isinstance(data, dict):
            saved[pkg] = data.get('build_id', '')
        else:
            saved[pkg] = str(data)
    
    queries = [args.package] if args.package else TRACKED_RHEL_ROCM_PACKAGES
    
    new_builds_detected = []
    no_changes = True
    
    for pkg_name in queries:
        print(f"\nChecking package: {pkg_name}")
        
        latest = query_epel_package(pkg_name, args.release)
        
        if not latest:
            print(f"  Not found")
            continue
        
        last_build_id = saved.get(pkg_name.lower(), '')
        current_build_id = latest.get('build_id', '')
        
        print(f"  Last checked: {last_build_id}")
        print(f"  Current version: {current_build_id}")
        
        if last_build_id != current_build_id:
            new_builds_detected.append(latest)
            no_changes = False
    
    save_build_state(state_file, new_builds_detected)
    
    if no_changes:
        print("\n✅ No new build changes detected.")
        return 0
    else:
        print(f"\n🎉 {len(new_builds_detected)} new version(s) detected!")
        for build in new_builds_detected:
            pkg_name = build.get('package', 'unknown')
            ver = build.get('available_version', 'X')
            release_ver = build.get('rpm_release', '')
            print(f"   - {pkg_name}: {ver} (release: {release_ver or args.release})")
        return 1


if __name__ == '__main__':
    import sys
    exit_code = main()
    sys.exit(exit_code)
