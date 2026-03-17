"""Quick browser test - Critical Screens"""
import asyncio
import sys
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def quick_test():
    base = "http://localhost:5173"
    issues = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        print("="*60)
        print("CRITICAL SCREENS TEST")
        print("="*60)

        # Test 1: Home
        print("\n[1] HOME PAGE")
        await page.goto(base, wait_until="networkidle")
        await page.screenshot(path="D:/projects/github/claude-code-karma/test_home.png")
        print("  Loaded - Screenshot saved")

        # Test 2: Projects
        print("\n[2] PROJECTS PAGE")
        await page.goto(f"{base}/projects", wait_until="networkidle")
        await page.screenshot(path="D:/projects/github/claude-code-karma/test_projects.png")
        print("  Loaded - Screenshot saved")

        # Test 3: Project Detail
        print("\n[3] PROJECT DETAIL (karma-625f)")
        await page.goto(f"{base}/projects/karma-625f", wait_until="networkidle")
        await page.screenshot(path="D:/projects/github/claude-code-karma/test_project_detail.png")
        print("  Loaded - Screenshot saved")

        # Test 4: Session View
        print("\n[4] SESSION VIEW")
        await page.goto(f"{base}/projects/karma-625f/karma-625f", wait_until="networkidle")
        await page.screenshot(path="D:/projects/github/claude-code-karma/test_session.png")
        print("  Loaded - Screenshot saved")

        # Test 5: Subagent View
        print("\n[5] SUBAGENT VIEW")
        await page.goto(f"{base}/projects/karma-625f/karma-625f/agents/test", wait_until="networkidle")
        await page.screenshot(path="D:/projects/github/claude-code-karma/test_subagent.png")
        print("  Loaded - Screenshot saved")

        # Test 6: Agents
        print("\n[6] AGENTS PAGE")
        await page.goto(f"{base}/agents", wait_until="networkidle")
        await page.screenshot(path="D:/projects/github/claude-code-karma/test_agents.png")
        print("  Loaded - Screenshot saved")

        # Test 7: Analytics
        print("\n[7] ANALYTICS PAGE")
        await page.goto(f"{base}/analytics", wait_until="networkidle")
        await page.screenshot(path="D:/projects/github/claude-code-karma/test_analytics.png")
        print("  Loaded - Screenshot saved")

        print("\n" + "="*60)
        print(f"COMPLETE - {len(issues)} issues found")
        print("="*60)

        for issue in issues:
            print(f"  - {issue}")

        await browser.close()

asyncio.run(quick_test())
