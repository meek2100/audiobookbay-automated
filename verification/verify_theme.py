from playwright.sync_api import Page, expect, sync_playwright

def verify_theme_toggle(page: Page):
    # Load the page
    page.goto("http://localhost:5078/")

    # 1. Verify Default Theme (Crow)
    # data-theme should be "crow" (set by JS on load)
    # Check <html> element
    html = page.locator("html")
    expect(html).to_have_attribute("data-theme", "crow")

    # Verify button text
    toggle_btn = page.locator("#theme-toggle-btn")
    expect(toggle_btn).to_have_text("🌙 Crow")

    # 2. Toggle to Purple
    toggle_btn.click()

    # Verify attribute update
    expect(html).to_have_attribute("data-theme", "purple")
    expect(toggle_btn).to_have_text("🔮 Purple")

    # Take screenshot of Purple Theme
    page.screenshot(path="verification/theme_purple.png")

    # 3. Toggle back to Crow
    toggle_btn.click()
    expect(html).to_have_attribute("data-theme", "crow")
    expect(toggle_btn).to_have_text("🌙 Crow")

    # Take screenshot of Crow Theme
    page.screenshot(path="verification/theme_crow.png")

    # 4. Verify Persistence
    page.reload()
    expect(html).to_have_attribute("data-theme", "crow")

    # Set purple and reload
    toggle_btn.click()
    page.reload()
    expect(html).to_have_attribute("data-theme", "purple")

    print("Theme verification passed!")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            verify_theme_toggle(page)
        except Exception as e:
            print(f"Verification failed: {e}")
            exit(1)
        finally:
            browser.close()
