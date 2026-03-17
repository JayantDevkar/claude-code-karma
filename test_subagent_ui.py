"""Detailed subagent UI testing"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def test_subagent_viewing():
    """Test subagent session viewing in detail"""
    base_url = "http://localhost:5173"
    api_url = "http://localhost:8000"

    print("="*60)
    print("SUBAGENT SESSION VIEWING TEST")
    print("="*60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=1000)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        # First, find a session with subagents via API
        print("\n1. Finding session with subagents...")
        import httpx
        async with httpx.AsyncClient() as client:
            # Get projects
            projects_resp = await client.get(f"{api_url}/projects")
            projects = projects_resp.json()

            found_session = None
            for project in projects:
                if project.get("session_count", 0) > 0:
                    # Get project details
                    detail_resp = await client.get(f"{api_url}/projects/{project['slug']}")
                    detail = detail_resp.json()

                    for session in detail.get("sessions", []):
                        if session.get("subagent_count", 0) > 0:
                            found_session = {
                                "project_slug": project["slug"],
                                "session_uuid": session["uuid"],
                                "session_slug": session.get("slug", session["uuid"][:8]),
                                "subagent_count": session["subagent_count"]
                            }
                            print(f"   Found session: {session['uuid'][:8]} with {session['subagent_count']} subagents")
                            break
                    if found_session:
                        break

            if not found_session:
                print("   No sessions with subagents found. Creating test scenario...")
                # Use a known project and session
                found_session = {
                    "project_slug": projects[0]["slug"],
                    "session_uuid": "test-session",
                    "session_slug": projects[0]["slug"],
                    "subagent_count": 0
                }

        # Navigate to session page
        print(f"\n2. Navigating to session: {found_session['session_slug']}")
        session_url = f"{base_url}/projects/{found_session['project_slug']}/{found_session['session_slug']}"
        await page.goto(session_url, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Take screenshot
        await page.screenshot(path="D:/projects/github/claude-code-karma/screenshots/session_detail.png", full_page=True)
        print("   Screenshot saved: session_detail.png")

        # Check for subagent indicators
        print("\n3. Checking for subagent indicators...")

        # Look for subagent cards
        subagent_cards = await page.query_selector_all(".subagent-card, [data-testid='subagent-card'], .agent-card")
        print(f"   Subagent cards found: {len(subagent_cards)}")

        # Look for timeline subagent markers
        timeline_markers = await page.query_selector_all(".subagent-marker, .agent-marker, [data-subagent-id]")
        print(f"   Timeline markers found: {len(timeline_markers)}")

        # Check conversation overview for subagent links
        subagent_links = await page.query_selector_all("a[href*='/agents/']")
        print(f"   Subagent links found: {len(subagent_links)}")

        # If we have subagent links, click one
        if subagent_links:
            print(f"\n4. Clicking subagent link...")
            first_link = subagent_links[0]
            href = await first_link.get_attribute("href")
            print(f"   Link: {href}")

            # Click the link
            await first_link.click()
            await page.wait_for_timeout(3000)

            # Take screenshot of subagent view
            await page.screenshot(path="D:/projects/github/claude-code-karma/screenshots/subagent_view.png", full_page=True)
            print("   Screenshot saved: subagent_view.png")

            # Check subagent page elements
            print("\n5. Verifying subagent page elements...")

            checks = {
                "Conversation view": ".conversation-view, .messages, [data-testid='conversation']",
                "Back button": "a[href*='../'], .back-button, [data-testid='back']",
                "Agent info": ".agent-info, .agent-header, [data-testid='agent-info']",
                "Timeline": ".timeline, .timeline-rail, [data-testid='timeline']",
            }

            for check_name, selector in checks.items():
                element = await page.query_selector(selector)
                if element:
                    print(f"   ✓ {check_name}: Present")
                else:
                    print(f"   ✗ {check_name}: Missing")

        else:
            print("\n4. No subagent links found - checking session data...")
            # Check if session has subagents via API
            if found_session["subagent_count"] > 0:
                print("   Session should have subagents but UI doesn't show them - BUG!")
            else:
                print("   Session has no subagents - expected behavior")

        # Test navigation
        print("\n6. Testing navigation...")
        try:
            # Go back to session
            await page.go_back(wait_until="networkidle")
            await page.wait_for_timeout(1000)
            print("   ✓ Back navigation works")

            # Go forward to subagent
            await page.go_forward(wait_until="networkidle")
            await page.wait_for_timeout(1000)
            print("   ✓ Forward navigation works")
        except Exception as e:
            print(f"   ✗ Navigation error: {str(e)[:100]}")

        # Test keyboard navigation
        print("\n7. Testing keyboard shortcuts...")
        try:
            # Test ESC key
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            print("   ✓ ESC key registered")

            # Test Cmd+K (command palette)
            await page.keyboard.press("Meta+k")
            await page.wait_for_timeout(500)
            command_palette = await page.query_selector(".command-palette, [data-testid='command-palette']")
            if command_palette:
                print("   ✓ Cmd+K opens command palette")
                await page.keyboard.press("Escape")  # Close it
            else:
                print("   ✗ Cmd+K doesn't open command palette")
        except Exception as e:
            print(f"   ✗ Keyboard error: {str(e)[:100]}")

        await browser.close()

    print("\n" + "="*60)
    print("SUBAGENT TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_subagent_viewing())
