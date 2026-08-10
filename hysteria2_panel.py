#!/usr/bin/env python3
"""Dependency-free Hysteria 2 multi-user panel."""

import hashlib
import hmac
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
PBKDF2_ITERATIONS = 600000
NAME_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,64}$")
LOGGER = logging.getLogger("hysteria2-panel")


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
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
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

    def _fingerprint(self, token):
        return hmac.new(self.hmac_key, token.encode("utf-8"), hashlib.sha256).hexdigest()

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

    def create_proxy_user(self, name, token=None):
        name = _validate_name(name)
        token = _validate_token(token or secrets.token_urlsafe(24))
        now = int(time.time())
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO proxy_users(name, token_fingerprint, enabled, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                    (name, self._fingerprint(token), now, now),
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
            "SELECT id, name, enabled, created_at, updated_at FROM proxy_users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if not row:
            raise KeyError("proxy user not found")
        return row

    def set_proxy_user_enabled(self, user_id, enabled):
        now = int(time.time())
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            connection.execute(
                "UPDATE proxy_users SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, row["id"]),
            )

    def rotate_proxy_token(self, user_id, token=None):
        token = _validate_token(token or secrets.token_urlsafe(24))
        now = int(time.time())
        try:
            with self._connect() as connection:
                row = self._get_proxy_user(user_id, connection)
                connection.execute(
                    "UPDATE proxy_users SET token_fingerprint = ?, updated_at = ? WHERE id = ?",
                    (self._fingerprint(token), now, row["id"]),
                )
                return {"id": row["id"], "name": row["name"], "token": token}
        except sqlite3.IntegrityError as exc:
            raise ValueError("token already exists") from exc

    def delete_proxy_user(self, user_id):
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            connection.execute("DELETE FROM proxy_users WHERE id = ?", (row["id"],))

    def list_proxy_users(self, limit=50, offset=0):
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM proxy_users").fetchone()[0]
            rows = connection.execute(
                """
                SELECT id, name, enabled, created_at, updated_at
                FROM proxy_users ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return {"users": [dict(row) for row in rows], "total": total}

    def audit(self, actor, action, target, remote_ip):
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log(created_at, actor, action, target, remote_ip) VALUES (?, ?, ?, ?, ?)",
                (int(time.time()), actor, action, target, remote_ip),
            )


def handle_auth_payload(database, raw_body):
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
    def __init__(self, max_attempts=5, window_seconds=900, clock=time.time):
        self.max_attempts = int(max_attempts)
        self.window_seconds = int(window_seconds)
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
                    "method": self.command,
                    "path": self.path.split("?", 1)[0],
                    "message": message_format % args,
                },
                separators=(",", ":"),
            )
        )


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
        status, payload = handle_auth_payload(self.server.database, self.rfile.read(content_length))
        self.send_json(status, payload)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Not found"}})


def make_internal_server(address, database):
    server = ThreadingHTTPServer(address, InternalAuthHandler)
    server.database = database
    return server
