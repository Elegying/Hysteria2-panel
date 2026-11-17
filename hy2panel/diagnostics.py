"""Bounded, evidence-based line diagnostics. Never change routing or subscriptions."""

import collections
import gzip
import hashlib
import ipaddress
import json
import logging
import math
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .version import PANEL_VERSION


def read_network_sample(root=Path("/")):
    """Read default-route NIC counters; no quota counters or clear-on-read stats."""
    try:
        interfaces = set()
        for line in (root / "proc/net/route").read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 4 and fields[1] == "00000000" and int(fields[3], 16) & 1:
                interfaces.add(fields[0])
        ipv6 = root / "proc/net/ipv6_route"
        if ipv6.exists():
            for line in ipv6.read_text().splitlines():
                fields = line.split()
                if (
                    len(fields) >= 10
                    and fields[0] == "0" * 32
                    and fields[1] == "00"
                    and int(fields[8], 16) & 1
                ):
                    interfaces.add(fields[-1])
        interfaces.discard("lo")
        if not interfaces or any(
            not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", name) for name in interfaces
        ):
            return None
        counters = {"rxBytes": 0, "txBytes": 0}
        for name in interfaces:
            for key, filename in (("rxBytes", "rx_bytes"), ("txBytes", "tx_bytes")):
                counters[key] += int(
                    (
                        root / "sys/class/net" / name / "statistics" / filename
                    ).read_text()
                )
        epoch = (root / "proc/sys/kernel/random/boot_id").read_text().strip()
        return dict(
            counters,
            epoch=epoch + ":" + ",".join(sorted(interfaces)),
            elapsedMs=int(float((root / "proc/uptime").read_text().split()[0]) * 1000),
        )
    except (OSError, ValueError, IndexError):
        return None


def valid_network_sample(sample):
    return (
        isinstance(sample, dict)
        and set(sample) == {"epoch", "elapsedMs", "rxBytes", "txBytes"}
        and isinstance(sample["epoch"], str)
        and re.fullmatch(r"[0-9a-f-]{36}:[A-Za-z0-9_.:,\-]{1,128}", sample["epoch"])
        is not None
        and all(
            type(sample[key]) is int and 0 <= sample[key] < 2**63
            for key in ("elapsedMs", "rxBytes", "txBytes")
        )
    )


class NetworkHistory:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.rows = {}

    def accept(self, origin_id, sample):
        if not valid_network_sample(sample):
            return
        now = self.clock()
        with self.lock:
            if origin_id not in self.rows and len(self.rows) >= 512:
                oldest = min(self.rows, key=lambda key: self.rows[key]["received"])
                del self.rows[oldest]
            row = self.rows.setdefault(
                origin_id,
                {
                    "last": None,
                    "received": now,
                    "points": collections.deque(maxlen=180),
                },
            )
            previous = row["last"]
            if (
                previous
                and sample["epoch"] == previous["epoch"]
                and sample["elapsedMs"] <= previous["elapsedMs"]
            ):
                return
            rx = tx = None
            if previous and sample["epoch"] == previous["epoch"]:
                elapsed = (sample["elapsedMs"] - previous["elapsedMs"]) / 1000
                if 0 < elapsed <= 20 and now - row["received"] <= 20:
                    drx = sample["rxBytes"] - previous["rxBytes"]
                    dtx = sample["txBytes"] - previous["txBytes"]
                    if drx >= 0 and dtx >= 0:
                        rx, tx = round(drx / elapsed, 2), round(dtx / elapsed, 2)
            row["last"] = dict(sample)
            row["received"] = now
            row["points"].append({"at": round(now, 3), "rx": rx, "tx": tx})

    def snapshot(self, origin_ids):
        now = self.clock()
        with self.lock:
            result = {}
            for origin_id in origin_ids:
                row = self.rows.get(origin_id)
                points = (
                    [dict(p) for p in row["points"] if now - p["at"] <= 900]
                    if row
                    else []
                )
                fresh = bool(row and 0 <= now - row["received"] <= 20)
                last = points[-1] if points else {}
                result[origin_id] = {
                    "fresh": fresh,
                    "observedAt": row["received"] if row else None,
                    "rx": last.get("rx") if fresh else None,
                    "tx": last.get("tx") if fresh else None,
                    "points": points,
                }
            return result


class DiagnosticGrants:
    """Process-local, target-scoped credentials. Never stored in subscriptions."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.grants = {}

    def issue(self, scope):
        token = secrets.token_urlsafe(36)
        with self.lock:
            self.grants = {k: v for k, v in self.grants.items() if v[1] > self.clock()}
            if len(self.grants) >= 4:
                raise RuntimeError("diagnostic credential capacity reached")
            self.grants[hashlib.sha256(token.encode()).digest()] = (
                scope,
                self.clock() + 90,
            )
        return token

    def allows(self, scope, token):
        if not isinstance(token, str):
            return False
        with self.lock:
            grant = self.grants.get(hashlib.sha256(token.encode()).digest())
            return bool(grant and grant[0] == scope and self.clock() < grant[1])

    def active(self, scope):
        with self.lock:
            return any(
                target == scope and self.clock() < deadline
                for target, deadline in self.grants.values()
            )

    def revoke(self, token):
        with self.lock:
            self.grants.pop(hashlib.sha256(token.encode()).digest(), None)


class ProbeUnavailable(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeUnavailable("检测服务重定向，未继续请求")


class GlobalpingClient:
    """Official free API. Fixed origin, no credentials, hard budget and backoff."""

    BASE = "https://api.globalping.io/v1/"
    OPERATORS = (
        ("电信", {4134, 4809, 4812, 4816}),
        ("联通", {4837, 9929, 17621, 17622}),
        ("移动", {9808, 56040, 56041, 56042, 56044, 56046, 56048}),
    )

    def __init__(self, clock=time.monotonic, sleeper=time.sleep):
        self.clock, self.sleep = clock, sleeper
        self.spent = collections.deque()
        self.backoff = 0
        self.inventory = None
        self.inventory_at = -1000
        self.opener = urllib.request.build_opener(_NoRedirect())
        self.cancelled = lambda: False

    def request(self, path, body=None, etag=None):
        if self.cancelled():
            raise ProbeUnavailable("检测已停止")
        if self.clock() < self.backoff:
            raise ProbeUnavailable("免费探测额度暂不可用，稍后重试")
        headers = {
            "User-Agent": "Hysteria2-panel/" + PANEL_VERSION,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
        if etag:
            headers["If-None-Match"] = etag
        data = None
        limit = 8 * 1024 * 1024 if path == "probes" else 1024 * 1024
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        try:
            with self.opener.open(
                urllib.request.Request(self.BASE + path, data=data, headers=headers),
                timeout=12,
            ) as response:
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ProbeUnavailable("检测服务响应过大")
                if response.headers.get("Content-Encoding") == "gzip":
                    # Bound decompression as well as the compressed response.
                    import io

                    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
                        raw = handle.read(limit + 1)
                    if len(raw) > limit:
                        raise ProbeUnavailable("检测服务响应过大")
                return json.loads(raw), response.headers.get("ETag")
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return None, etag
            if exc.code == 429:
                self.backoff = self.clock() + 3600
                raise ProbeUnavailable("免费探测额度已用尽，稍后自动重试") from None
            raise ProbeUnavailable("免费探测服务暂不可用") from None
        except (OSError, ValueError) as exc:
            raise ProbeUnavailable("免费探测服务暂不可用") from exc

    def locations(self):
        if self.inventory is None or self.clock() - self.inventory_at >= 300:
            data, _ = self.request("probes")
            if not isinstance(data, list):
                raise ProbeUnavailable("探针列表无效")
            self.inventory, self.inventory_at = data, self.clock()
        available = {
            p.get("location", {}).get("asn")
            for p in self.inventory
            if isinstance(p, dict) and p.get("location", {}).get("country") == "CN"
        }
        locations = []
        for name, asns in self.OPERATORS:
            matches = sorted(available & asns)
            if matches:
                locations.append((name, matches[0]))
        if not locations:
            raise ProbeUnavailable("暂无中国大陆运营商探针")
        return locations

    def tcp(self, address, port):
        if (
            not ipaddress.ip_address(address).is_global
            or type(port) is not int
            or not 1 <= port <= 65535
        ):
            raise ValueError("invalid diagnostic target")
        locations = self.locations()
        now = self.clock()
        while self.spent and now - self.spent[0] >= 3600:
            self.spent.popleft()
        if len(self.spent) + len(locations) > 180:
            raise ProbeUnavailable("面板本小时探测预算已用完")
        self.spent.extend([now] * len(locations))
        created, _ = self.request(
            "measurements",
            {
                "type": "ping",
                "target": address,
                "measurementOptions": {"protocol": "TCP", "port": port, "packets": 3},
                "locations": [
                    {"country": "CN", "asn": asn, "limit": 1} for _, asn in locations
                ],
            },
        )
        measurement_id = created.get("id", "") if isinstance(created, dict) else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", measurement_id):
            raise ProbeUnavailable("检测任务编号无效")
        document, etag = None, None
        for _ in range(12):
            self.sleep(1)
            value, etag = self.request("measurements/" + measurement_id, etag=etag)
            if value is not None:
                document = value
            if isinstance(document, dict) and document.get("status") != "in-progress":
                break
        if not isinstance(document, dict) or document.get("status") != "finished":
            raise ProbeUnavailable("国内探测未完成")
        if (
            document.get("target") != address
            or document.get("type") != "ping"
            or document.get("measurementOptions", {}).get("protocol") != "TCP"
            or document.get("measurementOptions", {}).get("port") != port
        ):
            raise ProbeUnavailable("检测目标不匹配")
        rows = []
        for name, asns in self.OPERATORS:
            matches = [
                r
                for r in document.get("results", [])
                if isinstance(r, dict)
                and r.get("probe", {}).get("country") == "CN"
                and r.get("probe", {}).get("asn") in asns
            ]
            row = {
                "operator": name,
                "state": "unknown",
                "city": "",
                "latencyMs": None,
                "loss": None,
                "port": port,
            }
            if matches:
                item = matches[0]
                result, probe = item.get("result", {}), item["probe"]
                stats = result.get("stats", {})
                rcv, total, loss = (
                    stats.get("rcv"),
                    stats.get("total"),
                    stats.get("loss"),
                )
                if (
                    result.get("status") == "finished"
                    and result.get("resolvedAddress") == address
                    and type(rcv) is int
                    and type(total) is int
                    and 0 <= rcv <= total
                    and total >= 3
                    and isinstance(loss, (int, float))
                    and not isinstance(loss, bool)
                    and math.isfinite(loss)
                    and 0 <= loss <= 100
                ):
                    row.update(state="pass" if rcv else "fail", loss=loss)
                    latency = stats.get("avg")
                    if (
                        isinstance(latency, (int, float))
                        and not isinstance(latency, bool)
                        and math.isfinite(latency)
                        and latency >= 0
                    ):
                        row["latencyMs"] = latency
                row["city"] = str(probe.get("city", ""))[:80]
            rows.append(row)
        return {"rows": rows, "measurementId": measurement_id}


class LineMonitor:
    """One asynchronous diagnostic job at a time; HTTP only reads cached results."""

    def __init__(self, application, client=None):
        self.app = application
        self.client = client or GlobalpingClient()
        self.history = NetworkHistory()
        self.grants = application.database.diagnostic_grants
        self.lock = threading.Lock()
        self.results = {}
        self.busy = None
        self.enabled = False
        self.last_requested = {}
        self.target_keys = {}
        self.stop_event = threading.Event()
        self.job = None
        self.client.cancelled = self.stop_event.is_set

    def targets(self):
        result = {}
        local_id = self.app.usage_manager.local_origin_id
        addresses = self.app.system_metrics.server_ips()
        ip = next((value for value in addresses if self._public(value)), None)
        if ip:
            hopping = self.app.port_hopping_controller.status()
            result[local_id] = {
                "ip": ip,
                "scope": "local",
                "host": self.app.public_host,
                "pin": self.app.pin_sha256,
                "port": self.app.hysteria_port,
                "hopping": bool(hopping.get("enabled")),
                "hopStart": 2000 if hopping.get("ports") == "2000-50000" else 20000,
            }
        for node in self.app.database.list_nodes():
            if (
                node["status"] != "pending_verification"
                or node.get("policy_state") != "protocol_ready"
                or node.get("lifecycle_state") != "active"
            ):
                continue
            ip = node.get("observed_ip") or node.get("expected_ip")
            if not self._public(ip):
                continue
            identity = (
                self.app.database.node_diagnostic_identity(node["node_id"])
                if node.get("tier") == "premium"
                else {"pin": self.app.pin_sha256, "sni": self.app.public_host}
            )
            if not identity:
                continue
            version = str(node.get("agent_version") or "").split(".")
            modern_hopping = (
                len(version) == 3
                and all(part.isdigit() for part in version)
                and tuple(map(int, version)) >= (0, 39, 53)
            )
            result["node:" + node["node_id"]] = {
                "ip": ip,
                "scope": node["node_id"],
                "host": node.get("subscription_host") or self.app.public_host,
                "pin": identity["pin"],
                "sni": identity["sni"],
                "port": int(node.get("listen_port") or 19999),
                "hopping": bool(node.get("port_hopping")),
                "hopStart": 2000 if modern_hopping else 20000,
            }
        return result

    @staticmethod
    def _public(value):
        try:
            return ipaddress.ip_address(value).is_global
        except (ValueError, TypeError):
            return False

    def request(self, origin_id):
        if (
            not self.enabled
            or self.stop_event.is_set()
            or getattr(self.app, "_maintenance_active", False)
        ):
            return False, "检测服务尚未启动"
        target = self.targets().get(origin_id)
        if not target:
            return False, "只检测当前启用的对接节点"
        now = time.time()
        with self.lock:
            if self.busy:
                return False, "已有线路正在检测，请稍后重试"
            if now - self.last_requested.get(origin_id, 0) < 60:
                return False, "每条线路至少间隔 60 秒检测"
            self.busy = origin_id
            self.last_requested[origin_id] = now
            self.target_keys[origin_id] = dict(target)
        self.job = threading.Thread(
            target=self._check,
            args=(origin_id, target),
            daemon=True,
            name="line-diagnostic",
        )
        try:
            self.job.start()
        except RuntimeError:
            with self.lock:
                self.busy = None
            return False, "检测服务繁忙，请稍后重试"
        return True, "检测已开始"

    def _check(self, origin_id, target):
        result = {
            "checkedAt": int(time.time()),
            "ip": target["ip"],
            "domestic": [],
            "proxy": [],
            "domesticError": "",
            "dns": "unknown",
            "tcpReference": [],
            "source": "面板本机自检（不经过国内网络）"
            if target["scope"] == "local"
            else "面板服务器（不代表国内网络）",
            "domesticUdp": "unverified",
            "expectedPorts": len(set([443, target["port"]])),
        }
        try:
            try:
                resolved = {
                    info[4][0]
                    for info in socket.getaddrinfo(
                        target["host"], 443, type=socket.SOCK_DGRAM
                    )
                }
                result["dns"] = "pass" if target["ip"] in resolved else "fail"
            except OSError:
                pass
            # Real TLS-pinned QUIC authentication and HTTPS egress. Credential
            # stays on this panel; public probe API receives only IP and TCP port.
            from .nodes import HysteriaCanaryRunner

            runner = HysteriaCanaryRunner(target.get("sni") or target["host"])
            ports = list(
                dict.fromkeys(
                    [443, target["port"]]
                    + (
                        [
                            target.get("hopStart", 2000)
                            + secrets.randbelow(50001 - target.get("hopStart", 2000))
                        ]
                        if target["hopping"] and target["scope"] != "local"
                        else []
                    )
                )
            )
            for port in ports:
                if self.stop_event.is_set() or getattr(
                    self.app, "_maintenance_active", False
                ):
                    raise ProbeUnavailable("维护期间暂停检测")
                token = self.grants.issue(target["scope"])
                try:
                    runner._check_entrypoint(
                        target["ip"],
                        port,
                        token,
                        target["pin"],
                        "https://www.cloudflare.com/cdn-cgi/trace",
                    )
                    state, reason = "pass", ""
                except Exception as exc:
                    state = "fail"
                    reason = (
                        "代理启动或握手失败"
                        if "become ready" in str(exc)
                        else "出口地址与节点不一致"
                        if "does not match" in str(exc)
                        else "代理出网未通过（含认证、DNS 与 HTTPS）"
                    )
                finally:
                    self.grants.revoke(token)
                result["proxy"].append({"port": port, "state": state, "reason": reason})
            if target["hopping"] and target["scope"] == "local":
                # Locally generated packets do not traverse PREROUTING. A
                # self-test cannot prove or disprove the inbound hop mapping.
                result["proxy"].append({
                    "port": "{}–50000".format(target.get("hopStart", 2000)),
                    "state": "unknown",
                    "reason": "端口跳跃需外部验证；本机自检不经过入站转发规则",
                })
            for port in dict.fromkeys([443, target["port"]]):
                try:
                    with socket.create_connection((target["ip"], port), timeout=3):
                        pass
                    reference = "pass"
                except OSError:
                    reference = "fail"
                result["tcpReference"].append({"port": port, "state": reference})
                try:
                    measured = self.client.tcp(target["ip"], port)
                    result["domestic"].append(measured)
                except ProbeUnavailable as exc:
                    result["domesticError"] = str(exc)
                    break
            result["checkedAt"] = int(time.time())
            with self.lock:
                previous = self.results.get(origin_id, {})
                failures = [
                    row
                    for group in result["domestic"]
                    for row in group["rows"]
                    if row["state"] == "fail"
                ]
                failure_keys = sorted(
                    {str(row["port"]) + ":" + row["operator"] for row in failures}
                )
                repeated = (
                    previous.get("ip") == target["ip"]
                    and result["checkedAt"] - previous.get("checkedAt", 0) < 1200
                    and bool(set(failure_keys) & set(previous.get("failureKeys", [])))
                )
                result["failureRounds"] = (
                    (previous.get("failureRounds", 0) + 1)
                    if repeated
                    else int(bool(failures))
                )
                result["failureKeys"] = failure_keys
                self.results[origin_id] = result
        except Exception:
            result["domesticError"] = "检测未完成，请稍后重试"
            with self.lock:
                self.results[origin_id] = result
        finally:
            with self.lock:
                self.busy = None

    def snapshot(self, origin_ids):
        now = time.time()
        with self.lock:
            results = {
                key: dict(
                    self.results[key],
                    stale=now - self.results[key]["checkedAt"] > 1200,
                    running=self.busy == key,
                )
                for key in origin_ids
                if key in self.results
            }
            if self.busy in origin_ids:
                results.setdefault(self.busy, {"running": True, "checkedAt": None})
        return {"network": self.history.snapshot(origin_ids), "checks": results}

    def run(self, stop_event):
        self.stop_event = stop_event
        self.client.cancelled = stop_event.is_set
        while not stop_event.is_set():
            try:
                local_id = self.app.usage_manager.local_origin_id
                self.history.accept(local_id, read_network_sample())
                targets = self.targets()
                with self.lock:
                    for origin_id, target in targets.items():
                        if (
                            origin_id in self.target_keys
                            and self.target_keys[origin_id] != target
                        ):
                            self.results.pop(origin_id, None)
                            self.last_requested.pop(origin_id, None)
                # Sampling is passive. Only an explicit administrator request
                # starts network diagnostics; opening the dashboard never does.
                with self.lock:
                    self.results = {
                        key: value
                        for key, value in self.results.items()
                        if key in targets
                    }
                    self.last_requested = {
                        key: value
                        for key, value in self.last_requested.items()
                        if key in targets
                    }
            except Exception:
                # Optional monitoring must not take auth/accounting offline.
                logging.getLogger(__name__).debug(
                    "line monitor sample unavailable", exc_info=True
                )
            stop_event.wait(5)
        job = self.job
        if job is not None:
            job.join(timeout=29)
