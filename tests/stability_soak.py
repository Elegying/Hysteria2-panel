#!/usr/bin/env python3
"""Real installed services in the dedicated disposable systemd container only.

1000 users, 10 signed synthetic node reporters, 10 real Hysteria clients with
100 persistent TCP streams across both entrypoints, and 10 dashboard readers.
No production configuration, trust rule, quota or service limit is relaxed.
"""

import argparse
import base64
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shlex
import signal
import socket
import socketserver
import ssl
import statistics
import struct
import subprocess
import sys
import threading
import time
import uuid

TLS_CONTEXT = None


def command(*args):
    return subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=15).decode().strip()


def request(port, path, data=None, cookie=None):
    connection = (http.client.HTTPSConnection("127.0.0.1", port, timeout=9, context=TLS_CONTEXT)
                  if port == 31998 else http.client.HTTPConnection("127.0.0.1", port, timeout=9))
    try:
        headers = {"Content-Type": "application/json"}
        if cookie is not None:
            headers["Cookie"] = cookie
        connection.request("GET" if data is None else "POST", path,
                           None if data is None else json.dumps(data).encode(), headers)
        response = connection.getresponse()
        body = response.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024:
            raise RuntimeError("oversized fixture response")
        return response.status, body
    finally:
        connection.close()


def receive(sock, length):
    chunks = bytearray()
    while len(chunks) < length:
        chunk = sock.recv(length - len(chunks))
        if not chunk:
            raise RuntimeError("unexpected stream close")
        chunks.extend(chunk)
    return bytes(chunks)


def connect_stream(port):
    sock = socket.create_connection(("127.0.0.1", port), timeout=9)
    try:
        sock.sendall(b"\x05\x01\x00")
        if receive(sock, 2) != b"\x05\x00":
            raise RuntimeError("SOCKS negotiation failed")
        sock.sendall(b"\x05\x01\x00\x01" + socket.inet_aton("198.18.0.2") + struct.pack("!H", 32080))
        header = receive(sock, 4)
        if header[:2] != b"\x05\x00":
            raise RuntimeError("data-plane connection rejected")
        size = {1: 4, 4: 16}.get(header[3])
        if size is None:
            size = receive(sock, 1)[0]
        receive(sock, size + 2)
        return sock
    except BaseException:
        sock.close()
        raise


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(15)
        try:
            while True:
                body = self.request.recv(4096)
                if not body:
                    break
                self.request.sendall(body)
        except OSError:
            pass


class EchoServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


def main():
    global TLS_CONTEXT
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--seconds", type=int, default=48 * 3600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (os.geteuid() != 0 or os.environ.get("container") != "docker"
            or os.environ.get("HY2_STABILITY_ISOLATED") != "1"
            or not Path("/workspace/tests/installer_e2e.sh").is_file()):
        raise SystemExit("Refusing to run outside the dedicated isolated installer container")
    env_path = Path("/etc/hysteria2-panel/panel.env")
    values = {line.split("=", 1)[0]: shlex.split(line.split("=", 1)[1])[0]
              for line in env_path.read_text().splitlines() if line.startswith("HY2PANEL_") and line.split("=", 1)[1]}
    if values.get("HY2PANEL_PANEL_PORT") != "31998" or values.get("HY2PANEL_AUTH_PORT") != "31996":
        raise SystemExit("Refusing a non-fixture deployment")
    if len(args.candidate) != 40 or any(c not in "0123456789abcdef" for c in args.candidate):
        raise SystemExit("A complete candidate SHA is required")
    for name in ("hysteria2_panel.py", "hy2panel/accounting.py", "hy2panel/mobile_api.py"):
        if Path("/workspace", name).read_bytes() != Path("/opt/hysteria2-panel", name).read_bytes():
            raise SystemExit("Installed candidate does not match workspace: " + name)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    sys.path.insert(0, "/opt/hysteria2-panel")
    sys.path.insert(1, "/workspace")
    import hysteria2_panel as panel
    import node_agent
    from hy2panel.distributed import canonical_node_request
    db = panel.Database(Path(values["HY2PANEL_DB"]), bytes.fromhex(values["HY2PANEL_HMAC_KEY"]))
    if db.list_proxy_users(limit=1) or db.list_nodes():
        raise SystemExit("Fixture must start with an empty user/node dataset")
    # Enable HTTPS with a fixture-only CA, retaining the separate Hysteria identity.
    import grp
    certificate = env_path.parent / "stability.crt"
    key = env_path.parent / "stability.key"
    if certificate.exists() or key.exists():
        raise SystemExit("Retain the earlier fixture evidence; use a clean test container")
    command("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "7",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout", str(key), "-out", str(certificate))
    key.chmod(0o640)
    os.chown(key, 0, grp.getgrnam("hy2panel").gr_gid)
    certificate.chmod(0o644)
    replacements = {"HY2PANEL_PANEL_SCHEME": "https", "HY2PANEL_PANEL_PUBLIC_HOST": "localhost",
                    "HY2PANEL_PANEL_TLS_CERT": str(certificate), "HY2PANEL_PANEL_TLS_KEY": str(key)}
    original = env_path.read_text()
    (args.output / "original-panel.env").write_text(original)
    lines = [line for line in original.splitlines() if line.split("=", 1)[0] not in replacements]
    env_path.write_text("\n".join(lines + [key + "=" + value for key, value in replacements.items()]) + "\n")
    TLS_CONTEXT = ssl.create_default_context(cafile=str(certificate))
    command("systemctl", "restart", "hysteria2-panel.service")
    deadline = time.monotonic() + 30
    while True:
        try:
            if request(31998, "/readyz")[0] == 200:
                break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("HTTPS fixture did not become ready")
        time.sleep(1)
    users = [db.create_proxy_user("soak-{:04d}".format(i), device_limit=100,
                                  allow_udp_443=True) for i in range(1000)]
    now = int(time.time())
    nodes = []
    for index in range(10):
        node_id = uuid.uuid4().hex
        key = args.output / ("node-{}.key".format(index))
        command("openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key))
        public = subprocess.check_output(["openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"], timeout=10)
        with db._connect() as connection:
            connection.execute("""INSERT INTO nodes(node_id,name,expected_ip,observed_ip,status,
                public_key,hostname,platform,architecture,agent_version,created_at,registered_at,
                last_seen_at,verified_at,verified_by,last_heartbeat_at,last_heartbeat_ip,
                policy_state,policy_enabled_at,policy_enabled_by,data_plane_state)
                VALUES (?,?,'127.0.0.1','127.0.0.1','pending_verification',?,'fixture','linux',
                'arm64','0.39.40',?,?,?,?,'fixture',?,'127.0.0.1','protocol_ready',?,'fixture','dns_admitted')""",
                (node_id, "soak-node-{}".format(index), base64.b64encode(public).decode(),
                 now, now, now, now, now, now))
        nodes.append((node_id, key))
    stop = threading.Event()
    errors = []
    latencies = deque(maxlen=20000)
    lock = threading.Lock()
    children, handles, threads = [], [], []
    initial_pid = int(command("systemctl", "show", "--property=MainPID", "--value", "hysteria2-panel.service"))
    initial_restarts = command("systemctl", "show", "--property=NRestarts", "--value", "hysteria2-panel.service")
    started, started_at = time.monotonic(), time.time()
    report = {"candidate": args.candidate, "startedAt": started_at, "requestedSeconds": args.seconds,
              "users": 1000, "syntheticSignedNodes": 10, "hysteriaClients": 10, "tcpStreams": 100,
              "managementClients": 10, "authBurst": 64, "result": "running"}
    (args.output / "status.json").write_text(json.dumps(report, indent=2))
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    def guard(work):
        try:
            work()
        except Exception as error:
            with lock:
                errors.append(type(error).__name__ + ": " + str(error))
            stop.set()

    def start(work):
        thread = threading.Thread(target=guard, args=(work,), daemon=True)
        threads.append(thread)
        thread.start()

    def node_cycle(index, sequence):
        node_id, key = nodes[index]
        observed = int(time.time())
        payload = {"nodeId": node_id, "sentAt": observed, "nonce": secrets.token_urlsafe(32),
                   "cycleId": uuid.uuid4().hex,
                   "trafficBatches": [{"batchId": uuid.uuid4().hex, "observedAt": observed,
                                       "traffic": {users[100 + index]["name"]: {"tx": 10, "rx": 20}}}],
                   "onlineSnapshot": {"snapshotId": uuid.uuid4().hex, "sequence": sequence,
                                      "observedAt": observed, "trafficAckedAt": observed, "online": {}},
                   "commandPoll": {"requestId": uuid.uuid4().hex}}
        payload["signature"] = base64.b64encode(node_agent._openssl_sign(
            key, canonical_node_request("control-cycle", payload))).decode()
        status, body = request(31998, "/api/v1/node-control-cycles", payload)
        if status != 200:
            raise RuntimeError("signed node cycle HTTP {}".format(status))
        result = json.loads(body)
        if not result.get("traffic", [{}])[0].get("committed"):
            raise RuntimeError("node traffic was not committed")
        with db._connect() as connection:
            total = connection.execute("SELECT SUM(tx_bytes+rx_bytes) FROM origin_traffic_daily WHERE origin_id=?",
                                       ("node:" + node_id,)).fetchone()[0]
        if total != sequence * 30:
            raise RuntimeError("remote ledger mismatch")

    def reporter(index):
        sequence = 1
        while not stop.wait(10):
            sequence += 1
            node_cycle(index, sequence)

    def auth(index):
        before = time.monotonic()
        status, body = request(31996, "/auth", {"auth": users[200 + index]["token"], "tx": 0})
        elapsed = time.monotonic() - before
        if elapsed >= 10 or status != 200 or not json.loads(body).get("ok"):
            raise RuntimeError("authentication failed within normal capacity: HTTP {}".format(status))
        with lock:
            latencies.append(elapsed)

    def stream(port):
        with connect_stream(port) as sock:
            body = b"isolated-hysteria-acceptance\n" * 40
            while not stop.is_set():
                sock.sendall(body)
                if receive(sock, len(body)) != body:
                    raise RuntimeError("echo payload changed")
                stop.wait(1)

    admin = db.upsert_admin("soak-admin", secrets.token_urlsafe(32))
    session, _csrf = db.create_session(admin)
    cookie = "hy2panel_session=" + session
    session_created = time.monotonic()

    def management():
        while not stop.is_set():
            status, body = request(31998, "/", cookie=cookie)
            if status != 200 or b"soak-0000" not in body:
                raise RuntimeError("management read HTTP {}".format(status))
            stop.wait(5)

    first_hour, last_hour = [], deque(maxlen=120)
    echo = None
    try:
        command("ip", "address", "add", "198.18.0.2/32", "dev", "lo")
        echo = EchoServer(("198.18.0.2", 32080), Echo)
        threading.Thread(target=echo.serve_forever, daemon=True).start()
        for index in range(10):
            node_cycle(index, 1)
            start(lambda index=index: reporter(index))
        cert = Path(values["HY2PANEL_TLS_CERT"])
        pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
        for index in range(10):
            path = args.output / ("client-{}.json".format(index))
            path.write_text(json.dumps({"server": "127.0.0.1:{}".format(31999 if index % 2 == 0 else 443),
                                       "auth": users[index]["token"], "tls": {"insecure": True, "pinSHA256": pin},
                                       "socks5": {"listen": "127.0.0.1:{}".format(33000 + index)}}))
            handle = (args.output / ("client-{}.log".format(index))).open("wb")
            handles.append(handle)
            children.append(subprocess.Popen(["/opt/hysteria2-panel/bin/hysteria", "client", "-c", str(path)],
                                             stdout=handle, stderr=handle))
            deadline = time.monotonic() + 20
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", 33000 + index), timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("client did not start")
                    time.sleep(.2)
            for _ in range(10):
                start(lambda index=index: stream(33000 + index))
        for _ in range(10):
            start(management)
        # Start the observation clock only after the complete load is running.
        started, started_at = time.monotonic(), time.time()
        report["startedAt"] = started_at
        with ThreadPoolExecutor(max_workers=64) as executor, (args.output / "metrics.jsonl").open("a") as log:
            while not stop.is_set() and time.monotonic() - started < args.seconds:
                if time.monotonic() - session_created >= 6 * 3600:
                    session, _csrf = db.create_session(admin)
                    cookie = "hy2panel_session=" + session
                    # Let already-started reads finish with the previous cookie.
                    # Normal session expiry and create_session pruning stay intact.
                    session_created = time.monotonic()
                for future in [executor.submit(auth, index) for index in range(64)]:
                    future.result()
                pid = int(command("systemctl", "show", "--property=MainPID", "--value", "hysteria2-panel.service"))
                if pid != initial_pid or any(child.poll() is not None for child in children):
                    raise RuntimeError("unexpected service/client restart")
                proc = Path("/proc", str(pid))
                fields = dict(line.split(":", 1) for line in (proc / "status").read_text().splitlines() if ":" in line)
                elapsed = time.monotonic() - started
                metrics = {"elapsed": elapsed, "at": time.time(), "rssKiB": int(fields["VmRSS"].split()[0]),
                           "threads": int(fields["Threads"]), "fds": len(list((proc / "fd").iterdir())),
                           "cpuTicks": [int(v) for v in (proc / "stat").read_text().split()[13:15]],
                           "authP95Seconds": sorted(latencies)[int((len(latencies) - 1) * .95)]}
                queues = [int(row.split()[4].split(":")[1], 16)
                          for row in (proc / "net/tcp").read_text().splitlines()[1:]
                          if row.split()[3] == "0A"]
                metrics["maxListenQueue"] = max(queues, default=0)
                if 600 <= elapsed < 4200:
                    first_hour.append(metrics)
                last_hour.append(metrics)
                log.write(json.dumps(metrics) + "\n")
                log.flush()
                report["elapsedSeconds"] = elapsed
                report["latest"] = metrics
                (args.output / "status.json").write_text(json.dumps(report, indent=2))
                stop.wait(min(30, max(0, args.seconds - elapsed)))
        if errors:
            raise RuntimeError(errors[0])
        if time.monotonic() - started < args.seconds:
            raise RuntimeError("observation interrupted")
        if initial_restarts != command("systemctl", "show", "--property=NRestarts", "--value", "hysteria2-panel.service"):
            raise RuntimeError("service restart count changed")
        stop.set()
        for thread in threads:
            thread.join(timeout=10)
        clients = [panel.HysteriaStatsClient("http://127.0.0.1:{}".format(port),
                                            values["HY2PANEL_STATS_SECRET"]) for port in (31997, 31995)]
        expected_local = sum(sum(counters.values()) for client in clients
                             for counters in client.cumulative_traffic().values())
        settlement_deadline = time.monotonic() + 30
        while True:
            actual_local = sum(origin["tx_bytes"] + origin["rx_bytes"]
                               for origin in db.list_usage_origins(machine_totals=True)
                               if origin["kind"] == "local")
            if actual_local == expected_local:
                break
            if time.monotonic() >= settlement_deadline:
                raise RuntimeError("final local ledger differs from the two real cores")
            time.sleep(1)
        report["localLedgerBytes"] = actual_local
        if args.seconds >= 48 * 3600:
            initial = statistics.median(row["rssKiB"] for row in first_hour)
            final = statistics.median(row["rssKiB"] for row in last_hour)
            report["rssGrowthKiB"] = final - initial
            if final - initial > max(initial * .10, 16 * 1024):
                raise RuntimeError("RSS growth exceeds acceptance bound")
            for field in ("threads", "fds"):
                initial_resource = statistics.median(row[field] for row in first_hour)
                final_resource = statistics.median(row[field] for row in last_hour)
                report[field + "Growth"] = final_resource - initial_resource
                if final_resource > initial_resource + 4:
                    raise RuntimeError(field + " accumulated during the observation")
        report["result"] = "passed" if args.seconds >= 48 * 3600 else "short-run-only"
    except Exception as error:
        report["result"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=10)
        for child in children:
            child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for handle in handles:
            handle.close()
        if echo is not None:
            echo.shutdown()
            echo.server_close()
        report["endedAt"] = time.time()
        report["elapsedSeconds"] = time.monotonic() - started
        (args.output / "status.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
