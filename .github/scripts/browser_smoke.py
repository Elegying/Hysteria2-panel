#!/usr/bin/env python3
"""Render authenticated dashboard states in a real headless Chrome browser."""

import os
import pathlib
import shutil
import signal
import struct
import subprocess  # nosec B404 -- fixed local Chrome executable and argv.
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.test_panel import PanelHttpTests  # noqa: E402


def chrome_executable():
    candidates = (
        os.environ.get("CHROME_BIN", ""),
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    for candidate in candidates:
        if candidate and pathlib.Path(candidate).is_file():
            return candidate
    raise RuntimeError("Google Chrome or Chromium is required for browser smoke tests")


def png_size(path):
    data = pathlib.Path(path).read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Chrome did not create a valid PNG screenshot")
    return struct.unpack(">II", data[16:24]), len(data)


def render(chrome, html_path, output_path, width, height, profile_path):
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--disable-background-networking",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--user-data-dir={}".format(profile_path),
        "--window-size={},{}".format(width, height),
        "--virtual-time-budget=1500",
        "--screenshot={}".format(output_path),
        html_path.as_uri(),
    ]
    if os.geteuid() == 0:
        command.insert(1, "--no-sandbox")
    process = subprocess.Popen(  # nosec B603 -- fixed browser argv, no shell.
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if pathlib.Path(output_path).is_file() or process.poll() is not None:
            break
        time.sleep(0.1)
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    stderr = process.stderr.read() if process.stderr is not None else b""
    if not pathlib.Path(output_path).is_file():
        raise RuntimeError(
            "Chrome render failed: {}".format(
                stderr.decode("utf-8", errors="replace")[-2000:]
            )
        )
    dimensions, byte_count = png_size(output_path)
    if dimensions != (width, height) or byte_count < 10_000:
        raise RuntimeError(
            "unexpected browser render: dimensions={}, bytes={}".format(
                dimensions, byte_count
            )
        )


def main():
    fixture = PanelHttpTests("runTest")
    fixture.setUp()
    try:
        for name in ("browser-alice", "browser-bob", "long-mobile-account-name"):
            fixture.db.create_proxy_user(name)
        raw_token, _csrf = fixture.db.create_session(fixture.admin_id)
        request = urllib.request.Request(
            fixture.base_url + "/",
            headers={"Cookie": "hy2panel_session={}".format(raw_token)},
        )
        with urllib.request.urlopen(  # nosec B310 -- fixture URL is fixed loopback HTTP.
            request, timeout=3
        ) as response:
            dashboard = response.read(2 * 1024 * 1024)
        if b"Hysteria 2" not in dashboard or b"user-table" not in dashboard:
            raise RuntimeError("authenticated dashboard fixture is incomplete")
    finally:
        fixture.tearDown()

    chrome = chrome_executable()
    with tempfile.TemporaryDirectory(prefix="hy2panel-browser-smoke-") as directory:
        work = pathlib.Path(directory)
        html_path = work / "dashboard.html"
        html_path.write_bytes(dashboard)
        render(
            chrome,
            html_path,
            work / "desktop.png",
            1380,
            900,
            work / "desktop-profile",
        )
        render(
            chrome,
            html_path,
            work / "mobile.png",
            375,
            812,
            work / "mobile-profile",
        )
    print("browser smoke passed: authenticated dashboard rendered at 1380x900 and 375x812")


if __name__ == "__main__":
    main()
