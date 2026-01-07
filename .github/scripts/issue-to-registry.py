#!/usr/bin/env python3
"""
ABOUTME: Convert GitHub issue template submissions to registry JSON format
ABOUTME: Helper script for maintainers to process new instance registrations

Usage:
    python issue-to-registry.py --issue-number 123
    python issue-to-registry.py --from-clipboard

This script reads a GitHub issue created with the register-instance.yml template
and generates a properly formatted JSON file for the registry.
"""

import argparse
import json
import re
import sys
from datetime import datetime


def parse_issue_body(issue_body: str) -> dict:
    """
    Parse GitHub issue body and extract registration fields.

    Args:
        issue_body: Raw issue body text from GitHub

    Returns:
        Dictionary with parsed registration data
    """
    data = {}

    # Extract fields using regex patterns
    patterns = {
        "instance_name": r"### Instance Name\s*\n\s*(.+)",
        "clearnet_url": r"### Clearnet URL\s*\n\s*(.+)",
        "tor_url": r"### Tor Hidden Service URL.*?\n\s*(.+)",
        "ipfs_cid": r"### IPFS CID.*?\n\s*(.+)",
        "subreddits": r"### Subreddits Archived\s*\n\s*(.+?)(?=\n###|\Z)",
        "team_name": r"### Team Name.*?\n\s*(.+)",
        "maintainer_github": r"### GitHub Username\s*\n\s*(.+)",
        "contact_email": r"### Contact Email.*?\n\s*(.+)",
        "contact_matrix": r"### Matrix Contact.*?\n\s*(.+)",
        "hosting_type": r"### Hosting Type\s*\n\s*(.+)",
        "location": r"### Server Location.*?\n\s*(.+)",
        "additional_info": r"### Additional Information\s*\n\s*(.+?)(?=\n###|\Z)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, issue_body, re.MULTILINE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            # Skip if placeholder text or "No response"
            if value and value not in ["_No response_", "No response", ""]:
                data[key] = value

    # Parse subreddits list
    if "subreddits" in data:
        subreddit_list = [
            s.strip() for s in data["subreddits"].split("\n") if s.strip() and not s.strip().startswith("_No response")
        ]
        data["subreddits_list"] = subreddit_list

    # Parse features checkboxes
    features = []
    feature_patterns = {
        "search": r"\[x\] Full-text search",
        "dark-mode": r"\[x\] Dark mode theme",
        "mobile": r"\[x\] Mobile-optimized",
        "tor": r"\[x\] Tor accessible",
        "ipfs": r"\[x\] IPFS pinned",
        "api": r"\[x\] REST API enabled",
    }

    for feature_key, feature_pattern in feature_patterns.items():
        if re.search(feature_pattern, issue_body, re.IGNORECASE):
            features.append(feature_key)

    data["features"] = features

    return data


def generate_instance_json(data: dict) -> dict:
    """
    Generate registry JSON format from parsed issue data.

    Args:
        data: Parsed issue data

    Returns:
        Registry-compatible JSON structure
    """
    # Generate instance ID (lowercase, hyphenated)
    instance_name = data.get("instance_name", "unknown")
    instance_id = re.sub(r"[^a-z0-9]+", "-", instance_name.lower()).strip("-")

    # Build endpoints object
    endpoints = {"clearnet": data.get("clearnet_url"), "api": f"{data.get('clearnet_url')}/api/v1/stats"}

    if data.get("tor_url"):
        endpoints["tor"] = data["tor_url"]

    if data.get("ipfs_cid"):
        endpoints["ipfs"] = f"https://ipfs.io/ipfs/{data['ipfs_cid']}"

    # Build contact object
    contact = {}
    if data.get("contact_email"):
        contact["email"] = data["contact_email"]
    if data.get("contact_matrix"):
        contact["matrix"] = data["contact_matrix"]

    # Build static_metadata
    subreddits_list = data.get("subreddits_list", [])
    static_metadata = {
        "subreddits": [{"name": sub, "url": f"/r/{sub}/"} for sub in subreddits_list],
        "hosting": data.get("hosting_type", "unknown"),
    }

    if data.get("location"):
        static_metadata["location"] = data["location"]

    # Build final JSON structure
    instance_json = {
        "instance_id": instance_id,
        "name": instance_name,
        "maintainer": data.get("maintainer_github"),
        "registered": datetime.utcnow().strftime("%Y-%m-%d"),
        "endpoints": endpoints,
        "static_metadata": static_metadata,
        "features": data.get("features", []),
    }

    # Add team_id if specified
    if data.get("team_name"):
        team_id = re.sub(r"[^a-z0-9]+", "-", data["team_name"].lower()).strip("-")
        instance_json["team_id"] = team_id

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

    args = parser.parse_args()

    # Get issue body
    issue_body = None

    if args.issue_number:
        try:
            import subprocess

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

    if not parsed_data.get("instance_name"):
        print("✗ Could not find instance name in issue body")
        sys.exit(1)

    # Generate JSON
    print("📝 Generating registry JSON...")
    instance_json = generate_instance_json(parsed_data)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = f"instances/{instance_json['instance_id']}.json"

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
    print(f"1. Visit {instance_json['endpoints']['clearnet']} - verify it loads")
    print(f"2. Visit {instance_json['endpoints']['api']} - verify JSON response")
    print("3. Check that subreddit list is accurate")
    print("4. If Tor/IPFS URLs provided, verify they work")
    print("5. Review JSON for accuracy before committing")
    print("\nNext steps:")
    print(f"  git add {output_path}")
    print(f"  git commit -m 'registry: add {instance_json['name']}'")
    print("  git push")


if __name__ == "__main__":
    main()
