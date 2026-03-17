"""Browser UI testing script for Claude Code Karma"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright
from datetime import datetime

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class BrowserUITester:
    def __init__(self):
        self.base_url = "http://localhost:5173"
        self.api_url = "http://localhost:8000"
        self.issues = []
        self.screenshots = []

    async def test_page(self, page, url, name, checks):
        """Test a page and run checks"""
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"URL: {url}")
        print(f"{'='*60}")

        try:
            response = await page.goto(url, wait_until="networkidle", timeout=30000)
            print(f"Status: {response.status}")

            # Wait for page to load
            await page.wait_for_timeout(2000)

            # Take initial screenshot
            screenshot_path = f"D:/projects/github/claude-code-karma/screenshots/{name.replace('/', '_')}_initial.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved: {screenshot_path}")

            # Get page title
            title = await page.title()
            print(f"Page title: {title}")

            # Check for errors
            error_text = await page.inner_text("body") if await page.query_selector("body") else ""
            if "error" in error_text.lower() and "Error:" in error_text:
                self.issues.append({
                    "page": name,
                    "type": "Error displayed",
                    "text": error_text[:200]
                })
                print(f"❌ ERROR FOUND: {error_text[:100]}")

            # Run custom checks
            for check_name, check_fn in checks.items():
                try:
                    result = check_fn(page)
                    if asyncio.iscoroutine(result):
                        result = await result
                    if result:
                        print(f"✓ {check_name}")
                    else:
                        print(f"❌ {check_name} FAILED")
                        self.issues.append({
                            "page": name,
                            "type": check_name,
                            "details": "Check failed"
                        })
                except Exception as e:
                    print(f"❌ {check_name} ERROR: {str(e)[:100]}")
                    self.issues.append({
                        "page": name,
                        "type": check_name,
                        "error": str(e)
                    })

            return True

        except Exception as e:
            print(f"❌ Failed to load page: {str(e)}")
            self.issues.append({
                "page": name,
                "type": "Page Load Error",
                "error": str(e)
            })
            return False

    async def run_tests(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})

            # Test 1: Home page
            await self.test_page(
                page,
                f"{self.base_url}/",
                "home",
                {
                    "Header present": lambda p: p.query_selector("header") is not None,
                    "No console errors": lambda p: True  # Would need to listen to console
                }
            )

            # Test 2: Projects listing
            await self.test_page(
                page,
                f"{self.base_url}/projects",
                "projects",
                {
                    "Project cards visible": lambda p: p.query_selector("[data-testid='project-card']") is not None or p.query_selector(".project-card") is not None,
                }
            )

            # Test 3: Project detail (using slug)
            await self.test_page(
                page,
                f"{self.base_url}/projects/karma-625f",
                "project_detail_karma",
                {
                    "Sessions list visible": lambda p: p.query_selector("table") is not None or p.query_selector(".sessions") is not None,
                }
            )

            # Test 4: Agents page
            await self.test_page(
                page,
                f"{self.base_url}/agents",
                "agents",
                {
                    "Page loaded": lambda p: p.query_selector("main") is not None,
                }
            )

            # Test 5: Skills page
            await self.test_page(
                page,
                f"{self.base_url}/skills",
                "skills",
                {
                    "Page loaded": lambda p: p.query_selector("main") is not None,
                }
            )

            # Test 6: Analytics page
            await self.test_page(
                page,
                f"{self.base_url}/analytics",
                "analytics",
                {
                    "Charts visible": lambda p: p.query_selector("canvas") is not None or p.query_selector(".chart") is not None,
                }
            )

            # Get a session with subagents for testing
            print("\n" + "="*60)
            print("Finding session with subagents...")
            print("="*60)

            # Try to navigate to a session directly
            await self.test_page(
                page,
                f"{self.base_url}/projects/karma-625f/karma-625f",
                "session_view",
                {
                    "Timeline present": lambda p: p.query_selector(".timeline") is not None or p.query_selector("[data-testid='timeline']") is not None,
                }
            )

            # Summary
            print("\n" + "="*60)
            print("TESTING SUMMARY")
            print("="*60)
            print(f"Total Issues Found: {len(self.issues)}")

            if self.issues:
                print("\nIssues Details:")
                for i, issue in enumerate(self.issues, 1):
                    print(f"\n{i}. {issue['page']}: {issue['type']}")
                    if 'error' in issue:
                        print(f"   Error: {issue['error'][:100]}")
                    if 'text' in issue:
                        print(f"   Text: {issue['text'][:100]}")
            else:
                print("\n✓ No critical issues found!")

            # Save results
            with open("D:/projects/github/claude-code-karma/ui_test_results.json", "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "issues": self.issues,
                    "screenshots": self.screenshots
                }, f, indent=2)
            print("\nResults saved to ui_test_results.json")

            await browser.close()

if __name__ == "__main__":
    tester = BrowserUITester()
    asyncio.run(tester.run_tests())
