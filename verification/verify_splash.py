
from playwright.sync_api import sync_playwright, expect
import time
import re

def verify_splash():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Create context to simulate session storage
        context = browser.new_context()
        page = context.new_page()

        # 1. First Visit: Splash Screen should be visible immediately
        print("Visiting page for the first time...")
        page.goto("http://localhost:5000/")

        # Check splash overlay visibility
        # The overlay should be opacity: 1 by default
        splash = page.locator("#splash-overlay")
        expect(splash).to_be_visible()
        expect(splash).to_have_css("opacity", "1")

        # Take screenshot of splash
        print("Taking screenshot of splash screen...")
        page.screenshot(path="verification/splash_visible.png")

        # Wait for splash to dismiss (default 4.5s)
        # We can simulate click to dismiss faster
        print("Clicking to dismiss splash...")
        splash.click()

        # Wait for transition (1.5s)
        time.sleep(2)

        # Should be hidden
        expect(splash).not_to_be_visible()
        # Should have .hidden class using regex
        expect(splash).to_have_class(re.compile(r"hidden"))

        # Verify sessionStorage is set
        is_shown = page.evaluate("sessionStorage.getItem('splashShown')")
        assert is_shown == "true"
        print("SessionStorage 'splashShown' is verified as true.")

        # 2. Second Visit: Splash Screen should be hidden immediately
        print("Reloading page (simulating second visit)...")
        page.reload()

        # Check that 'no-splash' class is added to html immediately
        html = page.locator("html")
        expect(html).to_have_class(re.compile(r"no-splash"))

        # Splash should be hidden (display: none !important via css)
        expect(splash).not_to_be_visible()

        # Take screenshot of main page (no splash)
        print("Taking screenshot of main page (no splash)...")
        page.screenshot(path="verification/splash_hidden.png")

        browser.close()

if __name__ == "__main__":
    try:
        verify_splash()
        print("Verification script completed successfully.")
    except Exception as e:
        print(f"Verification failed: {e}")
        exit(1)
