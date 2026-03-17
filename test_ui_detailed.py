"""Comprehensive UI testing for all screens"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class DetailedUITester:
    def __init__(self):
        self.base_url = "http://localhost:5173"
        self.issues = []
        self.warnings = []

    async def click_and_check(self, page, selector, description):
        """Click an element and check for errors"""
        try:
            element = await page.query_selector(selector)
            if not element:
                self.warnings.append(f"{description}: Element not found ({selector})")
                return False

            await element.click()
            await page.wait_for_timeout(1000)
            return True
        except Exception as e:
            self.issues.append(f"{description}: {str(e)[:100]}")
            return False

    async def test_navigation_menu(self, page):
        """Test main navigation menu"""
        print("\n[Navigation Menu Test]")

        nav_items = [
            ("a[href='/projects']", "Projects link"),
            ("a[href='/agents']", "Agents link"),
            ("a[href='/skills']", "Skills link"),
            ("a[href='/analytics']", "Analytics link"),
            ("a[href='/history']", "History link"),
            ("a[href='/settings']", "Settings link"),
        ]

        for selector, desc in nav_items:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                print(f"  ✓ {desc}: '{text.strip()[:30]}'")
            else:
                self.warnings.append(f"Missing: {desc}")
                print(f"  ✗ Missing: {desc}")

    async def test_project_card_actions(self, page):
        """Test project card interactions"""
        print("\n[Project Card Actions Test]")

        # Look for project cards
        cards = await page.query_selector_all(".project-card, [data-project-slug]")
        print(f"  Found {len(cards)} project cards")

        if cards:
            # Test first card
            first_card = cards[0]
            print("  Testing first card interactions...")

            # Check for link
            link = await first_card.query_selector("a")
            if link:
                href = await link.get_attribute("href")
                print(f"  ✓ Card link: {href}")

            # Check for any buttons
            buttons = await first_card.query_selector_all("button")
            print(f"  ✓ Buttons in card: {len(buttons)}")

    async def test_filters_and_search(self, page):
        """Test filter and search functionality"""
        print("\n[Filters & Search Test]")

        # Look for search inputs
        search_inputs = await page.query_selector_all("input[type='search'], input[placeholder*='search' i], input[placeholder*='filter' i]")
        print(f"  Found {len(search_inputs)} search/filter inputs")

        # Look for filter buttons/dropdowns
        filter_buttons = await page.query_selector_all("button:has-text('Filter'), button:has-text('Sort'), select")
        print(f"  Found {len(filter_buttons)} filter controls")

        # Try typing in search if found
        if search_inputs:
            try:
                await search_inputs[0].fill("test")
                await page.wait_for_timeout(500)
                await search_inputs[0].fill("")
                print("  ✓ Search input works")
            except:
                print("  ✗ Search input failed")

    async def test_pagination(self, page):
        """Test pagination controls"""
        print("\n[Pagination Test]")

        # Look for pagination
        pagination = await page.query_selector_all(".pagination, nav[aria-label*='pagination' i], button:has-text('Next')")
        print(f"  Found {len(pagination)} pagination controls")

        if pagination:
            print("  ✓ Pagination controls present")

    async def test_responsive_layout(self, page):
        """Test responsive design"""
        print("\n[Responsive Layout Test]")

        sizes = [
            (1920, 1080, "Desktop"),
            (768, 1024, "Tablet"),
            (375, 667, "Mobile"),
        ]

        for width, height, name in sizes:
            await page.set_viewport_size({"width": width, "height": height})
            await page.wait_for_timeout(500)

            # Check for horizontal scrollbar (bad)
            has_scroll = await page.evaluate("() => document.body.scrollWidth > window.innerWidth")
            if has_scroll:
                self.warnings.append(f"Horizontal scroll on {name}")
                print(f"  ✗ {name}: Has horizontal scroll")
            else:
                print(f"  ✓ {name}: No horizontal scroll")

        # Reset to desktop
        await page.set_viewport_size({"width": 1920, "height": 1080})

    async def test_console_errors(self, page):
        """Check for console errors"""
        print("\n[Console Errors Test]")

        errors = []
        page.on("console", lambda msg: errors.append(msg) if msg.type == "error" else None)

        # Navigate around
        await page.goto(f"{self.base_url}/projects")
        await page.wait_for_timeout(1000)
        await page.goto(f"{self.base_url}/agents")
        await page.wait_for_timeout(1000)

        await page.wait_for_timeout(2000)  # Wait for any delayed errors

        if errors:
            print(f"  ✗ Found {len(errors)} console errors")
            for err in errors[:5]:  # First 5
                self.issues.append(f"Console error: {err.text[:100]}")
                print(f"    - {err.text[:80]}")
        else:
            print("  ✓ No console errors")

    async def test_timeline_interaction(self, page):
        """Test timeline component"""
        print("\n[Timeline Interaction Test]")

        # Go to a session page
        await page.goto(f"{self.base_url}/projects/karma-625f/karma-625f")
        await page.wait_for_timeout(2000)

        # Look for timeline
        timeline = await page.query_selector(".timeline, .timeline-rail, [data-testid='timeline']")
        if timeline:
            print("  ✓ Timeline present")

            # Look for timeline items
            items = await page.query_selector_all(".timeline-item, .event-item, [data-timeline-event]")
            print(f"  ✓ Timeline items: {len(items)}")

            # Try clicking an item if present
            if items:
                await items[0].click()
                await page.wait_for_timeout(500)
                print("  ✓ Timeline item clickable")
        else:
            self.warnings.append("Timeline not found on session page")
            print("  ✗ Timeline not found")

    async def test_accessibility(self, page):
        """Basic accessibility checks"""
        print("\n[Accessibility Test]")

        # Check for aria labels on important elements
        important_selectors = [
            ("button", "Buttons without aria-label"),
            ("input", "Inputs without labels"),
        ]

        for selector, desc in important_selectors:
            elements = await page.query_selector_all(selector)
            without_labels = []
            for el in elements[:10]:  # Check first 10
                aria_label = await el.get_attribute("aria-label")
                aria_labelledby = await el.get_attribute("aria-labelledby")
                if not aria_label and not aria_labelledby:
                    without_labels.append(selector)

            if without_labels:
                self.warnings.append(f"{desc}: {len(without_labels)} elements")
                print(f"  ⚠ {desc}: {len(without_labels)}/10")
            else:
                print(f"  ✓ {desc}: All checked")

    async def run_tests(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})

            # Start at home
            await page.goto(self.base_url, wait_until="networkidle")
            await page.wait_for_timeout(1000)

            # Run all tests
            await self.test_navigation_menu(page)
            await self.test_project_card_actions(page)
            await self.test_filters_and_search(page)
            await self.test_pagination(page)
            await self.test_timeline_interaction(page)
            await self.test_accessibility(page)

            print("\n" + "="*60)
            print("DETAILED UI TEST SUMMARY")
            print("="*60)
            print(f"Issues: {len(self.issues)}")
            print(f"Warnings: {len(self.warnings)}")

            if self.issues:
                print("\n--- ISSUES ---")
                for issue in self.issues:
                    print(f"  - {issue}")

            if self.warnings:
                print("\n--- WARNINGS ---")
                for warning in self.warnings[:10]:  # First 10
                    print(f"  - {warning}")

            if not self.issues and not self.warnings:
                print("\n✓ All tests passed!")

            # Save results
            results = {
                "issues": self.issues,
                "warnings": self.warnings,
                "timestamp": str(asyncio.get_event_loop().time())
            }
            with open("D:/projects/github/claude-code-karma/detailed_ui_test_results.json", "w") as f:
                json.dump(results, f, indent=2)

            await browser.close()

if __name__ == "__main__":
    tester = DetailedUITester()
    asyncio.run(tester.run_tests())
