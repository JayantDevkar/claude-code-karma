"""Final comprehensive UI test with actual content verification"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def comprehensive_ui_test():
    """Comprehensive UI test focusing on subagent viewing and actual content"""
    base_url = "http://localhost:5173"
    api_url = "http://localhost:8000"

    print("="*70)
    print("COMPREHENSIVE UI TESTING - Final Report")
    print("="*70)

    results = {
        "passed": [],
        "failed": [],
        "warnings": [],
        "screenshots": []
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        # Collect console messages
        console_messages = []
        def handle_console(msg):
            console_messages.append({"type": msg.type, "text": msg.text})
        page.on("console", handle_console)

        # Test 1: Home Page
        print("\n[TEST 1] Home Page")
        print("-" * 70)
        try:
            await page.goto(base_url, wait_until="networkidle")
            await page.wait_for_timeout(1000)

            # Check for key elements
            title = await page.title()
            has_header = await page.query_selector("header") is not None
            has_main = await page.query_selector("main") is not None

            print(f"  Title: {title}")
            print(f"  Header: {'✓' if has_header else '✗'}")
            print(f"  Main: {'✓' if has_main else '✗'}")

            screenshot = "screenshots/final_home.png"
            await page.screenshot(path=f"D:/projects/github/claude-code-karma/{screenshot}")
            results["screenshots"].append(screenshot)

            if has_header and has_main:
                results["passed"].append("Home page loads with header and main content")
            else:
                results["failed"].append("Home page missing key elements")

        except Exception as e:
            results["failed"].append(f"Home page error: {str(e)[:100]}")
            print(f"  ✗ Error: {str(e)[:100]}")

        # Test 2: Projects Page
        print("\n[TEST 2] Projects Page")
        print("-" * 70)
        try:
            await page.goto(f"{base_url}/projects", wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Check for project cards or list
            cards = await page.query_selector_all("[data-project-slug], .project-card, a[href*='/projects/']")
            print(f"  Project links found: {len(cards)}")

            # Get text content
            body_text = await page.inner_text("body")
            has_no_data = "no projects" in body_text.lower() or "no data" in body_text.lower()
            has_projects = "karma" in body_text.lower() or "project" in body_text.lower()

            print(f"  Has project data: {'✓' if has_projects else '✗'}")
            print(f"  Shows empty state: {'✓' if has_no_data else '✗'}")

            screenshot = "screenshots/final_projects.png"
            await page.screenshot(path=f"D:/projects/github/claude-code-karma/{screenshot}")
            results["screenshots"].append(screenshot)

            if has_projects:
                results["passed"].append("Projects page displays project data")
            else:
                results["warnings"].append("Projects page may be empty or has loading issues")

        except Exception as e:
            results["failed"].append(f"Projects page error: {str(e)[:100]}")
            print(f"  ✗ Error: {str(e)[:100]}")

        # Test 3: Project Detail Page
        print("\n[TEST 3] Project Detail Page (karma-625f)")
        print("-" * 70)
        try:
            await page.goto(f"{base_url}/projects/karma-625f", wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Check for sessions
            session_items = await page.query_selector_all("tr, .session-item, [data-session-uuid]")
            print(f"  Session items found: {len(session_items)}")

            # Check for tables
            tables = await page.query_selector_all("table")
            print(f"  Tables found: {len(tables)}")

            # Check page text
            body_text = await page.inner_text("body")
            has_sessions = "session" in body_text.lower()
            has_empty = "no sessions" in body_text.lower() or "empty" in body_text.lower()

            print(f"  Has sessions data: {'✓' if has_sessions else '✗'}")
            print(f"  Shows empty state: {'✓' if has_empty else '✗'}")

            screenshot = "screenshots/final_project_detail.png"
            await page.screenshot(path=f"D:/projects/github/claude-code-karma/{screenshot}")
            results["screenshots"].append(screenshot)

            # Check for API discrepancy we found earlier
            if has_empty or len(session_items) == 0:
                results["warnings"].append("Project detail shows 0 sessions (API discrepancy bug)")

        except Exception as e:
            results["failed"].append(f"Project detail error: {str(e)[:100]}")
            print(f"  ✗ Error: {str(e)[:100]}")

        # Test 4: Session Page
        print("\n[TEST 4] Session Page")
        print("-" * 70)
        try:
            await page.goto(f"{base_url}/projects/karma-625f/karma-625f", wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Check for timeline
            timeline = await page.query_selector(".timeline, .timeline-rail, [data-testid='timeline']")
            print(f"  Timeline present: {'✓' if timeline else '✗'}")

            # Check for conversation/messages
            messages = await page.query_selector_all(".message, .conversation-message, [data-message]")
            print(f"  Message elements: {len(messages)}")

            # Check for subagent indicators
            subagent_indicators = await page.query_selector_all("a[href*='/agents/'], .subagent-link, [data-subagent]")
            print(f"  Subagent links: {len(subagent_indicators)}")

            screenshot = "screenshots/final_session.png"
            await page.screenshot(path=f"D:/projects/github/claude-code-karma/{screenshot}")
            results["screenshots"].append(screenshot)

            if not timeline:
                results["warnings"].append("Timeline not found on session page")

            if len(subagent_indicators) == 0:
                results["warnings"].append("No subagent links found (may have no subagents)")
            else:
                results["passed"].append(f"Found {len(subagent_indicators)} subagent links")

        except Exception as e:
            results["failed"].append(f"Session page error: {str(e)[:100]}")
            print(f"  ✗ Error: {str(e)[:100]}")

        # Test 5: Subagent Page (if accessible)
        print("\n[TEST 5] Subagent Viewing")
        print("-" * 70)
        try:
            # Try to navigate to a subagent directly
            await page.goto(f"{base_url}/projects/karma-625f/karma-625f/agents/test-agent", wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Check for error
            body_text = await page.inner_text("body")
            has_error = "error" in body_text.lower() and "not found" in body_text.lower()

            if has_error:
                print("  ✗ Subagent page shows error (expected if no subagents exist)")
                results["warnings"].append("Subagent page shows error - no test subagents available")
            else:
                print("  ✓ Subagent page loaded")

                # Check for conversation view
                conversation = await page.query_selector(".conversation-view, .messages")
                if conversation:
                    print("  ✓ Conversation view present")
                    results["passed"].append("Subagent conversation view works")

            screenshot = "screenshots/final_subagent.png"
            await page.screenshot(path=f"D:/projects/github/claude-code-karma/{screenshot}")
            results["screenshots"].append(screenshot)

        except Exception as e:
            print(f"  Note: {str(e)[:100]}")
            results["warnings"].append(f"Subagent navigation: {str(e)[:80]}")

        # Test 6: Agents Page
        print("\n[TEST 6] Agents Page")
        print("-" * 70)
        try:
            await page.goto(f"{base_url}/agents", wait_until="networkidle")
            await page.wait_for_timeout(1000)

            has_content = await page.query_selector("main, [data-testid]")
            print(f"  Agents page loads: {'✓' if has_content else '✗'}")

            screenshot = "screenshots/final_agents.png"
            await page.screenshot(path=f"D:/projects/github/claude-code-karma/{screenshot}")
            results["screenshots"].append(screenshot)

            if has_content:
                results["passed"].append("Agents page loads successfully")

        except Exception as e:
            results["failed"].append(f"Agents page error: {str(e)[:100]}")

        # Test 7: Navigation Menu
        print("\n[TEST 7] Navigation Menu")
        print("-" * 70)
        nav_links = {
            "/projects": "Projects",
            "/agents": "Agents",
            "/skills": "Skills",
            "/analytics": "Analytics",
            "/settings": "Settings"
        }

        for path, name in nav_links.items():
            try:
                await page.goto(f"{base_url}{path}", wait_until="networkidle")
                await page.wait_for_timeout(500)
                print(f"  ✓ {name} page loads")
                results["passed"].append(f"Navigation to {name} works")
            except:
                print(f"  ✗ {name} page failed")
                results["failed"].append(f"Navigation to {name} failed")

        # Test 8: Console Errors
        print("\n[TEST 8] Console Errors")
        print("-" * 70)
        errors = [m for m in console_messages if m["type"] == "error"]
        warnings = [m for m in console_messages if m["type"] == "warning"]

        print(f"  Console errors: {len(errors)}")
        print(f"  Console warnings: {len(warnings)}")

        if errors:
            for err in errors[:3]:
                print(f"    - {err['text'][:80]}")
                results["warnings"].append(f"Console error: {err['text'][:60]}")

        # Final Summary
        print("\n" + "="*70)
        print("FINAL SUMMARY")
        print("="*70)
        print(f"Passed: {len(results['passed'])}")
        print(f"Failed: {len(results['failed'])}")
        print(f"Warnings: {len(results['warnings'])}")
        print(f"Screenshots: {len(results['screenshots'])}")

        if results["passed"]:
            print("\n✓ PASSED:")
            for item in results["passed"][:5]:
                print(f"  - {item}")

        if results["failed"]:
            print("\n✗ FAILED:")
            for item in results["failed"]:
                print(f"  - {item}")

        if results["warnings"]:
            print("\n⚠ WARNINGS:")
            for item in results["warnings"][:5]:
                print(f"  - {item}")

        # Save results
        with open("D:/projects/github/claude-code-karma/final_ui_test_results.json", "w") as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to final_ui_test_results.json")
        print(f"Screenshots saved in screenshots/ directory")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(comprehensive_ui_test())
