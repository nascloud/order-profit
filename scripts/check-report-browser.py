"""Verify a packaged program's generated HTML with Chromium, entirely offline."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def check_report_browser(report: Path, screenshot: Path) -> dict:
    errors, remote_requests = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: remote_requests.append(request.url)
                    if request.url.startswith(("http:", "https:")) else None)
            page.goto(report.resolve().as_uri())
            expect(page.locator("#profitFormula .value")).to_have_count(10)
            for view in ("daily", "products", "links"):
                page.locator(f'nav [data-view="{view}"]').click()
                expect(page.locator(f"#{view}Grid.tabulator")).to_be_visible()
                page.locator(f'#{view} [data-preset="cost"]').click()
                page.locator(f'#{view} [data-preset="all"]').click()
                page.locator(f'#{view} [data-preset="overview"]').click()
            page.locator('nav [data-view="daily"]').click()
            expect(page.locator("#dailyChart svg")).to_be_visible()
            page.locator('nav [data-view="products"]').click()
            expect(page.locator("#productChart svg")).to_be_visible()
            page.locator('nav [data-view="links"]').click()
            page.locator('#linkRank').select_option('sales')
            expect(page.locator("#linkTopChart svg")).to_be_visible()
            page.locator('#linksGrid').get_by_role('button', name='详情', exact=True).first.click()
            expect(page.locator('#rowDetail')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.locator('#rowDetail')).to_be_hidden()
            expect(page.locator('#reportError')).to_be_hidden()
            assert not errors, errors
            assert not remote_requests, remote_requests
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
            return {"status": "passed", "remote_requests": 0, "page_errors": 0,
                    "screenshot": screenshot.name}
        finally:
            browser.close()
