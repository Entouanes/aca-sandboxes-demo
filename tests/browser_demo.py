"""Run against the local simulation server, not a billable Azure environment."""

import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

url = os.getenv("DEMO_TEST_URL", "http://127.0.0.1:8080")
key = os.environ["DEMO_API_KEY"]
artifacts = Path(os.getenv("DEMO_SCREENSHOT_DIR", "test-results"))
artifacts.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1080})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading", name="From zero. To ready.")).to_be_visible()
    page.get_by_label("Presenter access key").fill(key)
    page.get_by_role("button", name="Connect", exact=True).click()
    expect(page.locator("#mode")).to_have_text("SIMULATION / NO AZURE")
    page.get_by_label("How many sandboxes?").fill("12")
    page.get_by_role("button", name="Launch sandboxes").click()
    expect(page.locator(".tile.red")).to_have_count(12)
    expect(page.locator(".tile.orange").first).to_be_visible(timeout=10000)
    page.screenshot(path=str(artifacts / "initializing.png"), full_page=True)
    expect(page.locator(".tile.green")).to_have_count(12, timeout=30000)
    expect(page.locator("#ready-count")).to_have_text("12")
    page.screenshot(path=str(artifacts / "ready.png"), full_page=True)
    page.locator(".tile").first.click()
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.locator("#detail-output")).to_contain_text("simulated")
    page.get_by_role("button", name="Close sandbox details").click()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete fleet").click()
    expect(page.locator(".tile")).to_have_count(0, timeout=15000)
    expect(page.get_by_role("heading", name="A clean slate.")).to_be_visible()
    assert not errors, errors
    browser.close()

print("Browser demo passed: 12 red -> orange -> green tiles, details, mobile layout, cleanup.")
