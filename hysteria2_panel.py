#!/usr/bin/env python3
"""Dependency-free Hysteria 2 multi-user panel."""

import argparse
import base64
import getpass
import hashlib
import hmac
import html
import http.cookies
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
PBKDF2_ITERATIONS = 600000
NAME_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,64}$")
LOGGER = logging.getLogger("hysteria2-panel")
DEFAULT_DEVICE_LIMIT = 3
DEFAULT_TRAFFIC_LIMIT_BYTES = 250 * 1024**3
MAX_DEVICE_LIMIT = 100
MAX_TRAFFIC_LIMIT_BYTES = 1024 * 1024**4
PANEL_VERSION = "0.4.0"

PAGE_STYLE = """
:root{--bg:#06111f;--surface:#0b1a2c;--surface-2:#132438;--text:#f3f7ff;--muted:#9aaac0;--line:#22364b;--accent:#5f91f7;--teal:#25b99a;--success:#4bc493;--warning:#f5b54b;--danger:#ff6675}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
main{width:min(1500px,calc(100% - 40px));margin:28px auto 48px}.topbar{display:flex;align-items:center;gap:14px;background:#102846;border:1px solid #284867;border-radius:22px;padding:24px 28px;margin-bottom:20px}.brand{min-width:max-content}.eyebrow{display:inline-block;border:1px solid #405b7c;border-radius:999px;padding:7px 13px;color:#c8d7ef;font-size:12px;letter-spacing:.12em}.topbar h1{font-size:32px;margin:0 6px}.topbar-spacer{flex:1}.pill{border:1px solid #3a526b;border-radius:999px;padding:9px 14px;color:var(--muted);white-space:nowrap}.pill strong{color:var(--text);margin-left:6px}
h1,h2,h3,p{margin-top:0}h2{font-size:20px;margin-bottom:4px}h3{font-size:16px}.muted{color:var(--muted)}.ok{color:var(--success)}.bad{color:var(--danger)}.warning{color:var(--warning)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:20px}.metric,.card{background:var(--surface);border:1px solid var(--line);border-radius:18px}.metric{padding:22px;border-top:3px solid var(--teal)}.metric strong{display:block;font-size:28px;margin:12px 0 4px}.metric span{color:var(--muted)}
.operations{display:grid;grid-template-columns:1.1fr 1fr;gap:18px;margin-bottom:20px}.card{padding:24px;margin-bottom:18px}.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:18px}.service-badge{border-radius:999px;padding:8px 13px;background:#123833;color:var(--success);font-weight:700;white-space:nowrap}.service-badge.off{background:#3a2028;color:#ff9aa4}
.button-row,.actions{display:flex;flex-wrap:wrap;gap:9px}button,.button{display:inline-block;border:1px solid transparent;border-radius:10px;background:var(--accent);color:#fff;padding:10px 15px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer}button:hover,.button:hover{filter:brightness(1.08)}button.secondary,.button.secondary{background:#1b2c40;border-color:#34495f}button.success{background:var(--success);color:#082016}button.warning{background:var(--warning);color:#251a05}button.danger{background:var(--danger)}button.ghost{background:transparent;border-color:#3a526b;color:#dce8f8}form.inline{display:inline}
.resource-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.resource,.detail{background:var(--surface-2);border:1px solid #283b50;border-radius:14px;padding:18px}.resource strong,.detail strong{display:block;font-size:22px;margin-top:8px}.service-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:18px}.version-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px}.notice{padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#10233a;color:#c7d6ea}
.rank-list{display:grid;gap:10px}.rank-row{display:grid;grid-template-columns:38px minmax(0,1fr) auto;align-items:center;gap:12px;padding:12px 14px;background:var(--surface-2);border:1px solid #283b50;border-radius:12px}.rank-number{color:var(--accent);font-weight:800}.rank-name{font-weight:700}.rank-traffic{color:var(--muted)}
.create-grid{display:grid;grid-template-columns:2fr 1fr 1fr auto;align-items:end;gap:12px;margin-bottom:22px}label{display:block;font-weight:650;margin-bottom:6px}input,textarea{width:100%;padding:11px 13px;border:1px solid #3a4d63;border-radius:9px;background:#101f31;color:var(--text);font:inherit}input:focus,textarea:focus,button:focus-visible,.button:focus-visible{outline:3px solid rgba(95,145,247,.38);outline-offset:2px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:1050px}th,td{padding:13px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}th{color:var(--muted);font-size:13px;white-space:nowrap}.status{font-weight:750}.enabled{color:var(--success)}.disabled{color:var(--danger)}progress{width:150px;height:10px;accent-color:var(--accent)}.traffic-cell{min-width:190px}.traffic-label{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--muted);margin-top:4px}.actions{min-width:360px}.inline-note{font-size:12px;color:var(--muted)}
.login{width:min(430px,100%);margin:12vh auto}.copy-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px;margin-bottom:16px}.error{color:var(--danger)}code{word-break:break-all}
@media(max-width:1050px){.topbar{flex-wrap:wrap}.topbar-spacer{display:none}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.operations{grid-template-columns:1fr}.create-grid{grid-template-columns:1fr 1fr}.create-grid .wide{grid-column:1/-1}}
@media(max-width:640px){main{width:min(100% - 20px,1500px);margin:12px auto 28px}.topbar{padding:18px;border-radius:16px;align-items:flex-start}.topbar h1{font-size:24px;width:100%;order:-1}.brand{display:none}.pill{font-size:12px}.metrics{grid-template-columns:1fr 1fr;gap:9px}.metric{padding:15px}.metric strong{font-size:20px}.card{padding:17px;border-radius:14px}.resource-grid,.service-details,.create-grid{grid-template-columns:1fr}.section-head{flex-direction:column}.copy-grid{grid-template-columns:1fr}.copy-grid button{width:100%}}
"""

PAGE_SCRIPT = """
document.addEventListener('click', async function(event) {
  const button = event.target.closest('[data-copy-target]');
  if (!button) return;
  const target = document.getElementById(button.dataset.copyTarget);
  if (!target) return;
  let copied = false;
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(target.value); copied = true; } catch (_) {}
  }
  if (!copied) {
    target.focus(); target.select(); copied = document.execCommand('copy');
  }
  button.textContent = copied ? '已复制' : '复制失败，请手动选择';
});
document.addEventListener('submit', function(event) {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
"""


class ConflictError(Exception):
    """Raised when an administrator submits a stale user mutation."""


def hash_password(password):
    if not isinstance(password, str) or len(password) < 8 or len(password) > 1024:
        raise ValueError("password must contain 8 to 1024 characters")
    salt = secrets.token_bytes(16)
    if hasattr(hashlib, "scrypt"):
        derived = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
        )
        return "scrypt${}${}${}${}${}".format(
            SCRYPT_N, SCRYPT_R, SCRYPT_P, salt.hex(), derived.hex()
        )
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
    )
    return "pbkdf2_sha256${}${}${}".format(PBKDF2_ITERATIONS, salt.hex(), derived.hex())


def verify_password(password, encoded):
    try:
        parts = encoded.split("$")
        algorithm = parts[0]
        if algorithm == "scrypt" and len(parts) == 6 and hasattr(hashlib, "scrypt"):
            _, n, r, p, salt_hex, expected_hex = parts
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(bytes.fromhex(expected_hex)),
            )
        elif algorithm == "pbkdf2_sha256" and len(parts) == 4:
            _, iterations, salt_hex, expected_hex = parts
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations),
                dklen=len(bytes.fromhex(expected_hex)),
            )
        else:
            return False
        return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
    except (AttributeError, TypeError, ValueError):
        return False


def _validate_name(name):
    if not isinstance(name, str):
        raise ValueError("name must be text")
    normalized = name.strip()
    if not NAME_PATTERN.fullmatch(normalized):
        raise ValueError("name must contain 1 to 64 printable characters")
    return normalized


def _validate_token(token):
    if not isinstance(token, str) or not 8 <= len(token) <= 512:
        raise ValueError("token must contain 8 to 512 characters")
    return token


class Database:
    def __init__(self, path, hmac_key):
        self.path = Path(path)
        if not isinstance(hmac_key, bytes) or len(hmac_key) < 32:
            raise ValueError("hmac key must contain at least 32 bytes")
        self.hmac_key = hmac_key

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proxy_users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    token_fingerprint TEXT NOT NULL UNIQUE,
                    token_seed BLOB,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                    generation INTEGER NOT NULL DEFAULT 0,
                    device_limit INTEGER NOT NULL DEFAULT 3 CHECK (device_limit BETWEEN 1 AND 100),
                    traffic_limit_bytes INTEGER NOT NULL DEFAULT 268435456000 CHECK (traffic_limit_bytes > 0),
                    tx_bytes INTEGER NOT NULL DEFAULT 0 CHECK (tx_bytes >= 0),
                    rx_bytes INTEGER NOT NULL DEFAULT 0 CHECK (rx_bytes >= 0),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    remote_ip TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(proxy_users)")
            }
            if "generation" not in columns:
                connection.execute(
                    "ALTER TABLE proxy_users ADD COLUMN generation INTEGER NOT NULL DEFAULT 0"
                )
            migrations = {
                "token_seed": "ALTER TABLE proxy_users ADD COLUMN token_seed BLOB",
                "device_limit": "ALTER TABLE proxy_users ADD COLUMN device_limit INTEGER NOT NULL DEFAULT 3",
                "traffic_limit_bytes": "ALTER TABLE proxy_users ADD COLUMN traffic_limit_bytes INTEGER NOT NULL DEFAULT 268435456000",
                "tx_bytes": "ALTER TABLE proxy_users ADD COLUMN tx_bytes INTEGER NOT NULL DEFAULT 0",
                "rx_bytes": "ALTER TABLE proxy_users ADD COLUMN rx_bytes INTEGER NOT NULL DEFAULT 0",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(statement)

    def _fingerprint(self, token):
        return hmac.new(self.hmac_key, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _token_from_seed(self, seed):
        digest = hmac.new(self.hmac_key, b"proxy-token\0" + seed, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def upsert_admin(self, username, password):
        username = _validate_name(username)
        password_hash = hash_password(password)
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM admins WHERE username = ?", (username,)
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE admins SET password_hash = ?, updated_at = ? WHERE id = ?",
                    (password_hash, now, row["id"]),
                )
                return row["id"]
            cursor = connection.execute(
                "INSERT INTO admins(username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, now, now),
            )
            return cursor.lastrowid

    def has_admin(self):
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM admins LIMIT 1").fetchone() is not None

    def verify_admin(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, password_hash FROM admins WHERE username = ?", (username,)
            ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return row["id"]
        return None

    def create_session(self, admin_id, ttl_seconds=43200):
        raw_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                "INSERT INTO sessions(token_hash, admin_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (hashlib.sha256(raw_token.encode()).hexdigest(), admin_id, csrf_token, now + ttl_seconds, now),
            )
        return raw_token, csrf_token

    def get_session(self, raw_token):
        if not raw_token:
            return None
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT sessions.admin_id, sessions.csrf_token, admins.username
                FROM sessions JOIN admins ON admins.id = sessions.admin_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
        return dict(row) if row else None

    def revoke_session(self, raw_token):
        if raw_token:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?",
                    (hashlib.sha256(raw_token.encode()).hexdigest(),),
                )

    def create_proxy_user(
        self,
        name,
        token=None,
        device_limit=DEFAULT_DEVICE_LIMIT,
        traffic_limit_bytes=DEFAULT_TRAFFIC_LIMIT_BYTES,
    ):
        name = _validate_name(name)
        device_limit = int(device_limit)
        traffic_limit_bytes = int(traffic_limit_bytes)
        if not 1 <= device_limit <= MAX_DEVICE_LIMIT:
            raise ValueError("device limit must be between 1 and 100")
        if not 1 <= traffic_limit_bytes <= MAX_TRAFFIC_LIMIT_BYTES:
            raise ValueError("traffic limit is out of range")
        token_seed = None
        if token is None:
            token_seed = secrets.token_bytes(32)
            token = self._token_from_seed(token_seed)
        token = _validate_token(token)
        now = int(time.time())
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """INSERT INTO proxy_users(
                    name, token_fingerprint, token_seed, enabled, device_limit,
                    traffic_limit_bytes, tx_bytes, rx_bytes, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?, 0, 0, ?, ?)""",
                    (
                        name,
                        self._fingerprint(token),
                        token_seed,
                        device_limit,
                        traffic_limit_bytes,
                        now,
                        now,
                    ),
                )
                return {"id": cursor.lastrowid, "name": name, "token": token}
        except sqlite3.IntegrityError as exc:
            raise ValueError("user name or token already exists") from exc

    def authenticate_token(self, token):
        if not isinstance(token, str) or not 1 <= len(token) <= 512:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT name FROM proxy_users WHERE token_fingerprint = ? AND enabled = 1",
                (self._fingerprint(token),),
            ).fetchone()
        return row["name"] if row else None

    def _get_proxy_user(self, user_id, connection):
        row = connection.execute(
            """SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
            tx_bytes, rx_bytes, created_at, updated_at
            FROM proxy_users WHERE id = ?""",
            (int(user_id),),
        ).fetchone()
        if not row:
            raise KeyError("proxy user not found")
        return row

    def get_proxy_user(self, user_id):
        with self._connect() as connection:
            return dict(self._get_proxy_user(user_id, connection))

    def get_proxy_user_by_name(self, name):
        with self._connect() as connection:
            row = connection.execute(
                """SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
                tx_bytes, rx_bytes, created_at, updated_at
                FROM proxy_users WHERE name = ? COLLATE NOCASE""",
                (name,),
            ).fetchone()
        return dict(row) if row else None

    def recover_proxy_token(self, user_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT token_seed FROM proxy_users WHERE id = ?", (int(user_id),)
            ).fetchone()
        if not row:
            raise KeyError("proxy user not found")
        seed = row["token_seed"]
        return self._token_from_seed(bytes(seed)) if seed is not None else None

    def set_proxy_user_enabled(self, user_id, enabled, expected_generation=None):
        now = int(time.time())
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            generation = row["generation"] if expected_generation is None else int(expected_generation)
            if generation != row["generation"]:
                raise ConflictError("proxy user changed; refresh and try again")
            cursor = connection.execute(
                "UPDATE proxy_users SET enabled = ?, generation = generation + 1, updated_at = ? WHERE id = ? AND generation = ?",
                (1 if enabled else 0, now, row["id"], generation),
            )
            if cursor.rowcount != 1:
                raise ConflictError("proxy user changed; refresh and try again")
            return dict(row)

    def rotate_proxy_token(self, user_id, token=None, expected_generation=None):
        token_seed = None
        if token is None:
            token_seed = secrets.token_bytes(32)
            token = self._token_from_seed(token_seed)
        token = _validate_token(token)
        now = int(time.time())
        try:
            with self._connect() as connection:
                row = self._get_proxy_user(user_id, connection)
                generation = row["generation"] if expected_generation is None else int(expected_generation)
                if generation != row["generation"]:
                    raise ConflictError("proxy user changed; refresh and try again")
                cursor = connection.execute(
                    """UPDATE proxy_users
                    SET token_fingerprint = ?, token_seed = ?, generation = generation + 1, updated_at = ?
                    WHERE id = ? AND generation = ?""",
                    (self._fingerprint(token), token_seed, now, row["id"], generation),
                )
                if cursor.rowcount != 1:
                    raise ConflictError("proxy user changed; refresh and try again")
                return {"id": row["id"], "name": row["name"], "token": token}
        except sqlite3.IntegrityError as exc:
            raise ValueError("token already exists") from exc

    def delete_proxy_user(self, user_id, expected_generation=None):
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            generation = row["generation"] if expected_generation is None else int(expected_generation)
            if generation != row["generation"]:
                raise ConflictError("proxy user changed; refresh and try again")
            cursor = connection.execute(
                "DELETE FROM proxy_users WHERE id = ? AND generation = ?",
                (row["id"], generation),
            )
            if cursor.rowcount != 1:
                raise ConflictError("proxy user changed; refresh and try again")
            return dict(row)

    def list_proxy_users(self, limit=50, offset=0):
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM proxy_users").fetchone()[0]
            rows = connection.execute(
                """
                SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
                tx_bytes, rx_bytes, created_at, updated_at
                FROM proxy_users ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return {"users": [dict(row) for row in rows], "total": total}

    def list_proxy_user_names(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM proxy_users ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [row["name"] for row in rows]

    def list_proxy_users_for_usage(self):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
                tx_bytes, rx_bytes, created_at, updated_at
                FROM proxy_users ORDER BY name COLLATE NOCASE"""
            ).fetchall()
        return [dict(row) for row in rows]

    def add_traffic(self, traffic_by_user):
        if not isinstance(traffic_by_user, dict):
            raise ValueError("traffic must be a mapping")
        now = int(time.time())
        with self._connect() as connection:
            for name, traffic in traffic_by_user.items():
                if not isinstance(name, str) or not isinstance(traffic, dict):
                    raise ValueError("traffic entry is invalid")
                tx = traffic.get("tx", 0)
                rx = traffic.get("rx", 0)
                if not isinstance(tx, int) or not isinstance(rx, int) or tx < 0 or rx < 0:
                    raise ValueError("traffic counters must be non-negative integers")
                connection.execute(
                    """UPDATE proxy_users SET tx_bytes = tx_bytes + ?, rx_bytes = rx_bytes + ?,
                    updated_at = ? WHERE name = ? COLLATE NOCASE""",
                    (tx, rx, now, name),
                )

    def reset_proxy_user_traffic(self, user_id, expected_generation=None):
        now = int(time.time())
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            generation = row["generation"] if expected_generation is None else int(expected_generation)
            if generation != row["generation"]:
                raise ConflictError("proxy user changed; refresh and try again")
            cursor = connection.execute(
                """UPDATE proxy_users SET tx_bytes = 0, rx_bytes = 0,
                generation = generation + 1, updated_at = ?
                WHERE id = ? AND generation = ?""",
                (now, row["id"], generation),
            )
            if cursor.rowcount != 1:
                raise ConflictError("proxy user changed; refresh and try again")

    def reset_all_traffic(self):
        with self._connect() as connection:
            connection.execute(
                """UPDATE proxy_users SET tx_bytes = 0, rx_bytes = 0,
                generation = generation + 1, updated_at = ?""",
                (int(time.time()),),
            )

    def audit(self, actor, action, target, remote_ip):
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log(created_at, actor, action, target, remote_ip) VALUES (?, ?, ?, ?, ?)",
                (int(time.time()), actor, action, target, remote_ip),
            )


def handle_auth_payload(database, raw_body, usage_manager=None):
    if len(raw_body) > 4096:
        return 413, {"error": {"code": "REQUEST_TOO_LARGE", "message": "Request too large"}}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("auth"), str):
            raise ValueError
        if len(payload["auth"]) > 512:
            raise ValueError
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return 400, {"error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}
    user_id = database.authenticate_token(payload["auth"])
    if user_id and usage_manager is not None and not usage_manager.authorize(user_id):
        user_id = None
    return 200, {"ok": bool(user_id), "id": user_id or ""}


def build_connection_uri(host, port, auth, pin_sha256, label):
    bracketed_host = "[{}]".format(host) if ":" in host and not host.startswith("[") else host
    encoded_auth = urllib.parse.quote(auth, safe="")
    query = urllib.parse.urlencode({"insecure": "1", "pinSHA256": pin_sha256})
    return "hysteria2://{}@{}:{}/?{}#{}".format(
        encoded_auth,
        bracketed_host,
        int(port),
        query,
        urllib.parse.quote(label, safe=""),
    )


class LoginRateLimiter:
    def __init__(self, max_attempts=5, window_seconds=900, max_addresses=4096, clock=time.time):
        self.max_attempts = int(max_attempts)
        self.window_seconds = int(window_seconds)
        self.max_addresses = max(1, int(max_addresses))
        self.clock = clock
        self._attempts = {}
        self._lock = threading.Lock()

    def _recent(self, address):
        cutoff = self.clock() - self.window_seconds
        recent = [timestamp for timestamp in self._attempts.get(address, []) if timestamp > cutoff]
        if recent:
            self._attempts[address] = recent
        else:
            self._attempts.pop(address, None)
        return recent

    def is_allowed(self, address):
        with self._lock:
            return len(self._recent(address)) < self.max_attempts

    def record_failure(self, address):
        with self._lock:
            recent = self._recent(address)
            if not recent and len(self._attempts) >= self.max_addresses:
                oldest = min(
                    self._attempts,
                    key=lambda item: self._attempts[item][-1] if self._attempts[item] else 0,
                )
                self._attempts.pop(oldest, None)
            recent.append(self.clock())
            self._attempts[address] = recent

    def record_success(self, address):
        with self._lock:
            self._attempts.pop(address, None)


class JsonHandler(BaseHTTPRequestHandler):
    server_version = "Hysteria2Panel"
    sys_version = ""

    def _request_id(self):
        if not hasattr(self, "request_id"):
            self.request_id = uuid.uuid4().hex
        return self.request_id

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", self._request_id())
        super().end_headers()

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, message_format, *args):
        LOGGER.info(
            json.dumps(
                {
                    "event": "http_request",
                    "requestId": self._request_id(),
                    "remoteAddress": self.client_address[0],
                    "method": getattr(self, "command", ""),
                    "path": getattr(self, "path", "").split("?", 1)[0],
                    "message": message_format % args,
                },
                separators=(",", ":"),
            )
        )


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, address, handler, max_workers=64, request_timeout=10):
        self.max_workers = max(1, int(max_workers))
        self.request_timeout = max(1, int(request_timeout))
        self.tls_context = None
        self._worker_slots = threading.BoundedSemaphore(self.max_workers)
        super().__init__(address, handler)

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(self.request_timeout)
        if self.tls_context is not None:
            try:
                request = self.tls_context.wrap_socket(request, server_side=True)
            except Exception:
                request.close()
                raise
        return request, client_address

    def process_request(self, request, client_address):
        if not self._worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()


class InternalAuthHandler(JsonHandler):
    def do_POST(self):
        if self.path != "/auth":
            self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Not found"}})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if content_length < 0 or content_length > 4096:
            self.send_json(413, {"error": {"code": "REQUEST_TOO_LARGE", "message": "Request too large"}})
            return
        status, payload = handle_auth_payload(
            self.server.database,
            self.rfile.read(content_length),
            self.server.usage_manager,
        )
        self.send_json(status, payload)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Not found"}})


def make_internal_server(address, database, usage_manager=None):
    server = BoundedThreadingHTTPServer(address, InternalAuthHandler)
    server.database = database
    server.usage_manager = usage_manager
    return server


class PanelApplication:
    def __init__(
        self,
        database,
        public_host,
        hysteria_port,
        pin_sha256,
        stats_client,
        node_name="Hysteria 2",
        secure_cookies=True,
        rate_limiter=None,
        usage_manager=None,
        service_controller=None,
        system_metrics=None,
        update_checker=None,
    ):
        self.database = database
        self.public_host = public_host
        self.hysteria_port = int(hysteria_port)
        self.pin_sha256 = pin_sha256
        self.stats_client = stats_client
        self.usage_manager = usage_manager or UsageManager(database, stats_client)
        self.service_controller = service_controller or ServiceController()
        self.system_metrics = system_metrics or SystemMetrics()
        self.update_checker = update_checker or UpdateChecker()
        self.update_result = None
        self.node_name = node_name
        self.secure_cookies = bool(secure_cookies)
        self.rate_limiter = rate_limiter or LoginRateLimiter()
        self.user_action_lock = threading.Lock()


def _human_bytes(value):
    value = max(0, int(value or 0))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return "{:.1f} {}".format(value, unit) if unit != "B" else "{} B".format(value)
        value /= 1024.0


def _stat_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def summarize_dashboard(user_names, snapshot):
    traffic_by_user = snapshot.get("traffic", {})
    online_by_user = snapshot.get("online", {})
    summary = {
        "service_available": bool(snapshot.get("available")),
        "total_users": len(user_names),
        "inactive_users": 0,
        "online_devices": 0,
        "total_tx": 0,
        "total_rx": 0,
    }
    for name in user_names:
        traffic = traffic_by_user.get(name, {})
        tx = _stat_int(traffic.get("tx", 0))
        rx = _stat_int(traffic.get("rx", 0))
        summary["total_tx"] += tx
        summary["total_rx"] += rx
        summary["online_devices"] += _stat_int(online_by_user.get(name, 0))
        if tx == 0 and rx == 0:
            summary["inactive_users"] += 1
    return summary


class PanelHandler(JsonHandler):
    @property
    def cookie_name(self):
        if self.app.secure_cookies:
            return "hy2panel_session"
        return "hy2panel_http_session"

    @property
    def app(self):
        return self.server.application

    def _csp_nonce(self):
        if not hasattr(self, "_page_nonce"):
            self._page_nonce = secrets.token_urlsafe(18)
        return self._page_nonce

    def end_headers(self):
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{}'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'".format(
                self._csp_nonce()
            ),
        )
        if self.app.secure_cookies:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def _path(self):
        return urllib.parse.urlsplit(self.path).path

    def _redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_html(self, status, body):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_form(self):
        content_type = self.headers.get("Content-Type", "application/x-www-form-urlencoded")
        if content_type.split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
            raise ValueError("unsupported content type")
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if content_length < 0 or content_length > 16384:
            raise ValueError("invalid content length")
        parsed = urllib.parse.parse_qs(
            self.rfile.read(content_length).decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=10,
        )
        return {key: values[-1] for key, values in parsed.items()}

    def _session_token(self):
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return ""
        morsel = cookie.get(self.cookie_name)
        return morsel.value if morsel else ""

    def _session(self):
        return self.app.database.get_session(self._session_token())

    def _require_session(self):
        session = self._session()
        if not session:
            self._redirect("/login")
        return session

    def _require_csrf(self, session, form):
        submitted = form.get("csrf", "")
        return bool(submitted) and hmac.compare_digest(session["csrf_token"], submitted)

    def _page(self, title, content):
        return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Hysteria 2 Panel</title><style>{style}</style></head><body><main>{content}</main>
<script nonce="{nonce}">{script}</script></body></html>""".format(
            title=html.escape(title),
            style=PAGE_STYLE,
            content=content,
            nonce=self._csp_nonce(),
            script=PAGE_SCRIPT,
        )

    def _login_page(self, error=""):
        error_html = '<p class="error" role="alert">{}</p>'.format(html.escape(error)) if error else ""
        content = """<section class="card login"><h1>Hysteria 2 Panel</h1><p class="muted">管理员登录</p>{error}
<form method="post" action="/login"><label for="username">账号</label><input id="username" name="username" autocomplete="username" required maxlength="64">
<label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="1024">
<p><button type="submit">登录</button></p></form></section>""".format(error=error_html)
        return self._page("登录", content)

    def _dashboard(self, session, page_number=1):
        page_size = 50
        page_number = max(1, page_number)
        try:
            snapshot = self.app.usage_manager.snapshot()
        except Exception:
            LOGGER.exception("stats snapshot failed")
            snapshot = {"traffic": {}, "online": {}, "available": False}
        all_users = self.app.database.list_proxy_users_for_usage()
        result = self.app.database.list_proxy_users(page_size, (page_number - 1) * page_size)
        summary = summarize_dashboard([user["name"] for user in all_users], snapshot)
        try:
            service_status = self.app.service_controller.status()
        except Exception:
            LOGGER.exception("service status failed")
            service_status = "unknown"
        try:
            resources = self.app.system_metrics.snapshot()
        except Exception:
            LOGGER.exception("system metrics failed")
            resources = {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "memory_used": 0,
                "memory_total": 0,
                "disk_percent": 0.0,
                "disk_used": 0,
                "disk_total": 0,
                "uptime": "不可用",
            }
        csrf = html.escape(session["csrf_token"], quote=True)
        rows = []
        for user in result["users"]:
            name = user["name"]
            traffic = snapshot.get("traffic", {}).get(name, {})
            online = snapshot.get("online", {}).get(name, 0)
            used = _stat_int(traffic.get("tx", 0)) + _stat_int(traffic.get("rx", 0))
            limit = user["traffic_limit_bytes"]
            percent = min(100.0, 100.0 * used / limit) if limit else 0.0
            enabled = bool(user["enabled"])
            action_label = "禁用" if enabled else "启用"
            action_class = "danger" if enabled else "secondary"
            rows.append(
                """<tr><td><strong>{name}</strong><div class="inline-note">限 {device_limit} 个并发连接</div></td>
<td><span class="status {state_class}">{state}</span></td><td>{online} / {device_limit}</td><td>{tx} / {rx}</td>
<td class="traffic-cell"><progress max="100" value="{percent:.1f}" aria-label="{name} 总流量使用 {percent:.1f}%"></progress><div class="traffic-label"><span>{used} / {limit}</span><span>{percent:.1f}%</span></div></td>
<td><div class="actions">
<form class="inline" method="post" action="/users/{id}/toggle"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="{action_class}" type="submit">{action}</button></form>
<form class="inline" method="post" action="/users/{id}/rotate" data-confirm="轮换后旧连接地址会立即失效，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="warning" type="submit">轮换密钥</button></form>
<form class="inline" method="post" action="/users/{id}/delete" data-confirm="确定删除用户 {name} 吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="danger" type="submit">删除</button></form>
<form class="inline" method="post" action="/users/{id}/share"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="secondary" type="submit">分享</button></form>
<form class="inline" method="post" action="/users/{id}/reset" data-confirm="确定重置该用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="ghost" type="submit">重置流量</button></form>
</div></td></tr>""".format(
                    name=html.escape(name),
                    state="启用" if enabled else "禁用",
                    state_class="enabled" if enabled else "disabled",
                    online=int(online),
                    device_limit=user["device_limit"],
                    tx=_human_bytes(traffic.get("tx", 0)),
                    rx=_human_bytes(traffic.get("rx", 0)),
                    used=_human_bytes(used),
                    limit=_human_bytes(limit),
                    percent=percent,
                    id=user["id"],
                    generation=user["generation"],
                    csrf=csrf,
                    action=action_label,
                    action_class=action_class,
                )
            )
        if not rows:
            rows.append('<tr><td colspan="6" class="muted">暂无用户，请先创建。</td></tr>')
        pages = max(1, (result["total"] + page_size - 1) // page_size)
        pager = '<p class="muted">第 {} / {} 页，共 {} 个用户</p>'.format(page_number, pages, result["total"])
        stats_state = "正常" if summary["service_available"] else "异常"
        service_running = service_status == "active"
        service_label = "Hysteria 运行中" if service_running else "Hysteria 已停止"
        service_class = "" if service_running else " off"
        top_users = sorted(
            all_users,
            key=lambda item: item["tx_bytes"] + item["rx_bytes"],
            reverse=True,
        )[:5]
        rank_rows = "".join(
            '<div class="rank-row"><span class="rank-number">#{rank}</span><span class="rank-name">{name}</span><span class="rank-traffic">{traffic}</span></div>'.format(
                rank=index,
                name=html.escape(user["name"]),
                traffic=_human_bytes(user["tx_bytes"] + user["rx_bytes"]),
            )
            for index, user in enumerate(top_users, 1)
        ) or '<p class="muted">暂无用户流量。</p>'
        update = self.app.update_result
        if update:
            update_text = (
                '发现新版本 <a href="{url}">{latest}</a>'
                if update["update_available"]
                else "当前已是最新版本"
            ).format(url=html.escape(update["url"], quote=True), latest=html.escape(update["latest"]))
        else:
            update_text = "尚未检查远程版本"
        content = """<header class="topbar"><span class="eyebrow brand">HYSTERIA CONTROL CENTER</span><h1>Hysteria 2 用户管理面板</h1><span class="topbar-spacer"></span>
<span class="pill">服务状态 <strong>{service_label}</strong></span><span class="pill">最近刷新 <strong>{refreshed}</strong></span><span class="pill">当前用户 <strong>{total_users}</strong></span>
<form method="post" action="/logout"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary" type="submit">退出登录</button></form></header>
<section class="metrics" aria-label="服务概览">
<div class="metric"><span>不活跃用户</span><strong>{inactive_users}</strong><small class="muted">上传与下载均为 0</small></div>
<div class="metric"><span>在线设备</span><strong>{online_devices}</strong><small class="muted">按并发连接近似统计</small></div>
<div class="metric"><span>总上传流量</span><strong>{total_tx}</strong><small class="muted">全部用户累计上传</small></div>
<div class="metric"><span>总下载流量</span><strong>{total_rx}</strong><small class="muted">全部用户累计下载</small></div>
</section>
<section class="operations">
<article class="card"><div class="section-head"><div><h2>服务控制</h2><p class="muted">启停、重启和版本检查集中在这里。</p></div><span class="service-badge{service_class}">{service_label}</span></div>
<div class="button-row"><form method="post" action="/service/start"><input type="hidden" name="csrf" value="{csrf}"><button class="success" type="submit">启动 Hysteria</button></form>
<form method="post" action="/service/restart" data-confirm="确定重启 Hysteria 服务吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="warning" type="submit">重启 Hysteria</button></form>
<form method="post" action="/service/stop" data-confirm="停止后所有连接会中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">停止 Hysteria</button></form><a class="button secondary" href="/">刷新状态</a></div>
<div class="service-details"><div class="detail"><span class="muted">流量统计</span><strong class="{stats_class}">{stats}</strong></div><div class="detail"><span class="muted">服务端口</span><strong>UDP {port}</strong></div></div>
<div class="detail"><div class="version-row"><div><span class="muted">当前版本</span><strong>v{version}</strong></div><form method="post" action="/updates/check"><input type="hidden" name="csrf" value="{csrf}"><button type="submit">检查更新</button></form></div><p class="muted">{update_text}</p></div></article>
<article class="card"><div class="section-head"><div><h2>系统资源</h2><p class="muted">服务器实时负载与容量。</p></div></div><div class="resource-grid">
<div class="resource"><span class="muted">CPU 使用率</span><strong>{cpu:.1f}%</strong></div><div class="resource"><span class="muted">内存占用</span><strong>{memory:.1f}%</strong><small class="muted">{memory_used} / {memory_total}</small></div>
<div class="resource"><span class="muted">磁盘占用</span><strong>{disk:.1f}%</strong><small class="muted">{disk_used} / {disk_total}</small></div><div class="resource"><span class="muted">运行时长</span><strong>{uptime}</strong></div></div></article>
</section>
<section class="card"><div class="section-head"><div><h2>高流量用户</h2><p class="muted">当前累计总流量最高的 5 个账号。</p></div></div><div class="rank-list">{rank_rows}</div></section>
<section class="card"><div class="section-head"><div><h2>用户管理</h2><p class="muted">创建用户并设置并发设备和总流量限制。</p></div>
<form method="post" action="/users/reset-traffic" data-confirm="确定重置所有用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">重置全部流量</button></form></div>
<form class="create-grid" method="post" action="/users"><input type="hidden" name="csrf" value="{csrf}"><div class="wide"><label for="name">用户名称</label><input id="name" name="name" required maxlength="64" placeholder="例如：Alice 手机"></div>
<div><label for="device_limit">限制设备数</label><input id="device_limit" name="device_limit" type="number" min="1" max="100" value="3" required></div>
<div><label for="traffic_limit_gb">总流量（GB）</label><input id="traffic_limit_gb" name="traffic_limit_gb" type="number" min="1" max="1048576" value="250" required></div><button type="submit">添加用户</button></form>
<div class="table-wrap"><table><thead><tr><th>名称</th><th>状态</th><th>在线设备</th><th>上传 / 下载</th><th>总流量</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></div>{pager}</section>""".format(
            port=self.app.hysteria_port,
            stats=stats_state,
            stats_class="ok" if summary["service_available"] else "bad",
            service_label=service_label,
            service_class=service_class,
            refreshed=time.strftime("%H:%M:%S"),
            total_users=summary["total_users"],
            inactive_users=summary["inactive_users"],
            online_devices=summary["online_devices"],
            total_tx=_human_bytes(summary["total_tx"]),
            total_rx=_human_bytes(summary["total_rx"]),
            csrf=csrf,
            version=PANEL_VERSION,
            update_text=update_text,
            cpu=resources["cpu_percent"],
            memory=resources["memory_percent"],
            memory_used=_human_bytes(resources["memory_used"]),
            memory_total=_human_bytes(resources["memory_total"]),
            disk=resources["disk_percent"],
            disk_used=_human_bytes(resources["disk_used"]),
            disk_total=_human_bytes(resources["disk_total"]),
            uptime=html.escape(resources["uptime"]),
            rank_rows=rank_rows,
            rows="".join(rows),
            pager=pager,
        )
        return self._page("控制台", content)

    def _credentials_page(self, session, credentials):
        uri = build_connection_uri(
            self.app.public_host,
            self.app.hysteria_port,
            credentials["token"],
            self.app.pin_sha256,
            self.app.node_name,
        )
        content = """<header class="topbar"><h1>连接分享</h1><span class="topbar-spacer"></span><a class="button secondary" href="/">返回控制台</a></header>
<section class="card"><h2>{name}</h2><p class="muted">连接地址包含认证凭据，请只分享给受信任的人。</p>
<div class="copy-grid"><div><label for="token">认证密钥</label><textarea id="token" rows="2" readonly>{token}</textarea></div><button class="secondary" type="button" data-copy-target="token">复制密钥</button></div>
<div class="copy-grid"><div><label for="uri">Hysteria 2 连接地址</label><textarea id="uri" rows="4" readonly>{uri}</textarea></div><button type="button" data-copy-target="uri">一键复制分享</button></div>
<p class="notice" role="status">客户端会使用自签名证书，并同时固定证书 SHA-256 指纹。</p></section>""".format(
            name=html.escape(credentials["name"]),
            token=html.escape(credentials["token"]),
            uri=html.escape(uri),
        )
        return self._page("连接信息", content)

    def _error_page(self, status, message):
        content = '<section class="card"><h1>操作失败</h1><p class="error">{}</p><p><a class="button secondary" href="/">返回</a></p></section>'.format(
            html.escape(message)
        )
        self._send_html(status, self._page("操作失败", content))

    def do_GET(self):
        path = self._path()
        if path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if path == "/login":
            if self._session():
                self._redirect("/")
            else:
                self._send_html(200, self._login_page())
            return
        if path == "/":
            session = self._require_session()
            if not session:
                return
            try:
                page_number = int(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("page", ["1"])[0])
            except ValueError:
                page_number = 1
            self._send_html(200, self._dashboard(session, page_number))
            return
        self._error_page(404, "页面不存在")

    def do_POST(self):
        path = self._path()
        try:
            form = self._read_form()
        except (UnicodeDecodeError, ValueError):
            self._error_page(400, "请求格式无效")
            return
        if path == "/login":
            self._handle_login(form)
            return
        session = self._require_session()
        if not session:
            return
        if not self._require_csrf(session, form):
            self._error_page(403, "安全校验失败，请刷新页面后重试")
            return
        if path == "/logout":
            self.app.database.revoke_session(self._session_token())
            secure = "; Secure" if self.app.secure_cookies else ""
            self._redirect(
                "/login",
                "{}=; Path=/; Max-Age=0{}; HttpOnly; SameSite=Strict".format(
                    self.cookie_name, secure
                ),
            )
            return
        if path == "/users":
            self._handle_create_user(session, form)
            return
        if path == "/users/reset-traffic":
            self._handle_reset_all_traffic(session)
            return
        service_match = re.fullmatch(r"/service/(start|stop|restart)", path)
        if service_match:
            self._handle_service_action(session, service_match.group(1))
            return
        if path == "/updates/check":
            self._handle_update_check(session)
            return
        match = re.fullmatch(r"/users/(\d+)/(toggle|rotate|delete|share|reset)", path)
        if match:
            self._handle_user_action(session, int(match.group(1)), match.group(2), form)
            return
        self._error_page(404, "页面不存在")

    def _handle_login(self, form):
        address = self.client_address[0]
        if not self.app.rate_limiter.is_allowed(address):
            self._send_html(429, self._login_page("尝试次数过多，请稍后再试"))
            return
        admin_id = self.app.database.verify_admin(form.get("username", ""), form.get("password", ""))
        if not admin_id:
            self.app.rate_limiter.record_failure(address)
            self._audit_safely("anonymous", "login_failed", "admin")
            self._send_html(401, self._login_page("账号或密码错误"))
            return
        self.app.rate_limiter.record_success(address)
        raw_token, _ = self.app.database.create_session(admin_id)
        self._audit_safely(form.get("username", "admin")[:64], "login_succeeded", "admin")
        secure = "; Secure" if self.app.secure_cookies else ""
        cookie = "{}={}; Path=/; Max-Age=43200{}; HttpOnly; SameSite=Strict".format(
            self.cookie_name, raw_token, secure
        )
        self._redirect("/", cookie)

    def _handle_create_user(self, session, form):
        try:
            device_limit = int(form.get("device_limit", DEFAULT_DEVICE_LIMIT))
            traffic_limit_gb = int(form.get("traffic_limit_gb", 250))
            with self.app.user_action_lock:
                credentials = self.app.database.create_proxy_user(
                    form.get("name", ""),
                    device_limit=device_limit,
                    traffic_limit_bytes=traffic_limit_gb * 1024**3,
                )
        except (TypeError, ValueError) as exc:
            self._error_page(400, str(exc))
            return
        self._audit_safely(session["username"], "proxy_user_created", credentials["name"])
        self._send_html(201, self._credentials_page(session, credentials))

    def _audit_safely(self, actor, action, target):
        try:
            self.app.database.audit(actor, action, target, self.client_address[0])
        except Exception:
            LOGGER.exception("audit write failed")

    def _kick_safely(self, name):
        try:
            self.app.stats_client.kick(name)
        except Exception:
            LOGGER.exception("disconnecting active user failed")

    def _handle_user_action(self, session, user_id, action, form):
        try:
            generation = int(form.get("generation", ""))
            with self.app.user_action_lock:
                if action == "toggle":
                    user = self.app.database.get_proxy_user(user_id)
                    enabled = not bool(user["enabled"])
                    self.app.database.set_proxy_user_enabled(
                        user_id, enabled, expected_generation=generation
                    )
                    if not enabled:
                        self._kick_safely(user["name"])
                    audit_action = "proxy_user_enabled" if enabled else "proxy_user_disabled"
                    self._audit_safely(session["username"], audit_action, user["name"])
                    self._redirect("/")
                    return
                if action == "rotate":
                    credentials = self.app.database.rotate_proxy_token(
                        user_id, expected_generation=generation
                    )
                    self._kick_safely(credentials["name"])
                    self._audit_safely(
                        session["username"], "proxy_token_rotated", credentials["name"]
                    )
                    self._send_html(200, self._credentials_page(session, credentials))
                    return
                if action == "share":
                    user = self.app.database.get_proxy_user(user_id)
                    token = self.app.database.recover_proxy_token(user_id)
                    if token is None:
                        self._error_page(
                            409,
                            "该用户来自旧版本，原密钥不可逆保存；请先点击轮换密钥，再使用分享功能",
                        )
                        return
                    self._audit_safely(session["username"], "proxy_link_shared", user["name"])
                    self._send_html(
                        200,
                        self._credentials_page(
                            session, {"id": user["id"], "name": user["name"], "token": token}
                        ),
                    )
                    return
                if action == "reset":
                    user = self.app.database.get_proxy_user(user_id)
                    self.app.usage_manager.reset_user(
                        user_id, expected_generation=generation
                    )
                    self._audit_safely(
                        session["username"], "proxy_traffic_reset", user["name"]
                    )
                    self._redirect("/")
                    return
                user = self.app.database.delete_proxy_user(
                    user_id, expected_generation=generation
                )
                self._kick_safely(user["name"])
                self._audit_safely(session["username"], "proxy_user_deleted", user["name"])
            self._redirect("/")
        except (TypeError, ValueError):
            self._error_page(400, "请求版本无效，请刷新页面后重试")
        except ConflictError:
            self._error_page(409, "用户状态已变化，请刷新页面后重试")
        except KeyError:
            self._error_page(404, "用户不存在")
        except Exception:
            LOGGER.exception("user action failed")
            self._error_page(500, "操作未完成，请检查服务日志")

    def _handle_reset_all_traffic(self, session):
        try:
            with self.app.user_action_lock:
                self.app.usage_manager.reset_all()
            self._audit_safely(session["username"], "all_proxy_traffic_reset", "all")
            self._redirect("/")
        except Exception:
            LOGGER.exception("resetting all traffic failed")
            self._error_page(500, "流量重置失败，请检查服务日志")

    def _handle_service_action(self, session, action):
        try:
            if action in {"stop", "restart"}:
                try:
                    self.app.usage_manager.collect_once()
                except Exception:
                    LOGGER.exception("traffic sync before service action failed")
            state = self.app.service_controller.action(action)
            self._audit_safely(
                session["username"], "hysteria_service_{}".format(action), state
            )
            self._redirect("/")
        except (RuntimeError, ValueError):
            LOGGER.exception("service action failed")
            self._error_page(500, "服务控制失败，请检查服务日志")

    def _handle_update_check(self, session):
        try:
            self.app.update_result = self.app.update_checker.check()
            self._audit_safely(session["username"], "panel_update_checked", PANEL_VERSION)
            self._redirect("/")
        except Exception:
            LOGGER.exception("update check failed")
            self._error_page(502, "暂时无法检查更新，请稍后重试")


def make_panel_server(address, application):
    server = BoundedThreadingHTTPServer(address, PanelHandler)
    server.application = application
    return server


class HysteriaStatsClient:
    def __init__(self, base_url, secret, timeout=2):
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.timeout = timeout

    def _request(self, path, data=None):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={"Authorization": self.secret, "Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise RuntimeError("Hysteria stats API returned {}".format(response.status))
            raw_body = response.read()
        if not raw_body and data is not None:
            return {}
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Hysteria stats API returned invalid JSON")
        return payload

    def snapshot(self):
        traffic = self._request("/traffic")
        online = self.online()
        self._validate_traffic(traffic)
        return {"traffic": traffic, "online": online, "available": True}

    @staticmethod
    def _validate_traffic(traffic):
        if not isinstance(traffic, dict) or not all(
            isinstance(name, str)
            and isinstance(stats, dict)
            and isinstance(stats.get("tx", 0), int)
            and isinstance(stats.get("rx", 0), int)
            and stats.get("tx", 0) >= 0
            and stats.get("rx", 0) >= 0
            for name, stats in traffic.items()
        ):
            raise ValueError("Hysteria traffic response is invalid")

    def collect_and_clear(self):
        traffic = self._request("/traffic?clear=true")
        self._validate_traffic(traffic)
        return traffic

    def online(self):
        online = self._request("/online")
        if not isinstance(online, dict) or not all(
            isinstance(name, str) and isinstance(count, int) and count >= 0
            for name, count in online.items()
        ):
            raise ValueError("Hysteria online response is invalid")
        return online

    def kick(self, name):
        self._request("/kick", [name])


class UsageManager:
    def __init__(self, database, stats_client, pending_ttl=5, clock=time.monotonic):
        self.database = database
        self.stats_client = stats_client
        self.pending_ttl = max(1, int(pending_ttl))
        self.clock = clock
        self.lock = threading.Lock()
        self.pending = {}
        self.last_online = {}
        self.quota_kicked = set()

    def _collect_locked(self):
        traffic = self.stats_client.collect_and_clear()
        self.database.add_traffic(traffic)
        for user in self.database.list_proxy_users_for_usage():
            used = user["tx_bytes"] + user["rx_bytes"]
            name = user["name"]
            if used >= user["traffic_limit_bytes"]:
                if name not in self.quota_kicked:
                    self.stats_client.kick(name)
                    self.quota_kicked.add(name)
            else:
                self.quota_kicked.discard(name)
        return traffic

    def collect_once(self):
        with self.lock:
            return self._collect_locked()

    def authorize(self, name):
        with self.lock:
            try:
                self._collect_locked()
            except Exception:
                LOGGER.exception("traffic sync failed during authentication")
                return False
            user = self.database.get_proxy_user_by_name(name)
            if not user or not user["enabled"]:
                return False
            if user["tx_bytes"] + user["rx_bytes"] >= user["traffic_limit_bytes"]:
                return False
            try:
                online = self.stats_client.online()
            except Exception:
                LOGGER.exception("online snapshot failed during authentication")
                return False
            now = self.clock()
            pending = [
                timestamp
                for timestamp in self.pending.get(name, [])
                if now - timestamp < self.pending_ttl
            ]
            online_count = online.get(name, 0)
            previous_online = self.last_online.get(name, online_count)
            if online_count > previous_online:
                pending = pending[min(len(pending), online_count - previous_online) :]
            self.last_online[name] = online_count
            if online_count + len(pending) >= user["device_limit"]:
                self.pending[name] = pending
                return False
            pending.append(now)
            self.pending[name] = pending
            return True

    def snapshot(self):
        with self.lock:
            available = True
            try:
                self._collect_locked()
            except Exception:
                LOGGER.exception("traffic sync failed during dashboard snapshot")
                available = False
            try:
                online = self.stats_client.online()
            except Exception:
                LOGGER.exception("online snapshot failed during dashboard snapshot")
                online = {}
                available = False
            users = self.database.list_proxy_users_for_usage()
        return {
            "traffic": {
                user["name"]: {"tx": user["tx_bytes"], "rx": user["rx_bytes"]}
                for user in users
            },
            "online": online,
            "available": available,
        }

    def reset_user(self, user_id, expected_generation=None):
        with self.lock:
            self._collect_locked()
            user = self.database.get_proxy_user(user_id)
            self.database.reset_proxy_user_traffic(user_id, expected_generation)
            self.stats_client.kick(user["name"])
            self.quota_kicked.discard(user["name"])
            self.pending.pop(user["name"], None)

    def reset_all(self):
        with self.lock:
            self._collect_locked()
            self.database.reset_all_traffic()
            self.quota_kicked.clear()

    def run_collector(self, stop_event, interval=10):
        while not stop_event.wait(interval):
            try:
                self.collect_once()
            except Exception:
                LOGGER.exception("background traffic sync failed")


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


class UpdateChecker:
    URL = "https://api.github.com/repos/Elegying/Hysteria2-panel/releases/latest"

    def __init__(self, current_version=PANEL_VERSION, opener=urllib.request.urlopen):
        self.current_version = current_version
        self.opener = opener

    @staticmethod
    def _version_tuple(value):
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
        if not match:
            raise ValueError("release version is invalid")
        return tuple(int(part) for part in match.groups())

    def check(self):
        request = urllib.request.Request(
            self.URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Hysteria2-panel"},
        )
        with self.opener(request, timeout=3) as response:
            raw_body = response.read(16385)
        if len(raw_body) > 16384:
            raise ValueError("release response is too large")
        payload = json.loads(raw_body.decode("utf-8"))
        latest = payload.get("tag_name") if isinstance(payload, dict) else None
        if not isinstance(latest, str):
            raise ValueError("release response is invalid")
        latest_tuple = self._version_tuple(latest)
        return {
            "current": "v{}".format(self.current_version.lstrip("v")),
            "latest": "v{}.{}.{}".format(*latest_tuple),
            "update_available": latest_tuple > self._version_tuple(self.current_version),
            "url": "https://github.com/Elegying/Hysteria2-panel/releases/latest",
        }


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
        }


def _parse_port(mapping, name, default):
    try:
        value = int(mapping.get(name, default))
    except (TypeError, ValueError) as exc:
        raise ValueError("{} must be a port number".format(name)) from exc
    if not 1 <= value <= 65535:
        raise ValueError("{} must be between 1 and 65535".format(name))
    return value


class Settings:
    def __init__(self, **values):
        self.__dict__.update(values)

    @classmethod
    def from_mapping(cls, mapping):
        try:
            hmac_key = bytes.fromhex(mapping.get("HY2PANEL_HMAC_KEY", ""))
        except ValueError as exc:
            raise ValueError("HY2PANEL_HMAC_KEY must be hexadecimal") from exc
        if len(hmac_key) < 32:
            raise ValueError("HY2PANEL_HMAC_KEY must decode to at least 32 bytes")
        public_host = mapping.get("HY2PANEL_PUBLIC_HOST", "").strip()
        node_name = mapping.get("HY2PANEL_NODE_NAME", "Hysteria 2").strip()
        panel_scheme = mapping.get("HY2PANEL_PANEL_SCHEME", "https").strip().lower()
        stats_secret = mapping.get("HY2PANEL_STATS_SECRET", "")
        cert_pin = mapping.get("HY2PANEL_CERT_PIN", "").strip()
        if not public_host:
            raise ValueError("HY2PANEL_PUBLIC_HOST is required")
        if not node_name or len(node_name) > 64 or any(ord(character) < 32 for character in node_name):
            raise ValueError("HY2PANEL_NODE_NAME must contain 1 to 64 printable characters")
        if panel_scheme not in {"http", "https"}:
            raise ValueError("HY2PANEL_PANEL_SCHEME must be http or https")
        if len(stats_secret) < 8:
            raise ValueError("HY2PANEL_STATS_SECRET must contain at least 8 characters")
        if not cert_pin:
            raise ValueError("HY2PANEL_CERT_PIN is required")
        hysteria_port = _parse_port(mapping, "HY2PANEL_HYSTERIA_PORT", 19999)
        panel_port = _parse_port(mapping, "HY2PANEL_PANEL_PORT", 19998)
        auth_port = _parse_port(mapping, "HY2PANEL_AUTH_PORT", 19996)
        stats_port = _parse_port(mapping, "HY2PANEL_STATS_PORT", 19997)
        ports = {hysteria_port, panel_port, auth_port, stats_port}
        if len(ports) != 4:
            raise ValueError("Hysteria, panel, auth and stats ports must be different")
        return cls(
            database_path=Path(mapping.get("HY2PANEL_DB", "/var/lib/hysteria2-panel/panel.db")),
            hmac_key=hmac_key,
            public_host=public_host,
            node_name=node_name,
            hysteria_port=hysteria_port,
            panel_host=mapping.get("HY2PANEL_PANEL_HOST", "0.0.0.0"),
            panel_port=panel_port,
            panel_scheme=panel_scheme,
            auth_host=mapping.get("HY2PANEL_AUTH_HOST", "127.0.0.1"),
            auth_port=auth_port,
            stats_port=stats_port,
            stats_url="http://127.0.0.1:{}".format(stats_port),
            stats_secret=stats_secret,
            tls_cert=Path(mapping.get("HY2PANEL_TLS_CERT", "/etc/hysteria2-panel/server.crt")),
            tls_key=Path(mapping.get("HY2PANEL_TLS_KEY", "/etc/hysteria2-panel/server.key")),
            cert_pin=cert_pin,
        )


def initialize_admin(settings, username, password, if_missing=False):
    database = Database(settings.database_path, settings.hmac_key)
    database.initialize()
    if if_missing and database.has_admin():
        return False
    database.upsert_admin(username, password)
    return True


def run_service(settings):
    database = Database(settings.database_path, settings.hmac_key)
    database.initialize()
    if not database.has_admin():
        raise RuntimeError("no administrator exists; run init-admin first")
    stats_client = HysteriaStatsClient(settings.stats_url, settings.stats_secret)
    usage_manager = UsageManager(database, stats_client)
    application = PanelApplication(
        database=database,
        public_host=settings.public_host,
        hysteria_port=settings.hysteria_port,
        pin_sha256=settings.cert_pin,
        stats_client=stats_client,
        node_name=settings.node_name,
        secure_cookies=settings.panel_scheme == "https",
        usage_manager=usage_manager,
    )
    panel_server = make_panel_server((settings.panel_host, settings.panel_port), application)
    if settings.panel_scheme == "https":
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if hasattr(ssl, "TLSVersion"):
            tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.load_cert_chain(str(settings.tls_cert), str(settings.tls_key))
        panel_server.tls_context = tls_context
    auth_server = make_internal_server(
        (settings.auth_host, settings.auth_port), database, usage_manager
    )
    collector_stop = threading.Event()
    collector_thread = threading.Thread(
        target=usage_manager.run_collector,
        args=(collector_stop,),
        name="traffic-collector",
        daemon=True,
    )
    panel_thread = threading.Thread(
        target=panel_server.serve_forever,
        name="panel-{}".format(settings.panel_scheme),
        daemon=True,
    )
    panel_thread.start()
    collector_thread.start()
    LOGGER.info(
        json.dumps(
            {
                "event": "service_started",
                "panelAddress": "{}:{}".format(settings.panel_host, settings.panel_port),
                "authAddress": "{}:{}".format(settings.auth_host, settings.auth_port),
            },
            separators=(",", ":"),
        )
    )
    try:
        auth_server.serve_forever()
    finally:
        collector_stop.set()
        auth_server.server_close()
        panel_server.shutdown()
        panel_server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hysteria 2 multi-user panel")
    subcommands = parser.add_subparsers(dest="command", required=True)
    init_parser = subcommands.add_parser("init-admin", help="create or update the administrator")
    init_parser.add_argument("--username", required=True)
    init_parser.add_argument("--if-missing", action="store_true")
    subcommands.add_parser("serve", help="run the authentication service and panel")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_mapping(os.environ)
        if args.command == "init-admin":
            password = os.environ.get("HY2PANEL_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
            changed = initialize_admin(settings, args.username, password, args.if_missing)
            print(json.dumps({"status": "ok", "adminCreated": changed}, separators=(",", ":")))
            return 0
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        run_service(settings)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print("hysteria2-panel: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
