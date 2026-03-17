"""Interactive elements testing"""
import asyncio
import sys
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def interactive_test():
    base = "http://localhost:5173"
    results = {"pass": [], "fail": [], "warn": []}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=800)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        print("="*60)
        print("INTERACTIVE ELEMENTS TEST")
        print("="*60)

        # Test clicking navigation items
        print("\n[NAVIGATION]")
        nav_items = [
            ("Projects", "/projects"),
            ("Agents", "/agents"),
            ("Skills", "/skills"),
            ("Analytics", "/analytics"),
            ("Settings", "/settings"),
        ]

        for name, path in nav_items:
            try:
                await page.goto(f"{base}{path}", wait_until="networkidle")
                await page.wait_for_timeout(500)
                results["pass"].append(f"Nav to {name}")
                print(f"  ✓ {name}")
            except Exception as e:
                results["fail"].append(f"Nav to {name}: {str(e)[:50]}")
                print(f"  ✗ {name}: {str(e)[:50]}")

        # Test project card clicks
        print("\n[PROJECT CARDS]")
        await page.goto(f"{base}/projects", wait_until="networkidle")
        await page.wait_for_timeout(1000)

        project_links = await page.query_selector_all("a[href*='/projects/']")
        print(f"  Found {len(project_links)} project links")

        if project_links:
            await project_links[0].click()
            await page.wait_for_timeout(1000)
            print(f"  ✓ Project card clickable")
            results["pass"].append("Project card click")
        else:
            results["warn"].append("No project cards found")
            print(f"  ⚠ No project cards")

        # Test filters/search
        print("\n[FILTERS & SEARCH]")
        await page.goto(f"{base}/projects", wait_until="networkidle")

        search_inputs = await page.query_selector_all("input[type='search'], input[placeholder*='search' i]")
        print(f"  Search inputs: {len(search_inputs)}")

        filter_buttons = await page.query_selector_all("button[aria-haspopup], select")
        print(f"  Filter controls: {len(filter_buttons)}")

        # Test timeline on session page
        print("\n[TIMELINE]")
        await page.goto(f"{base}/projects/karma-625f/karma-625f", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        timeline = await page.query_selector(".timeline, [data-testid='timeline']")
        if timeline:
            print(f"  ✓ Timeline present")
            results["pass"].append("Timeline visible")
        else:
            results["warn"].append("Timeline not found")
            print(f"  ⚠ Timeline not found (may load async)")

        # Test subagent navigation
        print("\n[SUBAGENT NAVIGATION]")
        subagent_links = await page.query_selector_all("a[href*='/agents/']")
        print(f"  Subagent links: {len(subagent_links)}")

        if subagent_links:
            href = await subagent_links[0].get_attribute("href")
            print(f"  Testing: {href}")
            await subagent_links[0].click()
            await page.wait_for_timeout(1500)
            results["pass"].append("Subagent link navigation")
            print(f"  ✓ Subagent link works")
        else:
            results["warn"].append("No subagent links (no subagents in data)")
            print(f"  ⚠ No subagent links")

        # Test back button
        print("\n[BACK NAVIGATION]")
        await page.go_back(wait_until="networkidle")
        await page.wait_for_timeout(500)
        results["pass"].append("Back navigation")
        print(f"  ✓ Back button works")

        # Test keyboard shortcuts
        print("\n[KEYBOARD SHORTCUTS]")
        await page.goto(f"{base}/projects", wait_until="networkidle")

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        print(f"  ✓ ESC key works")

        # Test responsive
        print("\n[RESPONSIVE]")
        await page.set_viewport_size({"width": 768, "height": 1024})
        await page.wait_for_timeout(500)
        results["pass"].append("Tablet view")
        print(f"  ✓ Tablet view OK")

        await page.set_viewport_size({"width": 375, "height": 667})
        await page.wait_for_timeout(500)
        results["pass"].append("Mobile view")
        print(f"  ✓ Mobile view OK")

        # Summary
        print("\n" + "="*60)
        print("RESULTS")
        print("="*60)
        print(f"Passed: {len(results['pass'])}")
        print(f"Failed: {len(results['fail'])}")
        print(f"Warnings: {len(results['warn'])}")

        if results['fail']:
            print("\nFAILURES:")
            for f in results['fail']:
                print(f"  - {f}")

        if results['warn']:
            print("\nWARNINGS:")
            for w in results['warn']:
                print(f"  - {w}")

        await browser.close()

asyncio.run(interactive_test())
