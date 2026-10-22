"""Exercise large complete dashboards inside the disposable installer host."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import ssl
import statistics
import subprocess
import sys
import threading
import time


def main():
    if (os.geteuid() != 0 or os.environ.get("container") != "docker"
            or not Path("/workspace/tests/installer_e2e.sh").is_file()):
        raise SystemExit("This check requires the disposable installer host")
    values = {line.split("=", 1)[0]: shlex.split(line.split("=", 1)[1])[0]
              for line in Path("/etc/hysteria2-panel/panel.env").read_text().splitlines()
              if line.startswith("HY2PANEL_") and line.split("=", 1)[1]}
    if values["HY2PANEL_PANEL_PORT"] != "31998":
        raise SystemExit("Refusing a non-fixture panel")
    sys.path.insert(0, "/opt/hysteria2-panel")
    import hysteria2_panel as panel
    db = panel.Database(Path(values["HY2PANEL_DB"]), bytes.fromhex(values["HY2PANEL_HMAC_KEY"]))
    total = db.list_proxy_users(limit=1)["total"]
    if total > 1000:
        raise SystemExit("Unexpected fixture dataset")
    prefix = "capacity-" + secrets.token_hex(4)
    for index in range(1000 - total):
        db.create_proxy_user(prefix + "-{:04d}".format(index))
    admin = db.upsert_admin(prefix, secrets.token_urlsafe(32))
    token, _ = db.create_session(admin)

    def property_value(name):
        return subprocess.check_output(["systemctl", "show", "--property=" + name,
                                        "--value", "hysteria2-panel.service"], timeout=5).decode().strip()

    pid = int(property_value("MainPID"))
    restarts = property_value("NRestarts")
    assert int(property_value("MemoryMax")) == 256 * 1024**2
    stop, samples = threading.Event(), []

    def sample():
        while not stop.wait(.05):
            try:
                status = dict(line.split(":", 1) for line in Path("/proc", str(pid), "status")
                              .read_text().splitlines() if ":" in line)
                samples.append(int(status["VmRSS"].split()[0]))
            except (OSError, KeyError):
                pass

    tls = (ssl.create_default_context(cafile=values["HY2PANEL_PANEL_TLS_CERT"])
           if values["HY2PANEL_PANEL_SCHEME"] == "https" else None)
    cookie_name = "hy2panel_session" if tls else "hy2panel_http_session"

    def fetch(_index):
        before = time.monotonic()
        if tls:
            connection = http.client.HTTPSConnection(values["HY2PANEL_PANEL_PUBLIC_HOST"],
                                                      31998, context=tls, timeout=10)
            connection._create_connection = lambda address, timeout, source_address=None: (
                socket.create_connection(("127.0.0.1", address[1]), timeout, source_address))
        else:
            connection = http.client.HTTPConnection("127.0.0.1", 31998, timeout=10)
        try:
            connection.request("GET", "/", headers={"Cookie": cookie_name + "=" + token})
            response = connection.getresponse()
            body = response.read(8 * 1024 * 1024 + 1)
            assert response.status == 200, "dashboard HTTP {}".format(response.status)
            assert body.count(b"<tr data-user-name=") == 1000
            assert len(body) <= 8 * 1024 * 1024
            return time.monotonic() - before
        finally:
            connection.close()

    sampler = threading.Thread(target=sample)
    sampler.start()
    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            timings = list(pool.map(fetch, range(30)))
    finally:
        stop.set()
        sampler.join(timeout=2)
    assert int(property_value("MainPID")) == pid
    assert property_value("NRestarts") == restarts
    print(json.dumps({"result": "passed", "users": 1000, "clients": 10, "requests": 30,
                      "peakRssKiB": max(samples, default=0),
                      "medianSeconds": statistics.median(timings), "maxSeconds": max(timings)}))


if __name__ == "__main__":
    main()
