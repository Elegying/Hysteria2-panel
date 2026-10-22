#!/usr/bin/env python3
"""Cross-engine core flows against a disposable, loopback-only panel."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import zipfile

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_panel import PanelHttpTests  # noqa: E402


def exercise(engine, output):
    fixture = PanelHttpTests("runTest")
    fixture.setUp()
    fixture.application.secure_cookies = False  # This fixture serves explicit HTTP.
    report = {"engine": engine, "passed": [], "result": "failed"}
    page = None
    try:
        fixture.db.create_proxy_user("core-existing")
        with sync_playwright() as playwright:
            with getattr(playwright, engine).launch() as browser:
                report["version"] = browser.version
                context = browser.new_context(viewport={"width": 1380, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(fixture.base_url + "/login")
                page.locator("#username").fill("Elegy")
                page.locator("#password").fill("admin-password")
                page.locator("#password").press("Enter")
                expect(page.locator("[data-egress-form]")).to_be_visible()
                report["passed"].append("keyboard-login")

                for label, width, scale in (("desktop", 1380, 1), ("narrow", 375, 1),
                                            ("zoom-200", 690, 2)):
                    original_page = page
                    zoom_context = None
                    if scale == 2:
                        # Browser zoom halves the CSS viewport and doubles DPR.
                        # CSS `zoom` alone does not update media queries.
                        zoom_context = browser.new_context(
                            viewport={"width": width, "height": 450}, device_scale_factor=2,
                            storage_state=context.storage_state())
                        page = zoom_context.new_page()
                        page.goto(fixture.base_url + "/")
                    else:
                        page.set_viewport_size({"width": width, "height": 900})
                    button = page.locator('[data-dialog-open="create-user-dialog"]')
                    button.focus()
                    button.press("Enter")
                    expect(page.locator("#create-user-dialog")).to_be_visible()
                    expect(page.locator("#name")).to_be_focused()
                    page.screenshot(path=str(output / (label + ".png")), full_page=True)
                    page.keyboard.press("Escape")
                    expect(page.locator("#create-user-dialog")).not_to_be_visible()
                    expect(button).to_be_focused()
                    dimensions = page.evaluate("""({width: innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        overflowing: [...document.querySelectorAll('main *')]
                          .filter(e => e.getBoundingClientRect().right > innerWidth + 1)
                          .slice(0, 12).map(e => ({tag: e.tagName, class: e.className,
                            right: e.getBoundingClientRect().right}))})""")
                    assert dimensions["scrollWidth"] <= dimensions["width"] + 1, dimensions
                    report["passed"].append(label + "-dialog-keyboard-focus")
                    if zoom_context is not None:
                        zoom_context.close()
                        page = original_page

                page.locator('[data-dialog-open="create-user-dialog"]').click()
                page.locator("#name").fill("core-created")
                page.locator("[data-create-user-form] button").click()
                expect(page.locator("#credentials-dialog")).to_be_visible()
                created = fixture.db.get_proxy_user_by_name("core-created")
                assert created is not None
                page.locator("#credentials-dialog [data-dialog-close]").click()
                expect(page.locator("#credentials-dialog")).not_to_be_visible()
                report["passed"].append("create-user")

                page.locator('[data-dialog-open="create-user-dialog"]').click()
                page.locator("#name").fill("core-created")
                page.locator("[data-create-user-form] button").click()
                expect(page.locator("[data-create-user-form] button")).to_be_enabled()
                assert len([u for u in fixture.db.list_proxy_users() if u["name"] == "core-created"]) == 1
                page.keyboard.press("Escape")
                report["passed"].append("duplicate-create-recovers")

                page.once("dialog", lambda dialog: dialog.dismiss())
                page.locator("[data-egress-form] button").click()
                assert fixture.egress_policy_controller.actions == []
                expect(page.locator("[data-egress-form] button")).to_be_enabled()
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator("[data-egress-form] button").click()
                expect(page.locator("[data-egress-state]")).to_have_text("FULL 已开启")
                assert fixture.egress_policy_controller.actions == ["full"]
                report["passed"].append("cancel-and-confirm-operation")

                page.locator('[data-dialog-open="migration-dialog"]').click()
                with page.expect_download() as download_event:
                    page.locator('form[action="/backup"] button').click()
                # Archives contain synthetic identities. Keep them private and
                # short-lived; never include them in public test artifacts.
                with tempfile.TemporaryDirectory(prefix="hy2-core-backup-") as temporary:
                    backup = Path(temporary) / "backup.zip"
                    download_event.value.save_as(backup)
                    with zipfile.ZipFile(backup) as package:
                        assert package.testzip() is None
                        assert "manifest.json" in package.namelist()
                page.locator("#migration-dialog [data-dialog-close]").click()
                report["passed"].append("backup-download")

                page.locator('form[action="/logout"] button').click()
                expect(page).to_have_url(fixture.base_url + "/login")
                page.goto(fixture.base_url + "/")
                expect(page).to_have_url(fixture.base_url + "/login")
                assert not errors, errors
                report["passed"].append("logout-revokes-session")
                report["result"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        fixture.tearDown()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("chromium", "firefox", "webkit"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    exercise(args.engine, args.output)
