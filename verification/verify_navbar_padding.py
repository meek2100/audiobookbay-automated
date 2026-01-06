from playwright.sync_api import Page, expect, sync_playwright

def verify_navbar_padding(page: Page):
    """
    Verifies that the 'Reload Library' icon button does NOT have the padding
    applied to standard navbar links.
    """
    # 1. Read the CSS content
    with open("audiobook_automated/static/css/style.css", "r") as f:
        css_content = f.read()

    # 2. Inject HTML with the CSS
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            {css_content}
        </style>
    </head>
    <body>
        <nav class="navbar">
            <div class="nav-container">
                <div class="nav-links">
                    <a href="#">Normal Link</a>
                    <a href="#" class="btn-icon">
                        <!-- Simulate SVG icon -->
                        <svg width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor"/></svg>
                    </a>
                </div>
            </div>
        </nav>
    </body>
    </html>
    """

    page.route("**/", lambda route: route.fulfill(
        status=200,
        content_type="text/html",
        body=html_content
    ))

    page.goto("http://localhost/")

    # 3. Verify standard link padding
    normal_link = page.locator("a:text('Normal Link')")
    # Expected padding from CSS: "8px 18px"
    # Computed style usually returns resolved values like "8px" for top/bottom etc.
    expect(normal_link).to_have_css("padding-top", "8px")
    expect(normal_link).to_have_css("padding-bottom", "8px")
    expect(normal_link).to_have_css("padding-left", "18px")
    expect(normal_link).to_have_css("padding-right", "18px")

    # 4. Verify btn-icon padding
    # Expected padding for btn-icon is 0 (from .btn-icon class)
    # The generic rule should NOT apply
    icon_btn = page.locator("a.btn-icon")
    expect(icon_btn).to_have_css("padding-top", "0px")
    expect(icon_btn).to_have_css("padding-bottom", "0px")
    expect(icon_btn).to_have_css("padding-left", "0px")
    expect(icon_btn).to_have_css("padding-right", "0px")

    # 5. Screenshot
    page.screenshot(path="/home/jules/verification/navbar_verification.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            verify_navbar_padding(page)
            print("Verification script completed successfully.")
        except Exception as e:
            print(f"Verification failed: {e}")
            raise e
        finally:
            browser.close()
