#!/usr/bin/env python3
# ABOUTME: Registry leaderboard generator for Redd-Archiver network
# ABOUTME: Fetches instance stats, calculates scores, generates LEADERBOARD.md and COVERAGE.md

"""
Registry Leaderboard Generator

Fetches statistics from all registered instances, calculates team scores with
completeness and risk weighting, tracks uptime, and generates markdown outputs.

Features:
- Robust health checks (5 retries over 1 hour, clearnet + Tor)
- Completeness-weighted scoring (rewards thorough archives)
- Risk weighting (1.5x for banned subreddit content)
- External uptime tracking (survives container rebuilds)
- Global coverage index (coordination tool)

Usage:
    python scripts/update_leaderboard.py
    python scripts/update_leaderboard.py --registry custom-registry.json
"""

import json
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional
import argparse


class LeaderboardGenerator:
    def __init__(self, registry_file: Path, output_dir: Path, quick_test: bool = False, platform_metrics_file: Optional[Path] = None):
        self.registry_file = registry_file
        self.output_dir = output_dir
        self.quick_test = quick_test
        self.output_dir.mkdir(exist_ok=True, parents=True)

        # Load platform totals for coverage calculation
        self.platform_totals = {}
        if platform_metrics_file and platform_metrics_file.exists():
            with open(platform_metrics_file) as f:
                metrics = json.load(f)
                for platform, data in metrics.get('platforms', {}).items():
                    self.platform_totals[platform] = {
                        'total_posts': data.get('total_posts_available', 0),
                        'total_communities': data.get('total_communities', 0)
                    }
            print(f"Loaded platform totals: {len(self.platform_totals)} platforms")
        else:
            print("Warning: platform_metrics.json not found, coverage % will be per-community only")

    async def check_instance_online(
        self, instance: Dict, session: aiohttp.ClientSession
    ) -> Dict:
        """
        Check if instance is online with robust retry logic.

        Retry strategy: 5 attempts over 1 hour (accounts for Tor circuit delays)
        Success criteria: ANY 1 successful request (clearnet OR tor)
        Checks: /health endpoint (must return 200)
        """
        endpoints = []

        # Add clearnet endpoint if available
        if instance.get('endpoints', {}).get('clearnet'):
            endpoints.append({
                'type': 'clearnet',
                'url': instance['endpoints']['clearnet'] + '/health'
            })

        # Add Tor endpoint if available
        if instance.get('endpoints', {}).get('tor'):
            endpoints.append({
                'type': 'tor',
                'url': instance['endpoints']['tor'] + '/health'
            })

        if not endpoints:
            return {
                'instance_id': instance['instance_id'],
                'online': False,
                'error': 'No endpoints configured'
            }

        # 5 retry attempts over 1 hour (or 30s for quick test)
        if self.quick_test:
            retry_delays = [0, 2, 4, 6, 8]  # Quick test: 0s, 2s, 4s, 6s, 8s
        else:
            retry_delays = [0, 300, 900, 1800, 3600]  # Production: 0s, 5min, 15min, 30min, 60min

        for attempt, delay in enumerate(retry_delays, 1):
            if delay > 0:
                print(f"  Retry {attempt}/5 for {instance['instance_id']} in {delay}s...")
                await asyncio.sleep(delay)

            # Try all endpoints (clearnet + tor)
            for endpoint in endpoints:
                try:
                    async with session.get(
                        endpoint['url'],
                        timeout=aiohttp.ClientTimeout(total=30),  # 30s timeout (Tor-friendly)
                        allow_redirects=True
                    ) as response:
                        if response.status == 200:
                            # SUCCESS! Instance is online
                            print(f"  ✓ {instance['instance_id']} online via {endpoint['type']} (attempt {attempt})")
                            return {
                                'instance_id': instance['instance_id'],
                                'online': True,
                                'endpoint': endpoint['type'],
                                'attempt': attempt
                            }
                except Exception as e:
                    # Try next endpoint or retry
                    continue

        # All retries failed on all endpoints
        print(f"  ✗ {instance['instance_id']} offline after {len(retry_delays)} attempts")
        return {
            'instance_id': instance['instance_id'],
            'online': False,
            'attempts': len(retry_delays)
        }

    async def fetch_instance_stats(
        self, instance: Dict, session: aiohttp.ClientSession
    ) -> Dict:
        """Fetch stats from instance API after confirming online."""
        # First check if online
        online_check = await self.check_instance_online(instance, session)

        if not online_check['online']:
            return online_check

        # Fetch stats from API endpoint
        api_url = instance['endpoints'].get('api')
        if not api_url:
            return {
                'instance_id': instance['instance_id'],
                'online': False,
                'error': 'No API endpoint configured'
            }

        try:
            async with session.get(
                api_url,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        'instance_id': instance['instance_id'],
                        'online': True,
                        'online_via': online_check['endpoint'],
                        'stats': data,
                        'checked_at': datetime.now(timezone.utc).isoformat()
                    }
                else:
                    return {
                        'instance_id': instance['instance_id'],
                        'online': False,
                        'error': f'HTTP {resp.status}'
                    }
        except Exception as e:
            return {
                'instance_id': instance['instance_id'],
                'online': False,
                'error': str(e)
            }

    def track_instance_uptime(
        self, instance: Dict, check_result: Dict, registry_data: Dict
    ) -> Dict:
        """Update uptime tracking based on health check."""
        now = datetime.now(timezone.utc).isoformat()

        if 'first_seen' not in instance:
            instance['first_seen'] = now
            instance['check_count'] = 0

        if check_result['online']:
            instance['last_check'] = now
            instance['last_online_via'] = check_result.get('online_via', 'unknown')
            instance['check_count'] = instance.get('check_count', 0) + 1

        # Calculate days since first seen
        first_seen_dt = datetime.fromisoformat(instance['first_seen'].replace('Z', '+00:00'))
        instance['days_online'] = (datetime.now(timezone.utc) - first_seen_dt).days

        return instance

    async def check_all_instances(self, instances: List[Dict]) -> List[Dict]:
        """Check all instances concurrently with retry logic."""
        print(f"\nChecking {len(instances)} instances...")
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_instance_stats(inst, session) for inst in instances]
            return await asyncio.gather(*tasks)

    def calculate_team_stats(
        self, team: Dict, instances: List[Dict], results: List[Dict]
    ) -> Dict:
        """
        Aggregate stats for a team with completeness and risk weighting.

        Scoring formula:
        - Per-subreddit content with risk weighting (banned = 1.5x)
        - Completeness bonus (coverage_percentage weighted)
        - Infrastructure bonus (500 pts per online instance)
        - Optional: Uptime bonus (days_online, commented out)
        """
        team_instances = [inst for inst in instances if inst.get('team_id') == team['team_id']]
        team_results = [
            res for res in results
            if any(inst['instance_id'] == res['instance_id'] for inst in team_instances)
        ]

        # Aggregate metrics
        total_posts = 0
        total_comments = 0
        total_users = 0
        communities_set = set()  # Track (platform, community_name) tuples
        communities_by_platform = {}  # Track per-platform counts
        online_count = 0

        # For completeness + risk-weighted scoring
        completeness_score = 0
        risk_weighted_content_score = 0

        for result in team_results:
            if result['online'] and 'stats' in result:
                stats = result['stats']
                online_count += 1

                # Per-community scoring (platform-aware)
                for community in stats.get('content', {}).get('subreddits', []):
                    platform = community.get('platform', 'reddit')
                    name = community['name']

                    # Deduplicate by (platform, name)
                    community_key = (platform, name)
                    if community_key not in communities_set:
                        communities_set.add(community_key)

                        # Track per-platform counts
                        if platform not in communities_by_platform:
                            communities_by_platform[platform] = 0
                        communities_by_platform[platform] += 1

                    # Simple totals (for display)
                    total_posts += community.get('archived_posts', 0)
                    total_comments += community.get('comments', 0)
                    total_users += community.get('users', 0)

                    # Risk-weighted content scoring
                    risk_weight = 1.5 if community.get('is_banned', False) else 1.0
                    risk_weighted_content_score += community.get('archived_posts', 0) * 0.0001 * risk_weight
                    risk_weighted_content_score += community.get('comments', 0) * 0.00001 * risk_weight
                    risk_weighted_content_score += community.get('users', 0) * 0.001 * risk_weight

                    # Completeness bonus
                    coverage_pct = community.get('coverage_percentage', 0)
                    completeness_score += 50 * (coverage_pct / 100)

        # Calculate total team score
        score = (
            risk_weighted_content_score +
            completeness_score +
            online_count * 500
            # Optional uptime bonus (tracked, not scored yet):
            # + sum(inst.get('days_online', 0) for inst in team_instances)
        )

        # Calculate platform-specific coverage percentages
        platform_coverage = {}
        for platform, archived_count in communities_by_platform.items():
            if platform in self.platform_totals:
                total_available = self.platform_totals[platform]['total_communities']
                coverage_pct = round((archived_count / total_available * 100), 2) if total_available > 0 else 0
                platform_coverage[platform] = {
                    'archived': archived_count,
                    'total_available': total_available,
                    'coverage_percentage': coverage_pct
                }

        # Calculate overall coverage (all platforms combined)
        total_archived = len(communities_set)
        total_available = sum(p['total_communities'] for p in self.platform_totals.values())
        overall_coverage = round((total_archived / total_available * 100), 2) if total_available > 0 else 0

        return {
            'team_id': team['team_id'],
            'name': team['name'],
            'description': team.get('description', ''),
            'total_instances': len(team_instances),
            'online_instances': online_count,
            'total_posts': total_posts,
            'total_comments': total_comments,
            'total_users': total_users,
            'total_communities': total_archived,  # Deduplicated across platforms
            'communities_by_platform': communities_by_platform,
            'platform_coverage': platform_coverage,
            'overall_coverage_percentage': overall_coverage,
            'team_score': round(score, 2)
        }

    def generate_coverage_index(
        self, instances: List[Dict], results: List[Dict]
    ) -> Dict:
        """
        Build global community coverage index (multi-platform).

        Shows which communities are archived where, with completeness metrics.
        Key is (platform, community_name) for proper deduplication.
        """
        coverage_map = {}

        for result in results:
            if not result['online'] or 'stats' not in result:
                continue

            instance_id = result['instance_id']
            instance = next((i for i in instances if i['instance_id'] == instance_id), None)
            if not instance:
                continue

            stats = result['stats']

            for community in stats.get('content', {}).get('subreddits', []):
                platform = community.get('platform', 'reddit')
                name = community['name']
                key = (platform, name)

                if key not in coverage_map:
                    # Get community term (subreddit/subverse/guild)
                    community_term = {
                        'reddit': 'subreddit',
                        'voat': 'subverse',
                        'ruqqus': 'guild'
                    }.get(platform, 'community')

                    coverage_map[key] = {
                        'platform': platform,
                        'community_name': name,
                        'community_term': community_term,
                        'total_instances': 0,
                        'instances': [],
                        'best_coverage': 0,
                        'is_banned': community.get('is_banned', False),
                        'latest_date': community.get('latest_date')
                    }

                coverage_map[key]['total_instances'] += 1
                coverage_map[key]['instances'].append({
                    'instance_id': instance_id,
                    'instance_name': instance['name'],
                    'team_id': instance.get('team_id', 'Independent'),
                    'coverage_percentage': community.get('coverage_percentage', 0),
                    'archived_posts': community.get('archived_posts', 0),
                    'url': instance['endpoints'].get('clearnet', '')
                })

                # Track best coverage
                if community.get('coverage_percentage', 0) > coverage_map[key]['best_coverage']:
                    coverage_map[key]['best_coverage'] = community['coverage_percentage']

        return coverage_map

    def generate_leaderboard_markdown(
        self, teams_data: List[Dict], instances: List[Dict], results: List[Dict]
    ) -> str:
        """Generate LEADERBOARD.md with team rankings."""
        sorted_teams = sorted(teams_data, key=lambda x: x['team_score'], reverse=True)

        md = [
            "# Registry Leaderboard",
            "",
            f"**Last Updated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Platform Coverage (All Teams Combined)",
            ""
        ]

        # Calculate global coverage across all teams
        all_communities = set()
        all_by_platform = {}
        for result in results:
            if result['online'] and 'stats' in result:
                for community in result['stats'].get('content', {}).get('subreddits', []):
                    platform = community.get('platform', 'reddit')
                    name = community['name']
                    all_communities.add((platform, name))

                    if platform not in all_by_platform:
                        all_by_platform[platform] = set()
                    all_by_platform[platform].add(name)

        # Show platform coverage table
        md.extend([
            "| Platform | Archived Communities | Total Available | Coverage % |",
            "|----------|---------------------|-----------------|------------|"
        ])

        for platform in ['reddit', 'voat', 'ruqqus']:
            if platform in self.platform_totals:
                archived = len(all_by_platform.get(platform, set()))
                total = self.platform_totals[platform]['total_communities']
                coverage = round((archived / total * 100), 2) if total > 0 else 0
                md.append(f"| {platform.title()} | {archived:,} | {total:,} | {coverage}% |")

        total_archived = len(all_communities)
        total_available = sum(p['total_communities'] for p in self.platform_totals.values())
        overall = round((total_archived / total_available * 100), 2) if total_available > 0 else 0
        md.append(f"| **TOTAL** | **{total_archived:,}** | **{total_available:,}** | **{overall}%** |")

        md.extend([
            "",
            "## Top Teams",
            "",
            "| Rank | Team | Score | Instances | Communities | Posts | Comments | Users |",
            "|------|------|-------|-----------|-------------|-------|----------|-------|"
        ])

        for idx, team in enumerate(sorted_teams, 1):
            rank_display = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
            md.append(
                f"| {rank_display} | {team['name']} | {team['team_score']:,.1f} | "
                f"{team['online_instances']}/{team['total_instances']} | "
                f"{team['total_communities']} ({team.get('overall_coverage_percentage', 0)}%) | {team['total_posts']:,} | "
                f"{team['total_comments']:,} | {team['total_users']:,} |"
            )

        md.extend(["", "## Team Details", ""])

        for team in sorted_teams:
            md.extend([
                f"### {team['name']}",
                "",
                f"**Score**: {team['team_score']:,.1f} points",
                f"**Description**: {team['description']}",
                f"**Coverage**: {team.get('overall_coverage_percentage', 0)}% of all platforms",
                ""
            ])

            # Show platform breakdown if available
            if team.get('platform_coverage'):
                md.extend(["**Platform Breakdown**:", ""])
                for platform, data in team['platform_coverage'].items():
                    md.append(f"- {platform.title()}: {data['archived']:,}/{data['total_available']:,} ({data['coverage_percentage']}%)")
                md.append("")

            md.extend([
                "**Instances**:",
                "",
                "| Instance | Status | Days Online | Last Check | Endpoints | Communities |",
                "|----------|--------|-------------|------------|-----------|-------------|"
            ])

            team_instances = [inst for inst in instances if inst.get('team_id') == team['team_id']]
            for inst in team_instances:
                result = next((r for r in results if r['instance_id'] == inst['instance_id']), None)

                if result and result['online']:
                    status = "✅ Online"
                    endpoint_status = f"{result.get('online_via', 'unknown')}"
                    stats = result.get('stats', {}).get('content', {})
                    sub_count = len(stats.get('subreddits', []))
                else:
                    status = "❌ Offline"
                    endpoint_status = "none"
                    sub_count = "?"

                days_online = inst.get('days_online', '?')
                last_check = inst.get('last_check', 'Never')
                if last_check != 'Never':
                    last_check = datetime.fromisoformat(last_check.replace('Z', '+00:00')).strftime('%Y-%m-%d')

                md.append(
                    f"| {inst['name']} | {status} | {days_online} days | {last_check} | {endpoint_status} | {sub_count} |"
                )

            md.append("")

        md.extend([
            "---",
            "",
            "## Scoring Formula",
            "",
            "```python",
            "score = (",
            "    risk_weighted_content_score +     # Per-subreddit with 1.5x for banned",
            "    completeness_score +              # 50 pts × (coverage_percentage / 100)",
            "    online_count * 500                # Infrastructure reliability",
            ")",
            "```",
            "",
            "**Key Principles**:",
            "- Completeness matters: 95% archive >> 30% archive",
            "- Risk weighting: Banned content worth 1.5x",
            "- Per-subreddit granularity: Quality over quantity",
            ""
        ])

        return "\n".join(md)

    def generate_coverage_markdown(self, coverage_map: Dict) -> str:
        """Generate COVERAGE.md with global community index (multi-platform)."""
        # Categorize communities
        well_covered = []
        partial = []
        at_risk = []

        # Group by platform for display
        by_platform = {'reddit': [], 'voat': [], 'ruqqus': []}

        for key, data in coverage_map.items():
            platform = data['platform']

            if data['best_coverage'] >= 90 or data['total_instances'] >= 2:
                well_covered.append((key, data))
            elif data['is_banned'] and data['best_coverage'] < 70:
                at_risk.append((key, data))
            else:
                partial.append((key, data))

            if platform in by_platform:
                by_platform[platform].append((key, data))

        md = [
            "# Global Community Coverage",
            "",
            f"**Last Updated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Summary",
            "",
            f"- **Total Communities**: {len(coverage_map)}",
            f"  - Reddit: {len(by_platform['reddit'])} subreddits",
            f"  - Voat: {len(by_platform['voat'])} subverses",
            f"  - Ruqqus: {len(by_platform['ruqqus'])} guilds",
            f"- **Well Covered** (≥90% or 2+ instances): {len(well_covered)}",
            f"- **Partial Coverage**: {len(partial)}",
            f"- **At Risk** (banned + low coverage): {len(at_risk)}",
            ""
        ]

        # Show coverage by platform
        for platform in ['reddit', 'voat', 'ruqqus']:
            if not by_platform[platform]:
                continue

            platform_name = platform.title()
            prefix = {'reddit': 'r', 'voat': 'v', 'ruqqus': 'g'}[platform]
            term = {'reddit': 'Subreddit', 'voat': 'Subverse', 'ruqqus': 'Guild'}[platform]

            md.extend([
                f"## {platform_name} Communities",
                "",
                f"| {term} | Status | Best Coverage | Instances | Archive Links |",
                "|-----------|--------|---------------|-----------|---------------|"
            ])

            # Sort by coverage percentage descending
            sorted_communities = sorted(by_platform[platform], key=lambda x: x[1]['best_coverage'], reverse=True)

            for key, data in sorted_communities[:100]:  # Limit to top 100 per platform
                name = data['community_name']
                status = "**BANNED**" if data['is_banned'] else "Active"
                links = []
                for inst in data['instances'][:3]:  # Show up to 3 instances
                    if inst['url']:
                        links.append(f"[{inst['instance_name']}]({inst['url']})")
                links_str = ", ".join(links) if links else "N/A"

                md.append(
                    f"| {prefix}/{name} | {status} | {data['best_coverage']:.1f}% | "
                    f"{data['total_instances']} | {links_str} |"
                )

            md.append("")

        if at_risk:
            md.extend([
                "",
                "## 🔴 Priority: At-Risk Content (Low Coverage)",
                "",
                "These banned/quarantined communities need better archiving:",
                "",
                "| Community | Platform | Coverage | Instances | Urgency |",
                "|-----------|----------|----------|-----------|---------|"
            ])

            for key, data in sorted(at_risk, key=lambda x: x[1]['best_coverage']):
                platform = data['platform']
                prefix = {'reddit': 'r', 'voat': 'v', 'ruqqus': 'g'}[platform]
                name = data['community_name']
                urgency = "🔴 Critical" if data['best_coverage'] < 30 else "🟠 High"
                md.append(
                    f"| {prefix}/{name} | {platform} | {data['best_coverage']:.1f}% | {data['total_instances']} | {urgency} |"
                )

        return "\n".join(md)

    async def generate(self):
        """Main generation flow."""
        print("=" * 80)
        print("Registry Leaderboard Generator")
        print("=" * 80)

        # Load registry
        print(f"\nLoading registry: {self.registry_file}")
        with open(self.registry_file) as f:
            registry_data = json.load(f)

        teams = registry_data.get('teams', [])
        instances = registry_data.get('instances', [])

        print(f"Found {len(teams)} teams, {len(instances)} instances")

        # Check all instances
        results = await self.check_all_instances(instances)

        # Update uptime tracking
        print("\nUpdating uptime tracking...")
        for instance in instances:
            result = next((r for r in results if r['instance_id'] == instance['instance_id']), None)
            if result:
                self.track_instance_uptime(instance, result, registry_data)

        # Calculate team stats
        print("\nCalculating team statistics...")
        teams_data = []
        for team in teams:
            team_stats = self.calculate_team_stats(team, instances, results)
            teams_data.append(team_stats)
            print(f"  {team['name']}: {team_stats['team_score']:.1f} points")

        # Generate coverage index
        print("\nGenerating global coverage index...")
        coverage_map = self.generate_coverage_index(instances, results)
        print(f"  Indexed {len(coverage_map)} subreddits")

        # Generate markdown outputs
        print("\nGenerating markdown files...")

        leaderboard_md = self.generate_leaderboard_markdown(teams_data, instances, results)
        leaderboard_file = self.output_dir / "LEADERBOARD.md"
        leaderboard_file.write_text(leaderboard_md)
        print(f"  ✓ {leaderboard_file}")

        coverage_md = self.generate_coverage_markdown(coverage_map)
        coverage_file = self.output_dir / "COVERAGE.md"
        coverage_file.write_text(coverage_md)
        print(f"  ✓ {coverage_file}")

        # Save updated registry with uptime tracking
        registry_file_out = self.output_dir / "registry.json"
        registry_file_out.write_text(json.dumps(registry_data, indent=2))
        print(f"  ✓ {registry_file_out} (updated with uptime)")

        print("\n" + "=" * 80)
        print("✓ Leaderboard generation complete!")
        print("=" * 80)


async def main():
    parser = argparse.ArgumentParser(description='Generate registry leaderboard with multi-platform coverage')
    parser.add_argument(
        '--registry',
        type=Path,
        default=Path('.github/instances-example.json'),
        help='Registry JSON file (default: .github/instances-example.json)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('leaderboard'),
        help='Output directory (default: leaderboard/)'
    )
    parser.add_argument(
        '--platform-metrics',
        type=Path,
        default=Path('tools/platform_metrics.json'),
        help='Platform metrics JSON file for coverage calculation (default: tools/platform_metrics.json)'
    )
    parser.add_argument(
        '--quick-test',
        action='store_true',
        help='Use short retry delays for testing (2-8s instead of 5-60min)'
    )

    args = parser.parse_args()

    generator = LeaderboardGenerator(
        args.registry,
        args.output,
        quick_test=args.quick_test,
        platform_metrics_file=args.platform_metrics
    )
    await generator.generate()


if __name__ == '__main__':
    asyncio.run(main())
