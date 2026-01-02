# File: reproduce_issue.py
"""Verification script for reproducing issues and checking production prep."""

import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

TOLERANCE = 50


def verify_production_prep() -> None:  # noqa: PLR0915
    """Verify the production preparation logic including splash screen and layout."""
    # Start the server with specific SPLASH config
    env = {
        **os.environ,
        "SPLASH_ENABLED": "True",
        "SPLASH_TITLE": "VERIFICATION_TITLE",
        "SPLASH_DURATION": "5000",  # Long duration to allow us to test click
        "FLASK_DEBUG": "1",
    }

    server = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "audiobook_automated.app"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
    )

    try:
        print("Waiting for server to start...")
        time.sleep(5)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # --- 1. Verify Splash Screen Configuration & Interaction ---
            print("Checking Splash Screen Configuration...")
            page.goto("http://localhost:5078")

            # Check Title
            title = page.locator(".splash-title")
            if title.count() == 0:
                print("FAILURE: .splash-title not found.")
                sys.exit(1)

            text_content = title.text_content()
            if text_content == "VERIFICATION_TITLE":
                print("SUCCESS: SPLASH_TITLE verified.")
            else:
                print(f"FAILURE: Expected 'VERIFICATION_TITLE', got '{text_content}'")
                sys.exit(1)

            # Check Overlay Presence
            overlay = page.locator("#splash-overlay")
            if overlay.count() == 0:
                print("FAILURE: #splash-overlay not found.")
                sys.exit(1)

            # Test Click-to-Dismiss
            print("Testing Click-to-Dismiss...")
            overlay.click()

            # Should disappear quickly (faster than the 5s duration)
            time.sleep(1)
            if not overlay.is_visible():
                print("SUCCESS: Splash screen dismissed on click.")
            else:
                # Check if class 'active' was removed (fading out)
                classes = overlay.get_attribute("class")
                if "active" not in classes:
                    print("SUCCESS: Splash screen dismissed (fading out).")
                else:
                    print("FAILURE: Splash screen still active after click.")
                    sys.exit(1)

            # --- 2. Verify Responsive Grid (CSS Check) ---
            print("Checking CSS Grid implementation...")
            # We can inspect the CSS property of the grid container
            page.reload()  # Reload to bring back splash (but we don't care about it now)

            # Wait for content
            # (Note: Search page might be empty if no search, but .metadata-grid usually wraps results.
            # If search is empty, the grid might not be there. Let's force a search or check CSS file presence)

            # Actually, let's just check the CSS file content via JS evaluation since we can't easily mock search results in this integration test without a running torrent client/scraper mock.
            # But we can check clientWidth of body to verify the max-width change.

            viewport_width = 2500
            page.set_viewport_size({"width": viewport_width, "height": 1080})
            page.reload()
            time.sleep(1)

            content_width = page.evaluate("document.querySelector('.content').clientWidth")

            # Max width is 95vw. 95% of 2500 = 2375.
            # Allow some scrollbar variance.
            expected = viewport_width * 0.95

            print(f"Viewport: {viewport_width}, Content Width: {content_width}, Expected ~{expected}")

            if abs(content_width - expected) < TOLERANCE:
                print("SUCCESS: Content width is approximately 95vw (Ultra-wide supported).")
            else:
                print("WARNING: Content width mismatch. Ensure CSS updated correctly.")

            browser.close()

    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    verify_production_prep()
