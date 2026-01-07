#!/usr/bin/env python3
"""
ABOUTME: Automated screenshot capture script for redd-archiver README documentation
ABOUTME: Uses Playwright to capture key pages from the generated archive
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://localhost"  # nginx serves from OUTPUT_PATH root
SEARCH_URL = "http://localhost:5000"  # Flask search server
SCREENSHOTS_DIR = Path("screenshots")

# Screenshots to capture
SCREENSHOTS = [
    {
        "name": "01-dashboard",
        "url": f"{BASE_URL}/index.html",
        "description": "Main dashboard showing archive statistics",
        "viewport": {"width": 1920, "height": 1080},
    },
    {
        "name": "02-subreddit-index",
        "url": f"{BASE_URL}/r/RedditCensors/index.html",
        "description": "Subreddit index page with post listings",
        "viewport": {"width": 1920, "height": 1080},
    },
    {
        "name": "03-post-page",
        "url": f"{BASE_URL}/r/RedditCensors/comments/6cawkc/new_antitrump_sub_march_agains_trump_with_26/index.html",
        "description": "Individual post page with nested comments (11 comments)",
        "viewport": {"width": 1920, "height": 1080},
    },
    {
        "name": "04-user-page",
        "url": f"{BASE_URL}/user/aaronC/index.html",
        "description": "User profile page showing posts and comments",
        "viewport": {"width": 1920, "height": 1080},
    },
    {
        "name": "05-mobile-dashboard",
        "url": f"{BASE_URL}/index.html",
        "description": "Mobile view of dashboard (responsive design)",
        "viewport": {"width": 375, "height": 812},  # iPhone X
    },
    {
        "name": "06-mobile-post",
        "url": f"{BASE_URL}/r/RedditCensors/comments/6cawkc/new_antitrump_sub_march_agains_trump_with_26/index.html",
        "description": "Mobile view of post page",
        "viewport": {"width": 375, "height": 812},
    },
    {
        "name": "07-search-form",
        "url": f"{SEARCH_URL}/",
        "description": "Search interface with query input and operators",
        "viewport": {"width": 1920, "height": 1080},
    },
    {
        "name": "08-search-results",
        "url": f"{SEARCH_URL}/search?q=censorship&subreddit=RedditCensors&limit=10",
        "description": "Search results with highlighted excerpts",
        "viewport": {"width": 1920, "height": 1080},
    },
]


async def capture_screenshot(page, screenshot):
    """Capture a single screenshot"""
    print(f"📸 Capturing: {screenshot['name']}")
    print(f"   URL: {screenshot['url']}")
    print(f"   Viewport: {screenshot['viewport']['width']}x{screenshot['viewport']['height']}")

    # Set viewport
    await page.set_viewport_size(screenshot['viewport'])

    # Navigate to page
    await page.goto(screenshot['url'], wait_until='networkidle')

    # Wait a bit for any dynamic content
    await page.wait_for_timeout(1000)

    # Take screenshot (clip to viewport, not full page)
    screenshot_path = SCREENSHOTS_DIR / f"{screenshot['name']}.png"
    await page.screenshot(path=str(screenshot_path), full_page=False)

    print(f"   ✅ Saved to: {screenshot_path}")
    print()


async def main():
    """Main screenshot capture function"""
    # Create screenshots directory
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    print("=" * 80)
    print("🎬 Redd-Archiver Screenshot Automation")
    print("=" * 80)
    print()
    print(f"Base URL: {BASE_URL}")
    print(f"Output directory: {SCREENSHOTS_DIR.absolute()}")
    print(f"Total screenshots: {len(SCREENSHOTS)}")
    print()
    print("=" * 80)
    print()

    async with async_playwright() as p:
        # Launch browser
        print("🚀 Launching Chromium...")
        browser = await p.chromium.launch(headless=True)

        # Create context
        context = await browser.new_context()

        # Create page
        page = await context.new_page()

        # Capture all screenshots
        for idx, screenshot in enumerate(SCREENSHOTS, 1):
            print(f"[{idx}/{len(SCREENSHOTS)}]")
            try:
                await capture_screenshot(page, screenshot)
            except Exception as e:
                print(f"   ❌ Error: {e}")
                print()

        # Close browser
        await browser.close()

    print("=" * 80)
    print("✅ Screenshot capture complete!")
    print("=" * 80)
    print()
    print("Screenshots saved to:")
    for screenshot_file in sorted(SCREENSHOTS_DIR.glob("*.png")):
        size = screenshot_file.stat().st_size / 1024  # KB
        print(f"  - {screenshot_file.name} ({size:.1f} KB)")
    print()
    print("📝 Next steps:")
    print("  1. Review screenshots in the 'screenshots/' directory")
    print("  2. Add them to your README.md")
    print("  3. Commit to repository")


if __name__ == "__main__":
    asyncio.run(main())
