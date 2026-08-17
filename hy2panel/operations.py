"""Fixed system operations, update status and host metrics."""

import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404 - fixed executables and argv only
import tempfile
import threading
import time
from pathlib import Path

from .version import PANEL_VERSION


LOGGER = logging.getLogger("hysteria2-panel")


class ServiceController:
    SERVICE = "hysteria2-panel-server.service"
    ACTIONS = {"start", "stop", "restart"}

    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def status(self):
        result = self.runner(
            ["/bin/systemctl", "is-active", self.SERVICE],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        value = result.stdout.strip()
        return value if value else "unknown"

    def action(self, action):
        if action not in self.ACTIONS:
            raise ValueError("unsupported service action")
        result = self.runner(
            ["/usr/bin/sudo", "-n", "/bin/systemctl", action, self.SERVICE],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("service control failed")
        return self.status()


class RestoreController:
    SERVICE = "hysteria2-panel-restore.service"

    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def queue(self):
        result = self.runner(
            [
                "/usr/bin/sudo",
                "-n",
                "/bin/systemctl",
                "--no-block",
                "start",
                self.SERVICE,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("restore service could not be started")


class UpdateController:
    SERVICE = "hysteria2-panel-update.service"
    STATUS_PATH = Path("/var/lib/hysteria2-panel/update-status.json")
    QUEUE_GRACE_SECONDS = 30

    def __init__(
        self,
        runner=subprocess.run,
        status_path=STATUS_PATH,
        current_version=PANEL_VERSION,
        clock=time.time,
    ):
        self.runner = runner
        self.status_path = Path(status_path)
        self.current_version = str(current_version)
        self.clock = clock

    @staticmethod
    def _version_tuple(value):
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value))
        if not match:
            raise ValueError("update version is invalid")
        return tuple(int(part) for part in match.groups())

    @staticmethod
    def _version_label(value):
        return "v{}".format(str(value).lstrip("v"))

    def _write_status(self, payload):
        self.status_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.status_path.parent),
                prefix=".update-status-",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                json.dump(payload, temporary, ensure_ascii=False, sort_keys=True)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.status_path)
        finally:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def _read_status(self):
        try:
            with self.status_path.open("rb") as source:
                raw = source.read(16385)
        except FileNotFoundError:
            return None
        if not raw or len(raw) > 16384:
            raise ValueError("update status file is invalid")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("update status file is invalid")
        return payload

    def queue(self, target_version):
        target = self._version_label(target_version)
        if self._version_tuple(target) <= self._version_tuple(self.current_version):
            raise ValueError("update target must be newer than the current version")
        record = {
            "state": "queued",
            "target": target,
            "queued_at": int(self.clock()),
            "message": "更新任务已排队",
        }
        self._write_status(record)
        result = self.runner(
            [
                "/usr/bin/sudo",
                "-n",
                "/bin/systemctl",
                "--no-block",
                "start",
                self.SERVICE,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            record.update(
                state="failed",
                message="更新服务未能启动，请检查系统服务日志",
            )
            self._write_status(record)
            raise RuntimeError("update service could not be started")

    def status(self):
        current = self._version_label(self.current_version)
        try:
            record = self._read_status()
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            LOGGER.exception("update status could not be read")
            return {
                "state": "failed",
                "target": None,
                "current": current,
                "message": "更新状态文件损坏或不可读",
            }
        if not record:
            return {
                "state": "idle",
                "target": None,
                "current": current,
                "message": "尚未启动更新",
            }
        target = record.get("target")
        try:
            target_tuple = self._version_tuple(target)
        except ValueError:
            return {
                "state": "failed",
                "target": None,
                "current": current,
                "message": "更新目标版本无效",
            }
        result = {
            "state": str(record.get("state", "queued")),
            "target": self._version_label(target),
            "current": current,
            "message": str(record.get("message", "更新任务已排队")),
        }
        if result["state"] == "failed":
            return result
        unit = self.runner(
            [
                "/bin/systemctl",
                "show",
                self.SERVICE,
                "--property=ActiveState",
                "--property=SubState",
                "--property=Result",
                "--property=ExecMainStatus",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if unit.returncode != 0:
            result.update(state="failed", message="无法读取更新服务状态")
            return result
        properties = {}
        for line in unit.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                properties[key] = value
        if properties.get("ActiveState") in {"activating", "active", "reloading"}:
            result.update(state="running", message="正在安装 {}".format(result["target"]))
            return result
        service_result = properties.get("Result", "")
        main_status = properties.get("ExecMainStatus", "0")
        if service_result not in {"", "success"} or main_status not in {"", "0"}:
            result.update(state="failed", message="更新任务执行失败，请检查更新服务日志")
            return result
        if self._version_tuple(current) >= target_tuple:
            result.update(state="success", message="更新已完成，当前版本为 {}".format(current))
            return result
        try:
            elapsed = max(0, int(self.clock()) - int(record.get("queued_at", 0)))
        except (TypeError, ValueError):
            elapsed = self.QUEUE_GRACE_SECONDS + 1
        if elapsed <= self.QUEUE_GRACE_SECONDS:
            result.update(state="queued", message="更新任务已排队，正在等待执行")
            return result
        result.update(state="failed", message="更新任务已经结束，但面板版本未改变")
        return result


class RebootController:
    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def queue(self):
        result = self.runner(
            ["/usr/bin/sudo", "-n", "/bin/systemctl", "--no-block", "reboot"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("server reboot could not be started")


class SystemMetrics:
    def __init__(
        self,
        proc_root=Path("/proc"),
        disk_usage=shutil.disk_usage,
        cpu_count=os.cpu_count,
        loadavg=os.getloadavg,
    ):
        self.proc_root = Path(proc_root)
        self.disk_usage = disk_usage
        self.cpu_count = cpu_count
        self.loadavg = loadavg
        self.previous_cpu = None
        self.lock = threading.Lock()

    def _cpu_sample(self):
        parts = (self.proc_root / "stat").read_text().splitlines()[0].split()[1:]
        values = [int(value) for value in parts]
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return total, idle

    def _read_optional(self, relative_path):
        try:
            return (self.proc_root / relative_path).read_text().strip() or "不可用"
        except (OSError, UnicodeError):
            return "不可用"

    @staticmethod
    def _uptime_label(seconds):
        days, remainder = divmod(max(0, int(seconds)), 86400)
        hours = remainder // 3600
        if days:
            return "{}天 {}小时".format(days, hours)
        minutes = (remainder % 3600) // 60
        return "{}小时 {}分钟".format(hours, minutes)

    def snapshot(self):
        with self.lock:
            current_cpu = self._cpu_sample()
            if self.previous_cpu is None:
                cpu_percent = min(
                    100.0,
                    max(0.0, self.loadavg()[0] * 100.0 / max(1, self.cpu_count() or 1)),
                )
            else:
                total_delta = current_cpu[0] - self.previous_cpu[0]
                idle_delta = current_cpu[1] - self.previous_cpu[1]
                cpu_percent = (
                    max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta))
                    if total_delta > 0
                    else 0.0
                )
            self.previous_cpu = current_cpu

        memory = {}
        for line in (self.proc_root / "meminfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in {"MemTotal", "MemAvailable"}:
                memory[key] = int(value.strip().split()[0]) * 1024
        memory_total = memory.get("MemTotal", 0)
        memory_used = max(0, memory_total - memory.get("MemAvailable", 0))
        disk = self.disk_usage("/")
        uptime_seconds = float((self.proc_root / "uptime").read_text().split()[0])
        return {
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(100.0 * memory_used / memory_total, 1) if memory_total else 0.0,
            "memory_used": memory_used,
            "memory_total": memory_total,
            "disk_percent": round(100.0 * disk.used / disk.total, 1) if disk.total else 0.0,
            "disk_used": disk.used,
            "disk_total": disk.total,
            "uptime": self._uptime_label(uptime_seconds),
            "tcp_congestion_control": self._read_optional(
                "sys/net/ipv4/tcp_congestion_control"
            ),
            "default_qdisc": self._read_optional("sys/net/core/default_qdisc"),
        }
