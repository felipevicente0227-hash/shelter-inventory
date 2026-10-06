"""
dev/smoke_browser.py - the browser version end to end, in headless Chromium.

Builds _site/ the way .github/workflows/pages.yml does, serves it on
localhost, and checks that:
  * the real backend starts (Python via Pyodide - not the demo data)
  * an added item survives a reload
  * docs/examples/example-stock-list.csv imports
  * a downloaded backup restores into a fresh browser
  * a second tab is refused, so two tabs cannot overwrite each other
  * the page talks to nobody except this site and the pinned Pyodide CDN

    py dev/smoke_browser.py

Needs the playwright package and its Chromium (py -m playwright install
chromium). Exits with 2 and says SKIPPED if Chromium is not installed.
Screenshots go to dev/ (gitignored: dev/*.png).
"""

import functools
import http.server
import json
import shutil
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"


def build_site():
    shutil.rmtree(SITE, ignore_errors=True)
    SITE.mkdir()
    for f in ("webui/index.html", "webui/browser_api.py", "webui/sw.js", "inventory_core.py"):
        shutil.copy(ROOT / f, SITE / Path(f).name)
    shutil.copy(ROOT / "icon.ico", SITE / "favicon.ico")


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(SITE))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://localhost:{httpd.server_address[1]}/"


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIPPED: the playwright package is not installed.")
        return 2
    build_site()
    httpd, url = serve()
    hosts, errors = set(), []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as err:
            print(f"SKIPPED: Chromium for Playwright is not installed ({str(err).splitlines()[0]})")
            return 2

        def new_page(ctx):
            page = ctx.new_page()
            page.on("request", lambda r: hosts.add(r.url.split("/")[2]))
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.on("pageerror", lambda e: errors.append(str(e)))
            return page

        def ready(page):
            page.wait_for_function(
                "window.siBackend && window.siBackend() === 'browser' && document.querySelector('#boot').hidden && state",
                timeout=180_000)

        def names(page):
            return page.evaluate("state.items.map(i => i.name)")

        ctx = browser.new_context(accept_downloads=True)
        page = new_page(ctx)
        page.goto(url)
        ready(page)
        print("1. loads with the real backend:", page.evaluate("window.siBackend()"),
              "| Python's today:", page.evaluate("state.today"), "| version:", page.evaluate("state.version"))

        page.wait_for_selector("#mWelcome.on")
        page.fill("#wName", "Smoke Shelter")
        page.click("#wEmpty")
        page.click("#btnAdd")
        page.fill("#iName", "Smoke soup")
        page.fill("#iCurr", "3")
        page.fill("#iTgt", "10")
        page.click("#iSave")
        page.wait_for_function("state.items.length === 1")
        page.reload()
        ready(page)
        assert names(page) == ["Smoke soup"], names(page)
        assert not page.is_visible("#mWelcome.on"), "welcome shown again after reload"
        assert page.evaluate("state.settings.charity_name") == "Smoke Shelter"
        print("2. an added item survives a reload:", names(page))

        with page.expect_file_chooser() as fc:
            page.click("#btnImport")
        fc.value.set_files(str(ROOT / "docs" / "examples" / "example-stock-list.csv"))
        page.wait_for_selector("#mImport.on")
        page.click("#impSkip")
        page.wait_for_function("state.items.length === 5")
        page.reload()
        ready(page)
        assert len(names(page)) == 5, names(page)
        print("3. CSV import (and it survives a reload):", names(page))

        assert page.is_visible("#backupBanner"), "backup banner should show at 5 items"
        assert not page.is_visible("#navFolder"), "Data folder must be hidden in the browser"
        page.click("#navSettings")
        with page.expect_download() as dl:
            page.click("#sBackup")
        backup = ROOT / "dev" / dl.value.suggested_filename
        dl.value.save_as(backup)
        page.keyboard.press("Escape")
        assert not page.is_visible("#backupBanner"), "banner should hide after a backup"
        assert len(json.loads(backup.read_text(encoding="utf-8"))["items"]) == 5
        print("4. backup downloaded:", backup.name, "- banner hidden afterwards")

        second = new_page(ctx)
        second.goto(url)
        second.wait_for_function("document.querySelector('#bootTitle').textContent.includes('another tab')", timeout=30_000)
        assert second.evaluate("window.siBackend()") == "demo" and not second.evaluate("state"), "second tab must not load the data"
        second.close()
        print("   a second tab is refused (one tab at a time, so they cannot overwrite each other)")

        page.click("#navHelp")
        help_text = page.inner_text("#helpFolder")
        assert help_text.startswith("This is the browser version."), help_text
        page.keyboard.press("Escape")
        page.screenshot(path=str(ROOT / "dev" / "browser-desktop.png"))

        fresh = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                    has_touch=True)
        phone = new_page(fresh)
        phone.goto(url)
        ready(phone)
        phone.wait_for_selector("#mWelcome.on")
        with phone.expect_file_chooser() as fc:
            phone.click("#wRestore")
        fc.value.set_files(str(backup))
        phone.wait_for_selector("#mRestore.on")
        print("5. restore preview:", phone.inner_text("#rstText").replace("\n", " "))
        phone.click("#rstGo")      # fresh browser: nothing to keep, so no pre-restore download
        phone.wait_for_function("state.items.length === 5")
        assert phone.evaluate("state.settings.charity_name") == "Smoke Shelter"
        phone.click("[data-view=dash]")
        phone.screenshot(path=str(ROOT / "dev" / "browser-phone.png"), full_page=True)
        phone.click("[data-view=inv]")
        phone.screenshot(path=str(ROOT / "dev" / "browser-phone-inventory.png"))
        print("   restored into a fresh (phone-sized) browser:", names(phone))
        backup.unlink()
        browser.close()
    httpd.shutdown()

    expected = {url.split("/")[2], "cdn.jsdelivr.net"}
    print("6. hosts contacted:", sorted(hosts))
    assert hosts <= expected, f"unexpected hosts: {hosts - expected}"
    real_errors = [e for e in errors if "favicon" not in e]
    if real_errors:
        print("console errors:", *real_errors, sep="\n  ")
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
