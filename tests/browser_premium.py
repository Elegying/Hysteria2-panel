"""Exercise real dashboard controls against an isolated local HTTP fixture."""

import base64
import json
import pathlib
import subprocess  # nosec B404 -- fixed local Chrome executable and argv.
import sys
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_panel import PanelHttpTests  # noqa: E402

sys.path.insert(0, str(ROOT / ".github/scripts"))
from browser_smoke import chrome_executable  # noqa: E402

OUT = pathlib.Path(tempfile.mkdtemp(prefix="hy2-browser-controls-"))
OUT.mkdir(mode=0o700, exist_ok=True)


class Browser:
    def __init__(self, url):
        self.context = connect(url, proxy=None, max_size=32 * 1024 * 1024)
        self.ws = self.context.__enter__()
        self.sequence = 0
        self.accept = True
        self.dialogs = []
        self.errors = []

    def call(self, method, params=None):
        self.sequence += 1
        wanted = self.sequence
        self.ws.send(
            json.dumps({"id": wanted, "method": method, "params": params or {}})
        )
        until = time.monotonic() + 20
        while True:
            message = json.loads(
                self.ws.recv(timeout=max(0.01, until - time.monotonic()))
            )
            if message.get("method") == "Page.javascriptDialogOpening":
                self.dialogs.append(message["params"]["message"])
                self.sequence += 1
                self.ws.send(
                    json.dumps(
                        {
                            "id": self.sequence,
                            "method": "Page.handleJavaScriptDialog",
                            "params": {"accept": self.accept},
                        }
                    )
                )
            if message.get("method") == "Runtime.exceptionThrown":
                self.errors.append(message["params"])
            if message.get("id") == wanted:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message.get("result", {})

    def evaluate(self, expression):
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
        )
        if "exceptionDetails" in result:
            raise RuntimeError(str(result["exceptionDetails"]))
        return result.get("result", {}).get("value")

    def wait(self, expression, timeout=15):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            try:
                if self.evaluate("Boolean(" + expression + ")"):
                    return
            except RuntimeError:
                pass
            time.sleep(0.1)
        raise AssertionError("browser condition failed: " + expression)

    def navigate(self, url):
        tag = str(time.time_ns())
        self.evaluate("window.__auditDocument = " + json.dumps(tag))
        self.call("Page.navigate", {"url": url})
        self.wait(
            "window.__auditDocument !== "
            + json.dumps(tag)
            + " && location.href === "
            + json.dumps(url)
            + ' && document.readyState === "complete"'
        )

    def click(self, selector, navigation=False):
        tag = str(time.time_ns())
        point = self.evaluate(
            """(async () => {
            window.__auditDocument = %s;
            const e = document.querySelector(%s);
            if (!e) throw new Error('control is missing');
            if (e.disabled) throw new Error('control is disabled');
            let previous = null;
            let stable = 0;
            // Fragment navigation and scroll restoration can continue after load.
            // Stabilize the target and hit-test before sending a single real click.
            for (let frame = 0; frame < 120; frame++) {
                e.scrollIntoView({behavior:'instant',block:'center', inline:'center'});
                await new Promise(requestAnimationFrame);
                const r = e.getBoundingClientRect();
                if (!r.width || !r.height) throw new Error('control is hidden');
                const point = {x:r.x+r.width/2, y:r.y+r.height/2};
                const hit = document.elementFromPoint(point.x, point.y);
                stable = previous && previous.x === point.x && previous.y === point.y
                    && hit && (hit === e || e.contains(hit)) ? stable + 1 : 0;
                if (stable >= 2) return point;
                previous = point;
            }
            throw new Error('control did not settle at a hittable position');
        })()"""
            % (json.dumps(tag), json.dumps(selector))
        )
        self.call(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "button": "left", "clickCount": 1, **point},
        )
        self.call(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "button": "left", "clickCount": 1, **point},
        )
        if navigation:
            self.wait(
                "window.__auditDocument !== "
                + json.dumps(tag)
                + ' && document.readyState === "complete"'
            )

    def value(self, selector, value, event="input"):
        self.evaluate(
            """(() => {const e=document.querySelector(%s); e.value=%s; e.dispatchEvent(new Event(%s,{bubbles:true}));})()"""
            % (json.dumps(selector), json.dumps(value), json.dumps(event))
        )

    def screenshot(self, name):
        data = self.call(
            "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
        )
        (OUT / name).write_bytes(base64.b64decode(data["data"]))


fixture = PanelHttpTests("runTest")
fixture.setUp()
process = None
try:
    fixture.application.public_host = "vpn.example.test"
    fixture.db.create_proxy_user("subscription-demo", allow_udp_443=True)
    from tests.test_port_hopping import FakeHopping

    fixture.application.port_hopping_controller = FakeHopping()
    profile = tempfile.TemporaryDirectory(prefix="hy2-sub-browser-")
    log = (OUT / "chrome.log").open("wb")
    process = subprocess.Popen(
        [
            chrome_executable(),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--remote-debugging-port=0",
            "--user-data-dir=" + profile.name,
            "--window-size=1380,1000",
            "about:blank",
        ],
        stdout=log,
        stderr=log,
    )
    port_file = pathlib.Path(profile.name) / "DevToolsActivePort"
    for _ in range(100):
        if port_file.exists():
            break
        time.sleep(0.1)
    port = int(port_file.read_text().splitlines()[0])
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port))
    browser = Browser(
        next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
    )
    browser.call("Page.enable")
    browser.call("Runtime.enable")
    browser.navigate(fixture.base_url + "/login")
    browser.value("#username", "Elegy")
    browser.value("#password", "admin-password")
    browser.click(".login-form button", navigation=True)

    fixture.db.create_proxy_user(
        "premium-demo",
        user_type=1,
        device_limit=100,
        starts_at=1900000000,
        expires_at=2000000000,
    )
    browser.navigate(fixture.base_url + "/")
    assert (
        browser.evaluate(
            "document.querySelector('.user-group-tabs [aria-current=page]').textContent"
        )
        == "普通用户"
    )
    assert browser.evaluate(
        "document.querySelector('[data-user-name=premium-demo]')===null"
    )
    browser.click('[data-dialog-open="edit-user-dialog"]')
    browser.value("[data-edit-user-name-input]", "subscription-demo")
    browser.evaluate("loadEditUser()")
    browser.wait('!document.querySelector("[data-edit-user-fields]").disabled')
    assert browser.evaluate(
        'document.querySelector("[data-edit-user-status]").textContent.includes("已加载")'
    )
    browser.click("#edit-user-dialog [data-dialog-close]")
    browser.click(".user-group-tabs a[href*=premium]", navigation=True)
    assert (
        browser.evaluate(
            "document.querySelector('.user-group-tabs [aria-current=page]').textContent"
        )
        == "专线用户"
    )
    assert browser.evaluate(
        "document.querySelector('[data-user-name=subscription-demo]')===null"
    )
    assert browser.evaluate(
        "document.querySelector('[data-user-name=premium-demo]')!==null"
    )
    for width in (1380, 390):
        browser.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
        )
        browser.evaluate(
            "document.querySelector('.user-group-heading').scrollIntoView({block:'center',behavior:'instant'})"
        )
        assert browser.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        browser.screenshot("premium-tabs-" + str(width) + ".png")
    browser.click('[data-dialog-open="create-user-dialog"]')
    assert browser.evaluate('document.querySelector("#user_type").value') == "1"
    assert browser.evaluate('document.querySelector("#device_limit").value') == "100"
    browser.screenshot("premium-create.png")
    browser.click("#create-user-dialog [data-dialog-close]")
    browser.evaluate("document.querySelector('.node-onboarding-dialog').showModal()")
    browser.value("#node-tier", "premium", "change")
    browser.value("#node-region", "hk", "change")
    assert (
        browser.evaluate('document.querySelector("#node-host").value')
        == "hk.example.test"
    )
    assert (
        browser.evaluate('document.querySelector("#node-name").value')
        == "私家车-香港-专线"
    )
    assert browser.evaluate('document.querySelector("#node-port") === null')
    assert browser.evaluate('document.querySelector("#node-hopping").value') == "1"
    browser.value("#node-hopping", "0", "change")
    assert browser.evaluate('new FormData(document.querySelector("[data-node-enrollment-form]")).get("port_hopping")') == "0"
    browser.value("#node-hopping", "1", "change")
    browser.screenshot("premium-node-enrollment.png")
    assert not browser.errors, browser.errors
    print(
        json.dumps(
            {
                "passed": [
                    "default-normal",
                    "group-isolation",
                    "plan-defaults",
                    "region-autofill",
                    "automatic-port-hopping-switch",
                    "responsive-tabs",
                    "edit-user-load",
                ],
                "screenshots": str(OUT),
            },
            ensure_ascii=False,
        )
    )
finally:
    if process:
        process.terminate()
        process.wait(timeout=10)
    fixture.tearDown()
