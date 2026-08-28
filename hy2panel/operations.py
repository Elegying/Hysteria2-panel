"""Fixed system operations, update status and host metrics."""

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess  # nosec B404 - fixed executables and argv only
import tempfile
import threading
import time
from pathlib import Path

from .version import PANEL_VERSION


LOGGER = logging.getLogger("hysteria2-panel")
EGRESS_STATE_VERSION = 1
_SYSTEMD_NOTIFICATION_ENVIRONMENT = (
    "NOTIFY_SOCKET",
    "WATCHDOG_PID",
    "WATCHDOG_USEC",
)


def _systemctl_environment():
    environment = os.environ.copy()
    for name in _SYSTEMD_NOTIFICATION_ENVIRONMENT:
        environment.pop(name, None)
    return environment


class EgressPolicyStateError(RuntimeError):
    """Raised when the effective egress policy cannot be proved consistent."""


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
            env=_systemctl_environment(),
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
            env=_systemctl_environment(),
        )
        if result.returncode != 0:
            raise RuntimeError("service control failed")
        return self.status()


def _read_managed_file(path, expected_uid, max_bytes=1024 * 1024):
    path = Path(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError("managed configuration could not be inspected") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != expected_uid
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or metadata.st_size <= 0
        or metadata.st_size > max_bytes
    ):
        raise RuntimeError("managed configuration metadata is invalid")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("managed configuration could not be opened") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise RuntimeError("managed configuration changed while opening")
        payload = bytearray()
        while len(payload) <= max_bytes:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if not payload or len(payload) > max_bytes:
            raise RuntimeError("managed configuration size is invalid")
        return bytes(payload), opened
    finally:
        os.close(descriptor)


def _atomic_replace_managed_file(path, payload, metadata):
    path = Path(path)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(path.parent),
            prefix=".{}-".format(path.name),
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fchmod(temporary.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fchown(temporary.fileno(), metadata.st_uid, metadata.st_gid)
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        directory = os.open(
            str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _atomic_write_file(path, payload, mode, uid, gid):
    path = Path(path)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(path.parent),
            prefix=".{}-".format(path.name),
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fchmod(temporary.fileno(), mode)
            os.fchown(temporary.fileno(), uid, gid)
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        _fsync_directory(path.parent)
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _fsync_directory(path):
    directory = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _durable_unlink(path):
    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def _sha256(payload):
    return hashlib.sha256(payload).hexdigest()


class EgressPolicyController:
    ENV_PATH = Path("/etc/hysteria2-panel/panel.env")
    CONFIG_PATHS = (
        Path("/etc/hysteria2-panel/hysteria.yaml"),
        Path("/etc/hysteria2-panel/hysteria-443.yaml"),
    )
    STATE_PATH = Path("/etc/hysteria2-panel/.egress-state.json")
    SERVICES = (
        "hysteria2-panel-server.service",
        "hysteria2-panel-server-443.service",
    )
    POLICIES = {"web", "full"}
    UNITS = {
        "web": "hysteria2-panel-egress-web.service",
        "full": "hysteria2-panel-egress-full.service",
    }

    def __init__(
        self,
        runner=subprocess.run,
        env_path=ENV_PATH,
        config_paths=CONFIG_PATHS,
        state_path=STATE_PATH,
        expected_uid=0,
    ):
        self.runner = runner
        self.env_path = Path(env_path)
        self.config_paths = tuple(Path(path) for path in config_paths)
        self.state_path = Path(state_path)
        self.expected_uid = expected_uid

    @staticmethod
    def _policy_from_bytes(payload):
        try:
            source = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("egress policy configuration is invalid") from exc
        matches = re.findall(
            r"^HY2PANEL_EGRESS_POLICY=(web|full)$", source, re.MULTILINE
        )
        if len(matches) != 1:
            raise RuntimeError("egress policy configuration is invalid")
        return matches[0]

    @staticmethod
    def _panel_port_from_bytes(payload):
        try:
            source = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("egress policy configuration is invalid") from exc
        matches = re.findall(
            r"^HY2PANEL_PANEL_PORT=([0-9]{1,5})$", source, re.MULTILINE
        )
        if len(matches) != 1 or not 1 <= int(matches[0]) <= 65535:
            raise RuntimeError("egress policy configuration is invalid")
        return int(matches[0])

    def _paths(self):
        paths = [self.config_paths[0]]
        if len(self.config_paths) > 1 and (
            self.config_paths[1].exists() or self.config_paths[1].is_symlink()
        ):
            paths.append(self.config_paths[1])
        return paths

    def _unit_state_is_valid(self, unit):
        result = self.runner(
            [
                "/bin/systemctl",
                "show",
                "--no-pager",
                "--property=LoadState",
                "--property=ActiveState",
                unit,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_systemctl_environment(),
        )
        if result.returncode != 0:
            raise RuntimeError("Hysteria service state could not be verified")
        values = {}
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in values:
                raise RuntimeError("Hysteria service state is invalid")
            values[key] = value
        if set(values) != {"LoadState", "ActiveState"}:
            raise RuntimeError("Hysteria service state is incomplete")
        return values["LoadState"] == "loaded" and values["ActiveState"] in {
            "active",
            "inactive",
            "failed",
        }

    def _switch_unit_completed(self, unit):
        result = self.runner(
            [
                "/bin/systemctl",
                "show",
                "--no-pager",
                "--property=LoadState",
                "--property=ActiveState",
                "--property=SubState",
                "--property=Result",
                "--property=ExecMainStatus",
                unit,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_systemctl_environment(),
        )
        if result.returncode != 0:
            return False
        values = {}
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in values:
                return False
            values[key] = value
        return values == {
            "LoadState": "loaded",
            "ActiveState": "inactive",
            "SubState": "dead",
            "Result": "success",
            "ExecMainStatus": "0",
        }

    def inspect(self):
        try:
            env_payload, _metadata = _read_managed_file(
                self.env_path, self.expected_uid, max_bytes=65536
            )
            configured = self._policy_from_bytes(env_payload)
            panel_port = self._panel_port_from_bytes(env_payload)
            paths = self._paths()
            payloads = {self.env_path: env_payload}
            config_policies = []
            for path in paths:
                payload, _metadata = _read_managed_file(path, self.expected_uid)
                payloads[path] = payload
                config_policies.append(
                    EgressPolicyManager._policy_from_config(payload, panel_port)
                )
            state_payload, state_metadata = _read_managed_file(
                self.state_path, self.expected_uid, max_bytes=65536
            )
            if stat.S_IMODE(state_metadata.st_mode) != 0o644:
                raise RuntimeError("egress policy state metadata is invalid")
            state = json.loads(state_payload.decode("utf-8"))
            expected_files = {str(path): _sha256(payload) for path, payload in payloads.items()}
            consistent = (
                all(policy == configured for policy in config_policies)
                and isinstance(state, dict)
                and state.get("version") == EGRESS_STATE_VERSION
                and state.get("policy") == configured
                and state.get("files") == expected_files
                and all(
                    self._unit_state_is_valid(unit)
                    for unit in self.SERVICES[: len(paths)]
                )
            )
            return {
                "state": configured if consistent else "inconsistent",
                "configured_policy": configured,
            }
        except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError):
            LOGGER.exception("egress policy status could not be verified")
            return {"state": "unknown", "configured_policy": None}

    def status(self):
        return self.inspect()["state"]

    def switch(self, policy):
        if policy not in self.POLICIES:
            raise ValueError("unsupported egress policy")
        before = self.inspect()
        try:
            result = self.runner(
                [
                    "/usr/bin/sudo",
                    "-n",
                    "/bin/systemctl",
                    "start",
                    self.UNITS[policy],
                ],
                capture_output=True,
                text=True,
                timeout=330,
                check=False,
                env=_systemctl_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            if (
                self._switch_unit_completed(self.UNITS[policy])
                and self.status() == policy
            ):
                return policy
            raise EgressPolicyStateError(
                "egress policy switch timed out; state is inconsistent"
            ) from exc
        after = self.status()
        if result.returncode != 0:
            if before["state"] in self.POLICIES and after == before["state"]:
                raise RuntimeError(
                    "egress policy switch failed; previous policy restored"
                )
            raise EgressPolicyStateError(
                "egress policy switch failed; state is inconsistent"
            )
        if after != policy:
            raise EgressPolicyStateError(
                "egress policy switch completed without a consistent state"
            )
        return policy


class EgressPolicyManager:
    ENV_PATH = EgressPolicyController.ENV_PATH
    CONFIG_PATHS = (
        Path("/etc/hysteria2-panel/hysteria.yaml"),
        Path("/etc/hysteria2-panel/hysteria-443.yaml"),
    )
    SERVER = "hysteria2-panel-server.service"
    SECONDARY_SERVER = "hysteria2-panel-server-443.service"
    STATE_PATH = EgressPolicyController.STATE_PATH
    TRANSACTION_PATH = Path("/etc/hysteria2-panel/.egress-transaction.json")
    COMMON_RULES = (
        "reject(0.0.0.0/8)",
        "reject(127.0.0.0/8)",
        "reject(10.0.0.0/8)",
        "reject(100.64.0.0/10)",
        "reject(169.254.0.0/16)",
        "reject(172.16.0.0/12)",
        "reject(192.168.0.0/16)",
        "reject(224.0.0.0/4)",
        "reject(240.0.0.0/4)",
        "reject(::/128)",
        "reject(::1/128)",
        "reject(fc00::/7)",
        "reject(fe80::/10)",
        "reject(ff00::/8)",
    )

    def __init__(
        self,
        runner=subprocess.run,
        env_path=ENV_PATH,
        config_paths=CONFIG_PATHS,
        state_path=STATE_PATH,
        transaction_path=TRANSACTION_PATH,
        expected_uid=0,
    ):
        self.runner = runner
        self.env_path = Path(env_path)
        self.config_paths = tuple(Path(path) for path in config_paths)
        self.state_path = Path(state_path)
        self.transaction_path = Path(transaction_path)
        self.expected_uid = expected_uid

    @staticmethod
    def _replace_policy(payload, policy):
        try:
            source = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("egress policy configuration is invalid") from exc
        pattern = re.compile(r"^HY2PANEL_EGRESS_POLICY=(?:web|full)$", re.MULTILINE)
        if len(pattern.findall(source)) != 1:
            raise RuntimeError("egress policy configuration is invalid")
        return pattern.sub("HY2PANEL_EGRESS_POLICY={}".format(policy), source).encode(
            "utf-8"
        )

    @classmethod
    def _acl_block(cls, policy, panel_port):
        if policy not in EgressPolicyController.POLICIES:
            raise ValueError("unsupported egress policy")
        try:
            panel_port = int(panel_port)
        except (TypeError, ValueError) as exc:
            raise ValueError("panel port is invalid") from exc
        if not 1 <= panel_port <= 65535:
            raise ValueError("panel port is invalid")
        rules = list(cls.COMMON_RULES)
        if policy == "web":
            rules.extend(
                (
                    "direct(all, tcp/22)",
                    "direct(all, tcp/{})".format(panel_port),
                    "direct(all, tcp/53)",
                    "direct(all, udp/53)",
                    "direct(all, tcp/80)",
                    "direct(all, tcp/443)",
                    "direct(all, udp/443)",
                    "direct(all, udp/123)",
                    "reject(all)",
                )
            )
        else:
            rules.append("direct(all)")
        return "acl:\n  inline:\n{}".format(
            "".join('    - "{}"\n'.format(rule) for rule in rules)
        )

    @classmethod
    def _replace_acl(cls, payload, policy, panel_port):
        try:
            source = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("Hysteria configuration is invalid") from exc
        acl_matches = list(re.finditer(r"^acl:\n", source, re.MULTILINE))
        masquerade_matches = list(
            re.finditer(r"^masquerade:\n", source, re.MULTILINE)
        )
        if (
            len(acl_matches) != 1
            or len(masquerade_matches) != 1
            or acl_matches[0].start() >= masquerade_matches[0].start()
        ):
            raise RuntimeError("Hysteria ACL layout is invalid")
        return (
            source[: acl_matches[0].start()]
            + cls._acl_block(policy, panel_port)
            + source[masquerade_matches[0].start() :]
        ).encode("utf-8")

    @classmethod
    def _policy_from_config(cls, payload, panel_port):
        matches = [
            policy
            for policy in EgressPolicyController.POLICIES
            if cls._replace_acl(payload, policy, panel_port) == payload
        ]
        return matches[0] if len(matches) == 1 else None

    def _server_is_active(self, unit):
        active = self.runner(
            ["/bin/systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_systemctl_environment(),
        )
        state = active.stdout.strip()
        if active.returncode == 0 and state == "active":
            return True
        if state in {"inactive", "failed"}:
            return False
        raise RuntimeError("Hysteria service state could not be verified")

    def _unit_states(self, has_secondary):
        units = [self.SERVER]
        if has_secondary:
            units.append(self.SECONDARY_SERVER)
        return {unit: self._server_is_active(unit) for unit in units}

    def _restart_and_verify(self, states):
        restart_unit = None
        if states.get(self.SERVER):
            restart_unit = self.SERVER
        elif states.get(self.SECONDARY_SERVER):
            restart_unit = self.SECONDARY_SERVER
        if restart_unit is not None:
            restart = self.runner(
                ["/bin/systemctl", "restart", restart_unit],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                env=_systemctl_environment(),
            )
            if restart.returncode != 0:
                raise RuntimeError("Hysteria service restart failed")
        for unit, expected_active in states.items():
            actual_active = self._server_is_active(unit)
            if not expected_active and actual_active:
                stopped = self.runner(
                    ["/bin/systemctl", "stop", unit],
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                    env=_systemctl_environment(),
                )
                if stopped.returncode != 0 or self._server_is_active(unit):
                    raise RuntimeError("Hysteria service state could not be restored")
                continue
            if actual_active != expected_active:
                raise RuntimeError("Hysteria service state changed unexpectedly")

    def _ownership_gid(self):
        return 0 if self.expected_uid == 0 else os.getegid()

    def _write_json(self, path, value, mode):
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        _atomic_write_file(
            path, payload, mode, self.expected_uid, self._ownership_gid()
        )

    def _write_state(self, policy, payloads):
        self._write_json(
            self.state_path,
            {
                "version": EGRESS_STATE_VERSION,
                "policy": policy,
                "files": {
                    str(path): _sha256(payload)
                    for path, payload in payloads.items()
                },
            },
            0o644,
        )

    def _state_matches(self, policy, hashes):
        try:
            payload, metadata = _read_managed_file(
                self.state_path, self.expected_uid, max_bytes=65536
            )
            if stat.S_IMODE(metadata.st_mode) != 0o644:
                return False
            state = json.loads(payload.decode("utf-8"))
            if state != {
                "version": EGRESS_STATE_VERSION,
                "policy": policy,
                "files": hashes,
            }:
                return False
            return all(
                _sha256(_read_managed_file(path, self.expected_uid)[0]) == digest
                for path, digest in hashes.items()
            )
        except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError):
            return False

    def _write_transaction(self, original_policy, target_policy, originals, replacements):
        self._write_json(
            self.transaction_path,
            {
                "version": EGRESS_STATE_VERSION,
                "originalPolicy": original_policy,
                "targetPolicy": target_policy,
                "paths": [str(path) for path in originals],
                "originalFiles": {
                    str(path): base64.b64encode(payload).decode("ascii")
                    for path, (payload, _metadata) in originals.items()
                },
                "targetFiles": {
                    str(path): _sha256(payload)
                    for path, (payload, _metadata) in replacements.items()
                },
            },
            0o600,
        )

    def _read_transaction(self):
        payload, metadata = _read_managed_file(
            self.transaction_path, self.expected_uid, max_bytes=4 * 1024 * 1024
        )
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise RuntimeError("egress policy transaction metadata is invalid")
        try:
            record = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("egress policy transaction is invalid") from exc
        if not isinstance(record, dict):
            raise RuntimeError("egress policy transaction fields are invalid")
        paths = [self.env_path]
        for path in self.config_paths:
            if str(path) in record.get("paths", []):
                paths.append(path)
        expected_paths = [str(path) for path in paths]
        if (
            set(record) != {
                "version",
                "originalPolicy",
                "targetPolicy",
                "paths",
                "originalFiles",
                "targetFiles",
            }
            or record["version"] != EGRESS_STATE_VERSION
            or record["originalPolicy"] not in EgressPolicyController.POLICIES
            or record["targetPolicy"] not in EgressPolicyController.POLICIES
            or record["paths"] != expected_paths
            or set(record["originalFiles"]) != set(expected_paths)
            or set(record["targetFiles"]) != set(expected_paths)
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", digest or "")
                for digest in record["targetFiles"].values()
            )
        ):
            raise RuntimeError("egress policy transaction fields are invalid")
        decoded = {}
        try:
            for path in expected_paths:
                value = base64.b64decode(record["originalFiles"][path], validate=True)
                if not value or len(value) > 1024 * 1024:
                    raise ValueError
                decoded[Path(path)] = value
        except (TypeError, ValueError) as exc:
            raise RuntimeError("egress policy transaction backup is invalid") from exc
        record["decodedOriginalFiles"] = decoded
        return record

    def recover(self):
        try:
            self.transaction_path.lstat()
        except FileNotFoundError:
            return None
        record = self._read_transaction()
        if self._state_matches(record["targetPolicy"], record["targetFiles"]):
            _durable_unlink(self.transaction_path)
            return "committed"
        restored = {}
        for path in (Path(value) for value in record["paths"]):
            _current, metadata = _read_managed_file(path, self.expected_uid)
            payload = record["decodedOriginalFiles"][path]
            _atomic_replace_managed_file(path, payload, metadata)
            restored[path] = payload
        self._write_state(record["originalPolicy"], restored)
        _durable_unlink(self.transaction_path)
        return "rolled-back"

    def record_current_state(self, policy, panel_port):
        if policy not in EgressPolicyController.POLICIES:
            raise ValueError("unsupported egress policy")
        env_payload, _metadata = _read_managed_file(
            self.env_path, self.expected_uid, max_bytes=65536
        )
        if EgressPolicyController._policy_from_bytes(env_payload) != policy:
            raise RuntimeError("egress policy environment is inconsistent")
        paths = [self.config_paths[0]]
        if len(self.config_paths) > 1 and (
            self.config_paths[1].exists() or self.config_paths[1].is_symlink()
        ):
            paths.append(self.config_paths[1])
        payloads = {self.env_path: env_payload}
        for path in paths:
            payload, _metadata = _read_managed_file(path, self.expected_uid)
            if self._policy_from_config(payload, panel_port) != policy:
                raise RuntimeError("Hysteria egress configuration is inconsistent")
            payloads[path] = payload
        self._unit_states(len(paths) > 1)
        self._write_state(policy, payloads)

    def apply(self, policy, panel_port):
        if policy not in EgressPolicyController.POLICIES:
            raise ValueError("unsupported egress policy")
        self.recover()
        env_payload, env_metadata = _read_managed_file(
            self.env_path, self.expected_uid, max_bytes=65536
        )
        paths = [self.config_paths[0]]
        if len(self.config_paths) > 1 and (
            self.config_paths[1].exists() or self.config_paths[1].is_symlink()
        ):
            paths.append(self.config_paths[1])
        originals = {self.env_path: (env_payload, env_metadata)}
        for path in paths:
            originals[path] = _read_managed_file(path, self.expected_uid)
        replacements = {
            path: (self._replace_acl(payload, policy, panel_port), metadata)
            for path, (payload, metadata) in originals.items()
            if path != self.env_path
        }
        replacements[self.env_path] = (
            self._replace_policy(env_payload, policy),
            env_metadata,
        )
        original_policy = EgressPolicyController._policy_from_bytes(env_payload)
        states = self._unit_states(len(paths) > 1)
        self._write_transaction(
            original_policy, policy, originals, replacements
        )
        try:
            for path in paths + [self.env_path]:
                payload, metadata = replacements[path]
                _atomic_replace_managed_file(path, payload, metadata)
            self._restart_and_verify(states)
            self._write_state(
                policy,
                {path: replacements[path][0] for path in paths + [self.env_path]},
            )
            _durable_unlink(self.transaction_path)
        except Exception as switch_error:
            rollback_error = None
            try:
                for path in paths + [self.env_path]:
                    payload, metadata = originals[path]
                    _atomic_replace_managed_file(path, payload, metadata)
                self._restart_and_verify(states)
                self._write_state(
                    original_policy,
                    {path: originals[path][0] for path in paths + [self.env_path]},
                )
                _durable_unlink(self.transaction_path)
            except Exception as exc:
                rollback_error = exc
            if rollback_error is not None:
                raise RuntimeError(
                    "egress policy switch and rollback failed"
                ) from rollback_error
            raise RuntimeError("egress policy switch failed; previous policy restored") from switch_error


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
            env=_systemctl_environment(),
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
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.status_path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ValueError("update status file is invalid") from exc
        try:
            file_status = os.fstat(descriptor)
            parent_status = os.lstat(self.status_path.parent)
            if (
                not stat.S_ISREG(file_status.st_mode)
                or file_status.st_nlink != 1
                or stat.S_IMODE(file_status.st_mode) != 0o600
                or not stat.S_ISDIR(parent_status.st_mode)
                or stat.S_IMODE(parent_status.st_mode) & 0o022
                or file_status.st_uid != parent_status.st_uid
                or not 0 < file_status.st_size <= 16384
            ):
                raise ValueError("update status file is invalid")
            raw = os.read(descriptor, 16385)
        finally:
            os.close(descriptor)
        if len(raw) != file_status.st_size:
            raise ValueError("update status file is invalid")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("update status file is invalid")
        return payload

    def _update_unit_allows_queue(self):
        result = self.runner(
            [
                "/bin/systemctl",
                "show",
                self.SERVICE,
                "--all",
                "--property=ActiveState",
                "--property=Job",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env=_systemctl_environment(),
        )
        if result.returncode != 0:
            raise RuntimeError("update service state could not be verified")
        states = {
            key: value
            for line in result.stdout.splitlines()
            for key, separator, value in (line.partition("="),)
            if separator
        }
        active_state = states.get("ActiveState")
        if not active_state or "Job" not in states:
            raise RuntimeError("update service state could not be verified")
        return active_state in {"inactive", "failed"} and states["Job"] in {"", "0"}

    def queue(self, target_version):
        target = self._version_label(target_version)
        if self._version_tuple(target) <= self._version_tuple(self.current_version):
            raise ValueError("update target must be newer than the current version")
        existing = self._read_status()
        if existing is not None and not self._update_unit_allows_queue():
            raise RuntimeError("an update target is already active")
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
            env=_systemctl_environment(),
        )
        if result.returncode != 0:
            record.update(
                state="failed",
                message="更新服务未能启动，请检查系统服务日志",
            )
            self._write_status(record)
            raise RuntimeError("update service could not be started")

    def pending_target(self):
        record = self._read_status()
        if not record or record.get("state") != "queued":
            raise RuntimeError("no queued update target is available")
        target = self._version_label(record.get("target"))
        if self._version_tuple(target) <= self._version_tuple(self.current_version):
            raise RuntimeError("queued update target is not newer than the current version")
        return target

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
            env=_systemctl_environment(),
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
            env=_systemctl_environment(),
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
