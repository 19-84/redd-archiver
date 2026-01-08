#!/usr/bin/env python3
"""
ABOUTME: Convert GitHub issue template submissions to registry JSON format
ABOUTME: Helper script for maintainers to process new instance registrations

Usage:
    python issue-to-registry.py --issue-number 123
    python issue-to-registry.py --from-clipboard

This script reads a GitHub issue created with the register-instance.yml template,
fetches the instance API to auto-populate fields, and generates a properly
formatted JSON file for the registry.
"""

import argparse
import json
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime


def fetch_instance_api(url: str, use_tor: bool = False) -> dict:
    """
    Fetch /api/v1/stats from the instance.

    Args:
        url: Base URL of the instance (clearnet or .onion)
        use_tor: Whether to use torify for .onion URLs

    Returns:
        Parsed JSON response from the API

    Raises:
        Exception: If API fetch fails
    """
    api_url = f"{url.rstrip('/')}/api/v1/stats"

    if use_tor:
        # Use torify curl for .onion URLs
        try:
            result = subprocess.run(
                ["torify", "curl", "-s", "--max-time", "30", api_url],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise Exception(f"torify curl failed: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response from Tor: {e}") from e
    else:
        # Use urllib for clearnet URLs
        # Validate URL scheme to prevent file:// or other schemes
        if not api_url.startswith(("https://", "http://")):
            raise Exception(f"Invalid URL scheme: {api_url}")
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(api_url, headers={"User-Agent": "ReddArchiver-Registry/1.0"})  # noqa: S310
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise Exception(f"URL error: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}") from e


def detect_user_pages(url: str, use_tor: bool = False) -> bool:
    """
    Detect if user pages are enabled by checking the /api/v1/users endpoint.

    Args:
        url: Base URL of the instance
        use_tor: Whether to use torify for .onion URLs

    Returns:
        True if user pages appear to be enabled, False otherwise
    """
    users_url = f"{url.rstrip('/')}/api/v1/users?limit=1"

    try:
        if use_tor:
            result = subprocess.run(
                ["torify", "curl", "-s", "--max-time", "10", users_url],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
        else:
            if not users_url.startswith(("https://", "http://")):
                return False
            ctx = ssl.create_default_context()
            req = urllib.request.Request(users_url, headers={"User-Agent": "ReddArchiver-Registry/1.0"})  # noqa: S310
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:  # noqa: S310
                data = json.loads(response.read().decode("utf-8"))

        # If we get users data back, user pages are enabled
        return "data" in data and len(data.get("data", [])) > 0
    except Exception:
        # If endpoint fails, assume user pages not enabled
        return False


def get_api_url(clearnet_url: str | None, tor_url: str | None) -> tuple[str, bool]:
    """
    Determine which URL to use for API fetch.

    Args:
        clearnet_url: Optional clearnet URL
        tor_url: Optional Tor URL

    Returns:
        Tuple of (url_to_use, use_tor_flag)

    Raises:
        ValueError: If neither URL is provided
    """
    if clearnet_url:
        return clearnet_url, False  # prefer clearnet
    elif tor_url:
        return tor_url, True  # tor-only instance
    else:
        raise ValueError("At least one URL (clearnet or Tor) is required")


def parse_issue_body(issue_body: str) -> dict:
    """
    Parse GitHub issue body and extract registration fields.

    Args:
        issue_body: Raw issue body text from GitHub

    Returns:
        Dictionary with parsed registration data
    """
    data = {}

    # Extract fields using regex patterns (updated for new form structure)
    patterns = {
        "clearnet_url": r"### Clearnet URL\s*\n\s*(.+)",
        "tor_url": r"### Tor Hidden Service URL\s*\n\s*(.+)",
        "instance_name": r"### Instance Name.*?\n\s*(.+)",
        "team_name": r"### Team Name.*?\n\s*(.+)",
        "maintainer_github": r"### GitHub Username\s*\n\s*(.+)",
        "preferred_contact": r"### Preferred Contact Method.*?\n\s*(.+)",
        "hosting_type": r"### Hosting Type\s*\n\s*(.+)",
        "location": r"### Server Region.*?\n\s*(.+)",
        "country": r"### Country.*?\n\s*(.+)",
        "ipfs_cid": r"### IPFS CID.*?\n\s*(.+)",
        "additional_info": r"### Additional Information\s*\n\s*(.+?)(?=\n###|\Z)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, issue_body, re.MULTILINE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            # Skip if placeholder text or "No response" or "None"
            if value and value not in ["_No response_", "No response", "None", ""]:
                data[key] = value

    # Parse user_pages checkbox
    if re.search(r"\[x\] User pages enabled", issue_body, re.IGNORECASE):
        data["user_pages"] = True

    return data


def generate_instance_json(data: dict, api_data: dict, is_tor_only: bool, user_pages_detected: bool) -> dict:
    """
    Generate registry JSON format from parsed issue data and API data.

    Args:
        data: Parsed issue data from form
        api_data: Data fetched from instance's /api/v1/stats
        is_tor_only: Whether this is a Tor-only instance (no clearnet)
        user_pages_detected: Whether user pages were detected via API

    Returns:
        Registry-compatible JSON structure
    """
    # Get instance metadata from API, with form overrides
    api_instance = api_data.get("instance", {})

    # Instance name: form override or API
    instance_name = data.get("instance_name") or api_instance.get("name", "unknown")

    # Generate instance ID (lowercase, hyphenated)
    instance_id = re.sub(r"[^a-z0-9]+", "-", instance_name.lower()).strip("-")

    # Determine URLs
    clearnet_url = data.get("clearnet_url")
    tor_url = data.get("tor_url") or api_instance.get("tor_url")

    # Build endpoints object
    endpoints = {}
    if clearnet_url:
        endpoints["clearnet"] = clearnet_url
        endpoints["api"] = f"{clearnet_url}/api/v1/stats"
    elif tor_url:
        endpoints["api"] = f"{tor_url}/api/v1/stats"

    if tor_url:
        endpoints["tor"] = tor_url

    if data.get("ipfs_cid"):
        endpoints["ipfs"] = f"https://ipfs.io/ipfs/{data['ipfs_cid']}"

    # Build contact object
    contact = {}
    if data.get("preferred_contact"):
        contact["preferred"] = data["preferred_contact"]

    # Get subreddits from API
    api_subreddits = api_data.get("content", {}).get("subreddits", [])
    subreddits_list = []
    for sub in api_subreddits:
        if isinstance(sub, dict):
            subreddits_list.append({"name": sub.get("name", ""), "url": f"/r/{sub.get('name', '')}/"})
        elif isinstance(sub, str):
            subreddits_list.append({"name": sub, "url": f"/r/{sub}/"})

    # Build static_metadata
    static_metadata = {
        "subreddits": subreddits_list,
        "hosting": data.get("hosting_type", "unknown"),
    }

    # Only include geolocation for non-tor-only instances (privacy protection)
    if not is_tor_only:
        if data.get("location") and data["location"] != "Other/Unknown":
            static_metadata["location"] = data["location"]
        if data.get("country"):
            static_metadata["country"] = data["country"]

    # Auto-detect features from API
    features = ["api"]  # Always has API if we got here
    api_features = api_data.get("features", {})
    if api_features.get("tor") or tor_url:
        features.append("tor")

    # User pages: form checkbox OR auto-detected from API
    if data.get("user_pages") or user_pages_detected:
        features.append("user-pages")

    # Build final JSON structure
    instance_json = {
        "instance_id": instance_id,
        "name": instance_name,
        "maintainer": data.get("maintainer_github"),
        "registered": datetime.utcnow().strftime("%Y-%m-%d"),
        "endpoints": endpoints,
        "static_metadata": static_metadata,
        "features": features,
    }

    # Add team_id: form override or API
    team_name = data.get("team_name")
    api_team_id = api_instance.get("team_id")
    if team_name:
        team_id = re.sub(r"[^a-z0-9]+", "-", team_name.lower()).strip("-")
        instance_json["team_id"] = team_id
    elif api_team_id:
        instance_json["team_id"] = api_team_id

    # Add contact if any contact info provided
    if contact:
        instance_json["contact"] = contact

    # Add notes from additional_info if provided
    if data.get("additional_info"):
        instance_json["notes"] = data["additional_info"]

    return instance_json


def main():
    parser = argparse.ArgumentParser(description="Convert GitHub issue to registry JSON")
    parser.add_argument("--issue-number", type=int, help="GitHub issue number (requires gh CLI)")
    parser.add_argument("--from-clipboard", action="store_true", help="Read issue body from clipboard")
    parser.add_argument("--from-file", type=str, help="Read issue body from file")
    parser.add_argument("--output", type=str, help="Output JSON file path (default: instances/<instance-id>.json)")
    parser.add_argument("--skip-api", action="store_true", help="Skip API fetch (for testing)")

    args = parser.parse_args()

    # Get issue body
    issue_body = None

    if args.issue_number:
        try:
            result = subprocess.run(
                ["gh", "issue", "view", str(args.issue_number), "--json", "body"],
                capture_output=True,
                text=True,
                check=True,
            )
            issue_data = json.loads(result.stdout)
            issue_body = issue_data["body"]
            print(f"✓ Loaded issue #{args.issue_number}")
        except Exception as e:
            print(f"✗ Failed to load issue #{args.issue_number}: {e}")
            print("  Make sure 'gh' CLI is installed and authenticated")
            sys.exit(1)

    elif args.from_clipboard:
        try:
            import pyperclip

            issue_body = pyperclip.paste()
            print("✓ Loaded issue body from clipboard")
        except ImportError:
            print("✗ pyperclip not installed. Install with: pip install pyperclip")
            sys.exit(1)

    elif args.from_file:
        try:
            with open(args.from_file) as f:
                issue_body = f.read()
            print(f"✓ Loaded issue body from {args.from_file}")
        except Exception as e:
            print(f"✗ Failed to read file: {e}")
            sys.exit(1)

    else:
        print("✗ Must specify one of: --issue-number, --from-clipboard, --from-file")
        parser.print_help()
        sys.exit(1)

    # Parse issue body
    print("\n📋 Parsing issue data...")
    parsed_data = parse_issue_body(issue_body)

    # Validate at least one URL is provided
    clearnet_url = parsed_data.get("clearnet_url")
    tor_url = parsed_data.get("tor_url")

    if not clearnet_url and not tor_url:
        print("✗ At least one URL (clearnet or Tor) is required")
        sys.exit(1)

    # Determine if tor-only
    is_tor_only = not clearnet_url and bool(tor_url)
    if is_tor_only:
        print("🧅 Tor-only instance detected - geolocation will be excluded for privacy")

    # Fetch API data
    api_data = {}
    user_pages_detected = False
    if not args.skip_api:
        try:
            api_url, use_tor = get_api_url(clearnet_url, tor_url)
            print(f"\n🌐 Fetching API from: {api_url}")
            if use_tor:
                print("   (Using Tor - make sure torify is installed)")
            api_data = fetch_instance_api(api_url, use_tor)
            print("✓ API fetch successful")

            # Detect user pages
            print("🔍 Checking for user pages...")
            user_pages_detected = detect_user_pages(api_url, use_tor)
            if user_pages_detected:
                print("✓ User pages detected")
            else:
                print("✗ User pages not detected (or disabled)")

            # Show what we got from API
            api_instance = api_data.get("instance", {})
            api_content = api_data.get("content", {})
            print("\n📊 API Data Summary:")
            print(f"   Instance name: {api_instance.get('name', 'N/A')}")
            print(f"   Team ID: {api_instance.get('team_id', 'N/A')}")
            print(f"   Tor URL: {api_instance.get('tor_url', 'N/A')}")
            print(f"   Subreddits: {len(api_content.get('subreddits', []))}")
            print(f"   Total posts: {api_content.get('total_posts', 'N/A')}")
            print(f"   Total comments: {api_content.get('total_comments', 'N/A')}")
            print(f"   Total users: {api_content.get('total_users', 'N/A')}")

        except Exception as e:
            print(f"✗ Failed to fetch API: {e}")
            print("\n⚠️  Cannot proceed without API data.")
            print("   Please verify the instance is online and the API endpoint works.")
            sys.exit(1)
    else:
        print("\n⚠️  Skipping API fetch (--skip-api)")

    # Generate JSON
    print("\n📝 Generating registry JSON...")
    instance_json = generate_instance_json(parsed_data, api_data, is_tor_only, user_pages_detected)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = f"instances/{instance_json['instance_id']}.json"

    # Show form vs API data
    print("\n" + "=" * 60)
    print("📋 DATA SOURCES:")
    print("=" * 60)
    api_instance = api_data.get("instance", {})
    print(f"Instance name: {instance_json['name']}")
    if parsed_data.get("instance_name"):
        print("   └─ Source: Form (override)")
    elif api_instance.get("name"):
        print("   └─ Source: API")
    else:
        print("   └─ Source: Unknown")

    if instance_json.get("team_id"):
        print(f"Team ID: {instance_json['team_id']}")
        if parsed_data.get("team_name"):
            print("   └─ Source: Form (override)")
        else:
            print("   └─ Source: API")

    print(f"Subreddits: {len(instance_json['static_metadata']['subreddits'])}")
    print("   └─ Source: API")

    print(f"Features: {instance_json['features']}")
    print("   └─ Source: API (auto-detected)")
    if "user-pages" in instance_json["features"]:
        if parsed_data.get("user_pages"):
            print("   └─ user-pages: Form checkbox")
        else:
            print("   └─ user-pages: Auto-detected")

    if is_tor_only:
        print("Geolocation: EXCLUDED (Tor-only instance)")
    else:
        if instance_json["static_metadata"].get("location"):
            print(f"Location: {instance_json['static_metadata']['location']}")
        if instance_json["static_metadata"].get("country"):
            print(f"Country: {instance_json['static_metadata']['country']}")

    # Pretty print to console
    print("\n" + "=" * 60)
    print("Generated JSON:")
    print("=" * 60)
    print(json.dumps(instance_json, indent=2))
    print("=" * 60)

    # Save to file
    try:
        import os

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(instance_json, f, indent=2)
            f.write("\n")  # Add trailing newline
        print(f"\n✓ Saved to: {output_path}")
    except Exception as e:
        print(f"\n✗ Failed to save file: {e}")
        sys.exit(1)

    # Validation reminders
    print("\n" + "=" * 60)
    print("⚠️  VALIDATION CHECKLIST:")
    print("=" * 60)
    if instance_json["endpoints"].get("clearnet"):
        print(f"1. Visit {instance_json['endpoints']['clearnet']} - verify it loads")
    if instance_json["endpoints"].get("tor"):
        print(f"2. Verify Tor URL: {instance_json['endpoints']['tor']}")
        print("   (Use: torify curl <url>)")
    if instance_json["endpoints"].get("ipfs"):
        print(f"3. Verify IPFS URL: {instance_json['endpoints']['ipfs']}")
    print("4. Review subreddit list from API is accurate")
    print("5. Review JSON for accuracy before committing")
    print("\nNext steps:")
    print(f"  git add {output_path}")
    print(f"  git commit -m 'registry: add {instance_json['name']}'")
    print("  git push")


if __name__ == "__main__":
    main()
