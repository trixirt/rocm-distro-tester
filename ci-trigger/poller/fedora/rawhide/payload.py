#!/usr/bin/env python3
"""Fedora ROCm Package Poller - Docker Service Edition (v1.0)

Architecture: Manager Mode. This script acts as a controller for the builder's
Docker daemon, spinning up ephemeral Fedora containers to inspect package versions
without relying on local cached metadata.
"""
import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime

# Constants / Configuration
PACKAGE_FILE = Path("/etc/poller-data/packages.txt")
STATE_DIR = Path("/etc/poller-data/state")
HEALTHY_STATES = ["running", "healthy"]

def get_state_file():
    return STATE_DIR / "rawhide_build_state.json"

def load_package_list():
    """Reads the dynamic list of packages to track."""
    if not PACKAGE_FILE.exists():
        raise FileNotFoundError(f"Package list not found at {PACKAGE_FILE}")
    
    with open(PACKAGE_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def refresh_dnf_metadata():
    """Force a full metadata reload from upstream repositories."""
    print("🔄 [SYSTEM] Refreshing DNF metadata...", flush=True)
    try:
        # 1. Clean the cache completely to ensure zero stale data
        subprocess.run(["dnf", "clean", "all"], capture_output=True, text=True)
        
        # 2. Fetch only the headers (fastest way to find version updates)
        result = subprocess.run(["dnf", "makecache", "fast"], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"⚠️ [SYSTEM] DNF metadata refresh failed: {result.stderr}", flush=True)
            return False
        return True
    except Exception as e:
        print(f"🚨 [SYSTEM] Error during DNF refresh: {e}", flush=True)
        return False

def query_package_via_docker(pkg_name):
    """Query Fedora package info using Docker container for rawhide."""
    docker_registry = os.environ.get("FEDORA_DOCKREGISTRY", "fedora:rawhide")
    
    print(f"  📦 Checking {pkg_name} on ({docker_registry})", flush=True)
    
    try:
        cmd = [
            'docker', 'run', '--rm', docker_registry,
            'sh', '-c', f'version=$(dnf -y list --showduplicates "{pkg_name}" 2>/dev/null | grep version | tail -n1 | awk \'{print $2}\'); echo "$version"'
        ]
        
        # If we can't find it, let subprocess handle the noise and return failure
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        
        version = result.stdout.strip()
        if version:
            print(f"  ✅ Found version: {version}", flush=True)
            return {
                'package': pkg_name,
                'build_id': version,
                'timestamp': datetime.now().isoformat(),
                'status': 'available'
            }
        
    except subprocess.TimeoutExpired:
        print(f"  ⏰ Timeout querying {pkg_name} on {docker_registry}", flush=True)
    except Exception as e:
        print(f"  ❌ Docker error for {pkg_name}: {e}", flush=True)
        
    return None

def load_state(state_file):
    if not state_file.exists():
        return {}
    try:
        with open(state_file, 'r') as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"⚠️ Could not parse state file, treating as empty: {e}", flush=True)
        return {}

def main():
    print(f"\n=== Fedora ROCm Package Poller === Timestamp: {datetime.now().isoformat()}", flush=True)
    
    # 1. Get list of packages to test
    try:
        packages = load_package_list()
        print(f"Loading packages from {PACKAGE_FILE} ({len(packages)} items)", flush=True)
    except Exception as e:
        print(f"FATAL: {e}", flush=True)
        return 2

    # 2. Mandatory Pre-flight DNF refresh
    if not refresh_dnf_metadata():
        print("FATAL: Could not update metadata, exiting.", flush=True)
        return 1

    # 3. Iterate and Query
    state_file = get_state_file()
    saved_state = load_state(state_file)
    new_builds_detected = []
    
    for pkg in packages:
        found = query_package_via_docker(pkg)
        
        if found:
            current_id = found['build_id']
            last_id = saved_state.get(pkg.lower(), {}).get('build_id', '')
            
            if current_id != last_id:
                print(f"🆕 New version detected for {pkg}!", flush=True)
                new_builds_detected.append(found)
                
                # Update local state tracker
                saved_state[pkg.lower()] = found
    
    # 4. Report and Exit
    save_build_state(state_file, new_builds_detected)
    
    if new_builds_detected:
        print(f"\n🎉 {len(new_builds_detected)} new version(s) detected!", flush=True)
        for build in new_builds_detected:
            print(f"   - {build['package']}: {build.get('build_id', '')}", flush=True)
        return 1
    else:
        print("\n✅ No new builds to report.", flush=True)
        return 0

if __name__ == '__main__':
    sys.exit(main())
