#!/usr/bin/env python3
"""
ArchLinux Package Build Poller for ROCm Packages

Monitors ArchLinux repositories and the AUR API for new package builds of tracked packages.
Records last-checked state to enable efficient incremental polling.

Note: For official ROCm packages on Arch, we check the official repo and Arch User Repository (AUR).
Arch Linux does not use Koji but provides a simpler package database API.

Usage:
    poll-archlinux-builds.py [options]

Options:
    --package PKGNAME       Specific package to check (default: hipblas)
    --list-packages         Show all tracked ROCm packages
    -f, --file STATEFILE    State file location (default: ci-trigger/results/arch_build_state.json)
    --all                   Check all tracked packages

API Endpoints Used:
    https://wiki.archlinux.org/title/Official_repositories_database#Package_Repository_API
    https://archlinux.org/packages/search/?q=package_name
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

# ArchLinux packages to monitor for ROCm testing
TRACKED_ARCH_PACKAGES = [
    'hip',            # HIP toolkit
    'rocminfo',       # ROCm information tool
    'rocm-opencl',    # ROCm OpenCL implementation  
    'hipblas',        # HIP BLAS (if available in Arch)
    'rocblas',        # ROC BLAS (if available in Arch)
]

# Base URLs for ArchLinux package APIs
ARCHPKG_SEARCH_URL = "https://archlinux.org/packages/search/"
ARCHPKG_JSON_API = "https://archlinux.org/packages/json/"

# State tracking file (stores last build date/version per package)
DEFAULT_STATE_FILE = Path(__file__).parent / 'results' / 'arch_build_state.json'


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_arch_build_state(state_file: Path) -> Dict[str, str]:
    """Load previous ArchLinux package build state from file or return empty dict."""
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                saved_state = json.load(f)
                # Extract just the last version checked per package
                return {
                    pkg['name']: pkg.get('last_version', '') 
                    for pkg in saved_state
                }
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse state file, starting fresh: {e}")
    return {}


def save_arch_build_state(state_file: Path, new_changes: List[Dict]):
    """Save updated build state to disk."""
    if not new_changes:
        # No changes detected, just preserve existing state
        saved_state = load_arch_build_state(state_file)
        with open(state_file, 'w') as f:
            json.dump(list(saved_state.values()), f, indent=2)
        return
    
    updated_state = {}
    
    if state_file.exists():
        try:
            saved_state = load_arch_build_state(state_file)
        except:
            saved_state = {}
        
        updated_state = dict(saved_state)
    
    # Update with new changes
    for change in new_changes:
        pkg_name = change['package'].lower()
        updated_state[pkg_name] = {
            'package': change['package'],
            'last_version': change.get('version', 'unknown'),
            'last_build_date': change.get('timestamp', ''),
            'repo': change.get('repo', 'archlinux')
        }
    
    with open(state_file, 'w') as f:
        json.dump(list(updated_state.values()), f, indent=2)


def query_archlinux_api(package_name: str) -> Optional[Dict]:
    """Query ArchLinux APIs for latest package information."""
    pkg_name_safe = package_name.lower().replace('-', '_')
    
    try:
        # First, try official repository search
        search_url = f"{ARCHPKG_SEARCH_URL}?q={package_name}"
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        
        html_content = response.text
        
        # We need to extract package info from HTML (Arch doesn't provide pure JSON for searches)
        # Parse search results using basic HTML parsing or regex
        import re
        
        # Look for package details in search results page
        # Example: <div class="pkg">hip 5.0.0-1</div>
        
        pkg_matches = re.findall(
            r'<a href="/packages/([^"]+)".*?>([^<]+)</a>\s*\(\s*([^)]+)\)',
            html_content[:5000]  # Search first results only
        )
        
        for match in pkg_matches:
            pkg_path, pkg_version, repo_name = match
            
            if pkg_path.lower() == package_name.lower():
                return {
                    'package': package_name.capitalize(),
                    'version': pkg_version,
                    'release_date': datetime.now().isoformat(),
                    'repo': repo_name.strip(' ()'),
                    'available_in_arch': True
                }
        
        # If not found in official repos, check AUR via API
        aur_api_url = f"https://aur.archlinux.org/rpc?v=5&type=info&arg={package_name}"
        aur_response = requests.get(aur_api_url, timeout=10)
        
        if aur_response.status_code == 200:
            aur_data = aur_response.json()
            
            if 'results' in aur_data and len(aur_data['results']) > 0:
                aur_pkg = aur_data['results'][0]
                
                return {
                    'package': package_name.capitalize(),
                    'version': f"{aur_pkg.get('Version', 'unknown')}-{aur_pkg.get('NumVotes', '?')}",
                    'release_date': datetime.fromtimestamp(aur_pkg.get('LastModified', 0)).isoformat(),
                    'repo': 'AUR',
                    'available_in_arch': False,
                    'aur_url': f"https://aur.archlinux.org/packages/{package_name.lower()}"
                }
        
        print(f"No build found for package: {package_name}")
        return None
        
    except requests.RequestException as e:
        print(f"Error querying ArchLinux APIs: {e}")
        return None


def generate_arch_test_matrix() -> List[Dict]:
    """Generate mapping between tracked packages and test directories."""
    matrix = []
    
    # Define package to test directory mappings for Arch tests
    arch_package_config = {
        'hip': ('hip', 'hipblas-test'),
        'rocminfo': ('rocminfo', 'rocm-info-test'),
        'rocm-opencl': ('rocm-opencl', 'rocm-opencl-test'),
        'hipblas': ('hipblas', 'hipblas-arch-test'),
        'rocblas': ('rocblas', 'rocblas-arch-test'),
    }
    
    for pkg in TRACKED_ARCH_PACKAGES:
        matrix.append({
            'package_name': pkg.lower(),
            'package_display': pkg.capitalize(),
            'test_dir': arch_package_config.get(pkg, (pkg, f'{pkg}-test'))[-1],
            'arch_specific': True,
        })
    
    return matrix


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main entry point for package build tracking on ArchLinux."""
    parser = argparse.ArgumentParser(
        description='Poll ArchLinux repositories for ROCm package updates'
    )
    
    parser.add_argument(
        '--package', '-p',
        help='Specific package to check (default: all tracked packages)'
    )
    parser.add_argument(
        '--list-packages', '-l',
        action='store_true',
        help='Show all tracked ROCm packages'
    )
    parser.add_argument(
        '--file', '-f',
        type=Path,
        default=DEFAULT_STATE_FILE,
        help=f'State file location (default: {DEFAULT_STATE_FILE})'
    )
    parser.add_argument(
        '--archlinux', '-a', 
        action='store_true',
        help='Alias for --all packages (ArchLinux)'
    )
    
    args = parser.parse_args()
    
    # Initialize paths
    state_file = args.file
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load previous state
    saved_state = load_arch_build_state(state_file) if not args.file.exists() else {}
    
    print(f"=== ArchLinux Package Build Poller ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"State file: {state_file}")
    
    # Determine which packages to check
    check_list = []
    
    if args.package:
        check_list = [args.package]
    elif args.list_packages:
        check_list = TRACKED_ARCH_PACKAGES + ['--list-packages']
    else:
        check_list = TRACKED_ARCH_PACKAGES
    
    # Print package list if requested
    if args.list_packages or ('--list-packages' in check_list):
        print(f"\n✓ Tracked ROCm packages on ArchLinux:")
        for pkg in TRACKED_ARCH_PACKAGES:
            print(f"   - {pkg}")
        return 0
    
    new_changes_detected = []
    no_changes = True
    
    for pkg_name in check_list:
        print(f"\nChecking package: {pkg_name} on ArchLinux")
        
        latest = query_archlinux_api(pkg_name)
        
        if not latest:
            continue
        
        # Compare against previously saved version
        last_version = saved_state.get(pkg_name, {}).get('last_version', '')
        current_version = latest.get('version', 'unknown')
        
        print(f"  Previously checked (Arch build): {last_version}")
        print(f"  Current version: {current_version}")
        print(f"  Available in Arch repo: {latest.get('available_in_arch', False)}")
        
        # If versions differ, this is a new update
        if last_version != current_version:
            new_changes_detected.append(latest)
            no_changes = False
            
            # Map to appropriate test directory for Arch-specific testing
            for config in generate_arch_test_matrix():
                if config['package_name'] == pkg_name.lower():
                    latest['arch_test_dir'] = config['test_dir']
                    print(f"  📁 Arch test directory: {config['test_dir']}")
                    break
    
    # Save state with any new changes detected
    save_arch_build_state(state_file, new_changes_detected)
    
    # Report results
    if no_changes:
        print("\n✅ No ArchLinux package version updates detected for tracked packages.")
        return 0
    else:
        print(f"\n🎉 {len(new_changes_detected)} ArchLinux package update(s) detected!")
        for change in new_changes_detected:
            location = "AUR 📚" if not change.get('available_in_arch', True) else "Official Repo ✅"
            print(f"   - {change['package']}: v{change['version']} ({location})")
        
        return 1


if __name__ == '__main__':
    main()
