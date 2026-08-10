#!/usr/bin/env python3
"""Dependency-free Hysteria 2 multi-user panel."""

import argparse
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
import sqlite3
import ssl
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
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                    generation INTEGER NOT NULL DEFAULT 0,
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
            "SELECT id, name, enabled, generation, created_at, updated_at FROM proxy_users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if not row:
            raise KeyError("proxy user not found")
        return row

    def get_proxy_user(self, user_id):
        with self._connect() as connection:
            return dict(self._get_proxy_user(user_id, connection))

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
        token = _validate_token(token or secrets.token_urlsafe(24))
        now = int(time.time())
        try:
            with self._connect() as connection:
                row = self._get_proxy_user(user_id, connection)
                generation = row["generation"] if expected_generation is None else int(expected_generation)
                if generation != row["generation"]:
                    raise ConflictError("proxy user changed; refresh and try again")
                cursor = connection.execute(
                    "UPDATE proxy_users SET token_fingerprint = ?, generation = generation + 1, updated_at = ? WHERE id = ? AND generation = ?",
                    (self._fingerprint(token), now, row["id"], generation),
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
                SELECT id, name, enabled, generation, created_at, updated_at
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
        status, payload = handle_auth_payload(self.server.database, self.rfile.read(content_length))
        self.send_json(status, payload)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Not found"}})


def make_internal_server(address, database):
    server = BoundedThreadingHTTPServer(address, InternalAuthHandler)
    server.database = database
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
    ):
        self.database = database
        self.public_host = public_host
        self.hysteria_port = int(hysteria_port)
        self.pin_sha256 = pin_sha256
        self.stats_client = stats_client
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

    def end_headers(self):
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
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
<title>{title} · Hysteria 2 Panel</title><style>
:root{{--bg:#f4f6f8;--surface:#fff;--text:#18212b;--muted:#66717d;--line:#dfe4e8;--accent:#087f5b;--danger:#c92a2a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{width:min(1080px,calc(100% - 32px));margin:40px auto}}header{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:24px}}
h1{{font-size:24px;margin:0}}h2{{font-size:18px;margin:0 0 16px}}.card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:16px}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}}.metric{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px}}.metric strong{{display:block;font-size:22px;margin-top:4px}}.metric .ok{{color:var(--accent)}}.metric .bad{{color:var(--danger)}}
.login{{width:min(420px,100%);margin:12vh auto}}label{{display:block;font-weight:600;margin:12px 0 6px}}input,textarea{{width:100%;padding:10px 12px;border:1px solid #b8c1c9;border-radius:6px;font:inherit}}
button,.button{{display:inline-block;border:0;border-radius:6px;background:var(--accent);color:#fff;padding:9px 14px;font:inherit;font-weight:600;text-decoration:none;cursor:pointer}}
button.secondary,.button.secondary{{background:#52606d}}button.danger{{background:var(--danger)}}form.inline{{display:inline}}.actions{{display:flex;flex-wrap:wrap;gap:8px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:11px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}th{{color:var(--muted);font-size:13px}}
.status{{font-weight:700}}.enabled{{color:var(--accent)}}.disabled{{color:var(--danger)}}.muted{{color:var(--muted)}}.error{{color:var(--danger)}}code{{word-break:break-all}}
@media(max-width:720px){{main{{width:min(100% - 20px,1080px);margin:20px auto}}.metrics{{grid-template-columns:repeat(2,minmax(0,1fr))}}.table-wrap{{overflow-x:auto}}header{{align-items:flex-start;flex-direction:column}}}}
</style></head><body><main>{content}</main></body></html>""".format(
            title=html.escape(title), content=content
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
        result = self.app.database.list_proxy_users(page_size, (page_number - 1) * page_size)
        try:
            snapshot = self.app.stats_client.snapshot()
        except Exception:
            LOGGER.exception("stats snapshot failed")
            snapshot = {"traffic": {}, "online": {}, "available": False}
        summary = summarize_dashboard(self.app.database.list_proxy_user_names(), snapshot)
        rows = []
        for user in result["users"]:
            name = user["name"]
            traffic = snapshot.get("traffic", {}).get(name, {})
            online = snapshot.get("online", {}).get(name, 0)
            enabled = bool(user["enabled"])
            action_label = "禁用" if enabled else "启用"
            action_class = "danger" if enabled else "secondary"
            rows.append(
                """<tr><td>{name}</td><td><span class="status {state_class}">{state}</span></td><td>{online}</td><td>{tx} / {rx}</td>
<td><div class="actions"><form class="inline" method="post" action="/users/{id}/toggle"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="{action_class}" type="submit">{action}</button></form>
<form class="inline" method="post" action="/users/{id}/rotate"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="secondary" type="submit">轮换密钥</button></form>
<form class="inline" method="post" action="/users/{id}/delete"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="danger" type="submit">删除</button></form></div></td></tr>""".format(
                    name=html.escape(name),
                    state="启用" if enabled else "禁用",
                    state_class="enabled" if enabled else "disabled",
                    online=int(online),
                    tx=_human_bytes(traffic.get("tx", 0)),
                    rx=_human_bytes(traffic.get("rx", 0)),
                    id=user["id"],
                    generation=user["generation"],
                    csrf=html.escape(session["csrf_token"], quote=True),
                    action=action_label,
                    action_class=action_class,
                )
            )
        if not rows:
            rows.append('<tr><td colspan="5" class="muted">暂无用户，请先创建。</td></tr>')
        pages = max(1, (result["total"] + page_size - 1) // page_size)
        pager = '<p class="muted">第 {} / {} 页，共 {} 个用户</p>'.format(page_number, pages, result["total"])
        stats_state = "正常" if summary["service_available"] else "异常"
        stats_class = "ok" if summary["service_available"] else "bad"
        content = """<header><div><h1>Hysteria 2 Panel</h1><p class="muted">服务端口 UDP {port} · 流量统计 {stats}</p></div>
<form method="post" action="/logout"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary" type="submit">退出</button></form></header>
<section class="metrics" aria-label="服务概览">
<div class="metric"><span class="muted">服务状态</span><strong class="{stats_class}">{stats}</strong></div>
<div class="metric"><span class="muted">当前用户</span><strong>{total_users}</strong></div>
<div class="metric"><span class="muted">不活跃用户</span><strong>{inactive_users}</strong></div>
<div class="metric"><span class="muted">在线设备</span><strong>{online_devices}</strong></div>
<div class="metric"><span class="muted">总上传</span><strong>{total_tx}</strong></div>
<div class="metric"><span class="muted">总下载</span><strong>{total_rx}</strong></div>
</section>
<section class="card"><h2>创建用户</h2><form method="post" action="/users"><input type="hidden" name="csrf" value="{csrf}"><label for="name">用户名称</label>
<input id="name" name="name" required maxlength="64" placeholder="例如：Alice 手机"><p><button type="submit">创建并生成连接</button></p></form></section>
<section class="card"><h2>用户</h2><div class="table-wrap"><table><thead><tr><th>名称</th><th>状态</th><th>在线设备</th><th>上传 / 下载</th><th>操作</th></tr></thead>
<tbody>{rows}</tbody></table></div>{pager}</section>""".format(
            port=self.app.hysteria_port,
            stats=stats_state,
            stats_class=stats_class,
            total_users=summary["total_users"],
            inactive_users=summary["inactive_users"],
            online_devices=summary["online_devices"],
            total_tx=_human_bytes(summary["total_tx"]),
            total_rx=_human_bytes(summary["total_rx"]),
            csrf=html.escape(session["csrf_token"], quote=True),
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
        content = """<header><h1>连接信息</h1><a class="button secondary" href="/">返回控制台</a></header>
<section class="card"><p><strong>{name}</strong> 已创建。以下密钥和连接地址只显示一次，请立即保存。</p>
<label for="token">认证密钥</label><textarea id="token" rows="2" readonly>{token}</textarea>
<label for="uri">Hysteria 2 连接地址</label><textarea id="uri" rows="4" readonly>{uri}</textarea>
<p class="muted">客户端会使用自签名证书，并同时固定证书 SHA-256 指纹。</p></section>""".format(
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
            self._redirect(
                "/login",
                "{}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict".format(self.cookie_name),
            )
            return
        if path == "/users":
            self._handle_create_user(session, form)
            return
        match = re.fullmatch(r"/users/(\d+)/(toggle|rotate|delete)", path)
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
            with self.app.user_action_lock:
                credentials = self.app.database.create_proxy_user(form.get("name", ""))
        except ValueError as exc:
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
        online = self._request("/online")
        if not all(isinstance(name, str) and isinstance(stats, dict) for name, stats in traffic.items()):
            raise ValueError("Hysteria traffic response is invalid")
        if not all(isinstance(name, str) and isinstance(count, int) for name, count in online.items()):
            raise ValueError("Hysteria online response is invalid")
        return {"traffic": traffic, "online": online, "available": True}

    def kick(self, name):
        self._request("/kick", [name])


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
    application = PanelApplication(
        database=database,
        public_host=settings.public_host,
        hysteria_port=settings.hysteria_port,
        pin_sha256=settings.cert_pin,
        stats_client=stats_client,
        node_name=settings.node_name,
        secure_cookies=settings.panel_scheme == "https",
    )
    panel_server = make_panel_server((settings.panel_host, settings.panel_port), application)
    if settings.panel_scheme == "https":
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if hasattr(ssl, "TLSVersion"):
            tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.load_cert_chain(str(settings.tls_cert), str(settings.tls_key))
        panel_server.tls_context = tls_context
    auth_server = make_internal_server((settings.auth_host, settings.auth_port), database)
    panel_thread = threading.Thread(
        target=panel_server.serve_forever,
        name="panel-{}".format(settings.panel_scheme),
        daemon=True,
    )
    panel_thread.start()
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
