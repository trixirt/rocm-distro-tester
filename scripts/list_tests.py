#!/usr/bin/env python3
"""list_tests.py - Inventory tool for the ROCm Test Registry.

Queries the test-tier registry (rocm-builder:5000) and displays a 
human-readable or JSON-formatted table of every available package tag,
or provides concise input for verify_single_image.sh via the --brief option.

Compatible with Python 3.6+.

Usage:
    ./scripts/list_tests.py                    # Human-readable table
    ./scripts/list_tests.py --json             # Raw JSON catalog output
    ./scripts/list_tests.py hipblas            # Filter by pattern
    ./scripts/list_tests.py --brief            # List of <repo>:<tag> inputs for verification
"""

import argparse
import json
import os
import subprocess
import sys
from typing import List, Optional
from urllib.request import urlopen, Request


def resolve_alias(alias: str) -> Optional[str]:
    """Resolve a LAN alias (e.g., rocm-builder) without relying on DNS.

    Uses the same resolution strategy as verify_registry_test.sh:
    1. getent hosts (DNS + /etc/hosts)
    2. Direct parsing of /etc/hosts fallback if needed.
    """
    try:
        res = subprocess.run(
            ["getent", "hosts", alias], capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split()[0]
    except FileNotFoundError:
        pass

    # Strict /etc/hosts fallback
    try:
        with open("/etc/hosts") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) > 1 and alias in parts:
                    return parts[0]
    except (IOError, OSError):
        pass

    return None


def fetch_json(url: str) -> dict:
    """Fetch a URL and parse the result as JSON."""
    req = Request(url)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON from {url}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Connection failed for {url}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="List available test images in the registry.")
    parser.add_argument("pattern", nargs="?", help="Filter repository names by pattern.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON catalog data.")
    parser.add_argument("-b", "--brief", action="store_true", 
                        help="Concise list of inputs for verify_single_image.sh (e.g. 'repo:tag')")
    
    args = parser.parse_args()

    alias = os.getenv("REGISTRY_ALIAS", "rocm-builder")
    port = int(os.getenv("REGISTRY_PORT", "5000"))

    if not args.brief and not args.json:
        print(f"[RESOLVING] Checking {alias}:{port}...", file=sys.stderr)

    target_ip = resolve_alias(alias)
    if not target_ip:
        print(f"❌ Could not resolve '{alias}'. Check DNS or /etc/hosts.", file=sys.stderr)
        sys.exit(1)

    base_url = f"http://{target_ip}:{port}"

    # Fetch catalog
    if not args.brief and not args.json:
        print("[FETCHING] Getting registry catalog...", file=sys.stderr)
    
    catalog_data = fetch_json(f"{base_url}/v2/_catalog")
    repos: List[str] = catalog_data.get("repositories", [])

    if args.json:
        print(json.dumps(catalog_data, indent=2))
        return

    # --- Brief Output (Concise inputs for verify_single_image.sh) ---
    if args.brief:
        filtered_repos = [r for r in repos if not args.pattern or args.pattern.lower() in r.lower()]
        
        count = 0
        for repo in sorted(filtered_repos):
            tag_data = fetch_json(f"{base_url}/v2/{repo}/tags/list")
            for tag in sorted(tag_data.get("tags", [])):
                print(f"{repo}:{tag}")
                count += 1
        
        if count == 0:
            print("✅ No test images found matching criteria.", file=sys.stderr)
        return

    # --- Table Output ---
    filtered_repos = [r for r in repos if not args.pattern or args.pattern.lower() in r.lower()]
    
    if not filtered_repos:
        print("✅ No test images found matching criteria.")
        return

    print(f"\n{'PACKAGE':<30} {'DISTRO / RELEASE':<40} {'TAG LIST'}")
    print("-" * 120)

    for repo in sorted(filtered_repos):
        # Fetch tags for this specific package
        tag_data = fetch_json(f"{base_url}/v2/{repo}/tags/list")
        tags: List[str] = tag_data.get("tags", [])
        
        # Format columns based on standard naming (pkg-distro-release)
        parts = repo.split("-")
        pkg_name: str = parts[0] if len(parts) >1 else repo
        
        # For display, we show the repo minus the package name as "Distro/Release"
        distro_display: str = ",".join(parts[1:]) if len(parts) > 1 else repo
        
        tag_str = ", ".join(tags)
        
        # Truncate long tag lists for readability
        max_tag_len = 50
        display_tags = tag_str[:max_tag_len] + ("..." if len(tag_str) > max_tag_len else "")

        print(f"{pkg_name:<30} {distro_display:<40} | {display_tags}")

    print("-" * 120)
    print(f"💾 Total packages: {len(filtered_repos)}")


if __name__ == "__main__":
    main()
