#!/usr/bin/env python3
"""Dependency-free Hysteria 2 multi-user panel."""

import argparse
import base64
import datetime
import functools
import getpass
import gzip
import hashlib
import hmac
import html
import http.cookies
import json
import logging
import os
import queue
import re
import secrets
import shutil
import sqlite3
import ssl
import stat
# Every subprocess invocation uses a fixed executable and an argv list.
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
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
PANEL_VERSION = "0.13.0"
BACKUP_FORMAT_VERSION = 1
MAX_BACKUP_ARCHIVE_BYTES = 64 * 1024**2
MAX_BACKUP_CONTENT_BYTES = 128 * 1024**2
MAX_STATS_RESPONSE_BYTES = 8 * 1024**2
FAVICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<title>Hysteria 2 Panel</title><rect x="2" y="2" width="60" height="60" rx="14" fill="#0b1a2c" stroke="#284867" stroke-width="2"/>
<path fill="#4bc493" d="M9 16h7v12h11V16h7v32h-7V35H16v13H9z"/>
<path fill="#f3f7ff" d="M37 24c0-7 4-11 11-11s11 4 11 10c0 5-3 8-8 12l-6 6h14v7H37v-8l10-9c4-3 5-5 5-7 0-3-1-4-4-4-3 0-4 2-4 5h-7z"/>
</svg>"""

PAGE_STYLE = """
:root{color-scheme:dark;--bg:#06111f;--surface:#0b1a2c;--surface-2:#132438;--text:#f3f7ff;--muted:#9aaac0;--line:#22364b;--accent:#5f91f7;--teal:#25b99a;--success:#4bc493;--warning:#f5b54b;--danger:#ff6675}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;text-rendering:optimizeLegibility}
main{width:min(1420px,calc(100% - 40px));margin:20px auto 42px}.topbar{display:flex;align-items:center;gap:12px;background:#102846;border:1px solid #284867;border-radius:20px;padding:18px 22px;margin-bottom:16px}.brand{min-width:max-content}.eyebrow{display:inline-block;border:1px solid #405b7c;border-radius:999px;padding:7px 13px;color:#c8d7ef;font-size:12px;letter-spacing:.12em}.topbar h1{font-size:28px;margin:0 4px}.topbar-spacer{flex:1}.pill{border:1px solid #3a526b;border-radius:999px;padding:8px 12px;color:var(--muted);white-space:nowrap}.pill strong{color:var(--text);margin-left:6px}
h1,h2,h3,p{margin-top:0}h2{font-size:20px;margin-bottom:4px}h3{font-size:16px}.muted{color:var(--muted)}.ok{color:var(--success)}.bad{color:var(--danger)}.warning{color:var(--warning)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}.metric,.card{background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 28px rgba(0,0,0,.12)}.metric{padding:18px;border-top:3px solid var(--teal)}.metric strong{display:block;font-size:26px;margin:9px 0 3px;font-variant-numeric:tabular-nums}.metric span{color:var(--muted)}
.operations{display:grid;gap:16px;margin-bottom:16px;align-items:start}.dashboard-trio{align-items:stretch;grid-template-columns:minmax(0,1.45fr) minmax(270px,.85fr) minmax(240px,.72fr)}.dashboard-trio>.card{height:100%;margin-bottom:0}.card{padding:20px;margin-bottom:16px}.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:1px solid var(--line);padding-bottom:15px;margin-bottom:16px}.dashboard-trio .section-head{padding-bottom:12px;margin-bottom:12px}.service-badge{border-radius:999px;padding:8px 13px;background:#123833;color:var(--success);font-weight:700;white-space:nowrap}.service-badge.off{background:#3a2028;color:#ff9aa4}
.button-row,.actions{display:flex;flex-wrap:wrap;gap:9px}button,.button{display:inline-block;border:1px solid transparent;border-radius:10px;background:var(--accent);color:#fff;padding:10px 15px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer;transition:filter .15s ease,transform .15s ease}button:hover,.button:hover{filter:brightness(1.08);transform:translateY(-1px)}button:active,.button:active{transform:none}button.secondary,.button.secondary{background:#1b2c40;border-color:#34495f}button.success{background:var(--success);color:#082016}button.warning{background:var(--warning);color:#251a05}button.danger{background:var(--danger)}button.ghost{background:transparent;border-color:#3a526b;color:#dce8f8}form.inline{display:inline}
.resource-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.resource,.detail{background:var(--surface-2);border:1px solid #283b50;border-radius:14px;padding:18px}.resource{padding:12px}.resource strong{font-size:18px;margin-top:4px}.resource small{font-size:11px}.resource strong,.detail strong{display:block}.service-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.compact-detail{padding:12px}.compact-detail strong{font-size:18px;margin-top:4px}.bbr-detail strong,.version-row strong{font-size:18px;margin-top:4px}.bbr-detail small{display:block;font-size:11px;margin-top:3px}.version-panel>p{font-size:12px;margin:4px 0 0}.version-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.compact-button{padding:8px 11px}.notice{padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#10233a;color:#c7d6ea}
.rank-list{display:grid;gap:6px}.rank-row{display:grid;grid-template-columns:28px minmax(0,1fr);align-items:center;gap:7px;padding:7px 9px;background:var(--surface-2);border:1px solid #283b50;border-radius:10px}.rank-main{display:flex;align-items:baseline;gap:8px;min-width:0}.rank-number{color:var(--accent);font-weight:800}.rank-name{font-weight:700;overflow:hidden;text-overflow:ellipsis}.rank-traffic{color:var(--muted);font-size:12px;white-space:nowrap}
.create-grid{display:grid;grid-template-columns:2fr 1fr 1fr auto;align-items:end;gap:12px;margin-bottom:22px}.section-actions,.user-tools{display:flex;align-items:center;gap:9px}.user-section-head{display:grid;grid-template-columns:minmax(220px,1fr) minmax(240px,360px) auto;grid-template-areas:"heading search actions";align-items:center}.user-heading{grid-area:heading}.user-section-head .user-search{grid-area:search}.user-section-head .section-actions{grid-area:actions}.user-tools{justify-content:flex-end;margin-bottom:14px}.user-search{width:100%;margin:0}.search-status{margin:0;white-space:nowrap}label{display:block;font-weight:650;margin-bottom:6px}input,textarea{width:100%;padding:11px 13px;border:1px solid #3a4d63;border-radius:9px;background:#101f31;color:var(--text);font:inherit}input:focus,textarea:focus,button:focus-visible,.button:focus-visible{outline:3px solid rgba(95,145,247,.38);outline-offset:2px}button:disabled{cursor:wait;opacity:.65}.table-wrap{overflow-x:auto;scrollbar-gutter:stable}table{width:100%;border-collapse:separate;border-spacing:0;min-width:1050px;font-variant-numeric:tabular-nums}th,td{padding:13px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}th{color:var(--muted);font-size:13px;white-space:nowrap}.user-table th{position:sticky;top:0;z-index:2;background:var(--surface);box-shadow:0 1px 0 var(--line)}.user-table tbody tr{transition:background-color .15s ease}.user-table tbody tr:hover{background:#0f2135}.sort-link{color:inherit;text-decoration:none}.sort-link:hover{text-decoration:underline}.status{font-weight:750}.enabled{color:var(--success)}.disabled{color:var(--danger)}progress{width:150px;height:10px;accent-color:var(--accent)}.traffic-cell{min-width:190px}.traffic-label{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--muted);margin-top:4px}.actions{min-width:360px}.user-table tr[hidden]{display:none}
.login{width:min(430px,100%);margin:12vh auto}.login-form{display:grid;gap:12px}.login-actions{margin:4px 0 0}.login-actions button{min-width:110px}.copy-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px;margin-bottom:16px}.error{color:var(--danger)}code{word-break:break-all}
.migration-dialog{width:min(820px,calc(100% - 32px));max-height:min(86vh,760px);padding:0;border:1px solid #35506d;border-radius:18px;background:var(--surface);color:var(--text);box-shadow:0 24px 80px rgba(0,0,0,.55);overflow:auto}.migration-dialog::backdrop{background:rgba(1,8,18,.78);backdrop-filter:blur(4px)}.credentials-dialog{width:min(680px,calc(100% - 32px))}.create-dialog{width:min(560px,calc(100% - 32px))}.create-dialog .create-grid{grid-template-columns:1fr 1fr;margin-bottom:0}.create-dialog .wide,.create-dialog .create-grid>button{grid-column:1/-1}.credentials-dialog textarea{min-height:118px}.dialog-shell{padding:22px}.dialog-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:16px}.dialog-head h2{margin-bottom:4px}.dialog-close{flex:0 0 auto;width:40px;height:40px;padding:0;border-radius:50%;background:#1b2c40;border-color:#34495f;font-size:24px;line-height:1}.migration-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.migration-grid .detail{height:100%}.migration-grid p:last-child{margin-bottom:0}.toast{position:fixed;right:18px;bottom:18px;z-index:20;max-width:min(420px,calc(100% - 36px));margin:0;padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#102846;box-shadow:0 12px 36px rgba(0,0,0,.4)}.toast.error{border-color:#8a3844;color:#ffd5da}.toast[hidden]{display:none}
@media(min-width:641px) and (max-width:1300px){.brand{display:none}.topbar h1{white-space:nowrap}}
@media(max-width:1050px){.topbar{flex-wrap:wrap}.topbar-spacer{display:none}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.operations{grid-template-columns:1fr}.create-grid{grid-template-columns:1fr 1fr}.create-grid .wide{grid-column:1/-1}.user-section-head{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"heading actions" "search search"}}
@media(max-width:640px){main{width:calc(100% - 16px);margin:8px auto 24px}.topbar{padding:16px;border-radius:16px;align-items:flex-start;gap:9px}.topbar h1{font-size:23px;width:100%;order:-2;margin:0 0 5px}.brand{display:none}.pill{flex:1 1 calc(50% - 5px);padding:8px 10px;font-size:12px;text-align:center}.topbar-action,.logout-form{flex:1 1 calc(50% - 5px)}.topbar-action,.logout-form button{width:100%}.metrics{grid-template-columns:1fr 1fr;gap:8px}.metric{padding:14px}.metric strong{font-size:20px}.metric small{font-size:12px}.card{padding:16px;border-radius:14px}.create-grid,.migration-grid,.create-dialog .create-grid{grid-template-columns:1fr}.section-head{flex-direction:column;padding-bottom:13px}.section-head>form,.section-head>form button,.create-grid>button{width:100%}.section-actions{display:grid;grid-template-columns:1fr 1fr;width:100%}.section-actions form,.section-actions button{width:100%}.user-section-head{grid-template-columns:1fr;grid-template-areas:"heading" "actions" "search"}.user-tools{align-items:stretch;flex-direction:column}.search-status{white-space:normal}.button-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.button-row form,.button-row button,.button-row .button{width:100%}.bbr-detail,.version-panel{padding:10px}.version-row{gap:6px}.compact-button{padding:7px 6px;font-size:12px;white-space:nowrap}.login{margin:8vh auto}.login-actions button{width:100%}.copy-grid{grid-template-columns:1fr}.copy-grid button{width:100%}.migration-dialog{width:calc(100% - 12px);max-height:calc(100dvh - 12px);border-radius:14px}.dialog-shell{padding:16px}.dialog-head{position:sticky;top:-16px;z-index:1;background:var(--surface);padding-top:16px}.user-table{overflow:visible}.user-table table,.user-table tbody{display:block;width:100%;min-width:0}.user-table thead{display:none}.user-table tr{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px 10px;margin-bottom:8px;padding:10px;background:var(--surface-2);border:1px solid #283b50;border-radius:12px}.user-table td{display:block;width:auto;min-width:0;padding:0;border-bottom:0}.user-table td:nth-child(1){grid-column:1}.user-table td:nth-child(2){grid-column:2}.user-table td:nth-child(3){grid-column:3}.user-table td:nth-child(4){grid-column:1;font-size:11px;color:var(--muted)}.user-table td:nth-child(5){grid-column:2/4}.user-table td:nth-child(6){grid-column:1/-1;padding-top:2px}.user-table .traffic-cell{min-width:0}.user-table .traffic-label{gap:5px;font-size:10px}.user-table progress{display:block;width:100%;height:8px}.user-table .actions{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:4px;min-width:0}.user-table .actions form,.user-table .actions button{width:100%;min-width:0}.user-table .actions button{padding:7px 3px;font-size:11px;white-space:nowrap}.user-table .empty-state{grid-column:1/-1!important;text-align:center}.toast{right:8px;bottom:8px;max-width:calc(100% - 16px)}}
@media(max-width:340px){.metrics{grid-template-columns:1fr}.pill{flex-basis:100%}.version-panel{padding-inline:8px}.version-row{align-items:flex-start;flex-direction:column;gap:4px}.bbr-detail strong,.version-row strong{font-size:16px}.compact-button{padding:7px 5px;font-size:11px;white-space:nowrap}.user-table .actions button{padding-inline:1px;font-size:10px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important}.migration-dialog::backdrop{backdrop-filter:none}}
"""

PAGE_SCRIPT = """
let noticeTimer;
function notify(message, isError) {
  const notice = document.querySelector('[data-page-status]');
  if (!notice) return;
  notice.textContent = message;
  notice.classList.toggle('error', Boolean(isError));
  notice.hidden = false;
  window.clearTimeout(noticeTimer);
  noticeTimer = window.setTimeout(function() { notice.hidden = true; }, 3200);
}
async function copyText(value) {
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(value); return true; } catch (_) {}
  }
  const buffer = document.createElement('textarea');
  buffer.value = value;
  buffer.setAttribute('readonly', '');
  buffer.style.position = 'fixed';
  buffer.style.opacity = '0';
  document.body.appendChild(buffer);
  buffer.focus();
  buffer.select();
  const copied = document.execCommand('copy');
  buffer.remove();
  return copied;
}
async function submitInlineForm(form) {
  const response = await fetch(form.action, {
    method: 'POST',
    headers: {'Accept': 'application/json'},
    body: new URLSearchParams(new FormData(form)),
    credentials: 'same-origin'
  });
  let payload;
  try { payload = await response.json(); } catch (_) { payload = {}; }
  if (!response.ok) throw new Error(payload.error || '操作失败，请刷新页面后重试');
  return payload;
}
document.addEventListener('click', function(event) {
  const opener = event.target.closest('[data-dialog-open]');
  if (opener) {
    const dialog = document.getElementById(opener.dataset.dialogOpen);
    if (dialog && typeof dialog.showModal === 'function') dialog.showModal();
    return;
  }
  const closer = event.target.closest('[data-dialog-close]');
  if (closer) {
    const dialog = closer.closest('dialog');
    if (dialog) dialog.close();
  }
});
document.addEventListener('click', async function(event) {
  const button = event.target.closest('[data-copy-target]');
  if (!button) return;
  const target = document.getElementById(button.dataset.copyTarget);
  if (!target) return;
  const copied = await copyText(target.value);
  button.textContent = copied ? '已复制' : '复制失败，请手动选择';
  notify(copied ? '节点代码已复制' : '自动复制失败，请手动选择节点代码', !copied);
});
document.addEventListener('submit', function(event) {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-share-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '复制中…';
  try {
    const payload = await submitInlineForm(form);
    const copied = await copyText(payload.uri);
    button.textContent = copied ? '已复制' : '复制失败';
    notify(copied ? payload.name + ' 的节点代码已复制' : '自动复制失败，请重试', !copied);
  } catch (error) {
    button.textContent = original;
    notify(error.message || '分享失败，请重试', true);
  } finally {
    button.disabled = false;
    window.setTimeout(function() { button.textContent = original; }, 2200);
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-create-user-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = '添加中…';
  try {
    const payload = await submitInlineForm(form);
    const dialog = document.getElementById('credentials-dialog');
    dialog.querySelector('[data-credentials-title]').textContent = payload.name + ' 的节点信息';
    dialog.querySelector('#credentials-uri').value = payload.uri;
    dialog.dataset.refreshOnClose = '1';
    form.reset();
    const createDialog = form.closest('dialog');
    if (createDialog) createDialog.close();
    dialog.showModal();
  } catch (error) {
    notify(error.message || '添加用户失败，请重试', true);
  } finally {
    button.disabled = false;
    button.textContent = '添加用户';
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-restore-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const file = form.querySelector('input[type="file"]');
  const status = form.querySelector('[data-restore-status]');
  if (!file || !file.files.length) { status.textContent = '请选择 ZIP 备份文件'; return; }
  if (!window.confirm('恢复会替换全部代理用户、签名密钥和证书，并短暂重启服务。确定继续吗？')) return;
  status.textContent = '正在校验并上传备份…';
  try {
    const response = await fetch('/restore', {
      method: 'POST',
      headers: {'Content-Type': 'application/zip', 'X-HY2Panel-CSRF': form.dataset.csrf},
      body: file.files[0],
      credentials: 'same-origin'
    });
    const body = await response.text();
    if (!response.ok) throw new Error(body.replace(/<[^>]*>/g, ' ').replace(/\\s+/g, ' ').trim());
    status.textContent = '恢复任务已启动，服务将在数秒后重启；请稍后重新登录。';
  } catch (error) {
    status.textContent = error.message || '恢复上传失败，请重试';
  }
});
const credentialsDialog = document.getElementById('credentials-dialog');
if (credentialsDialog) credentialsDialog.addEventListener('close', function() {
  if (credentialsDialog.dataset.refreshOnClose === '1') window.location.href = '/';
});
const userSearch = document.querySelector('[data-user-search]');
if (userSearch) {
  const userRows = Array.from(document.querySelectorAll('[data-user-name]'));
  const searchStatus = document.querySelector('[data-search-status]');
  let filterFrame = 0;
  function filterUsers() {
    const query = userSearch.value.trim().toLocaleLowerCase();
    let visible = 0;
    userRows.forEach(function(row) {
      const matches = row.dataset.userName.toLocaleLowerCase().includes(query);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    if (searchStatus) searchStatus.textContent = query ? '显示 ' + visible + ' / ' + userRows.length + ' 个用户' : '共 ' + userRows.length + ' 个用户';
  }
  userSearch.addEventListener('input', function() {
    if (filterFrame) window.cancelAnimationFrame(filterFrame);
    filterFrame = window.requestAnimationFrame(filterUsers);
  });
  filterUsers();
}
"""


class ConflictError(Exception):
    """Raised when an administrator submits a stale user mutation."""


class BackupValidationError(ValueError):
    """Raised when a backup cannot be restored safely."""


class BackupManager:
    FILE_LIMITS = {
        "manifest.json": 64 * 1024,
        "data/panel.db": MAX_BACKUP_CONTENT_BYTES,
        "secrets/hmac-key.hex": 512,
        "tls/server.crt": 1024 * 1024,
        "tls/server.key": 1024 * 1024,
    }
    PAYLOAD_NAMES = {
        "data/panel.db",
        "secrets/hmac-key.hex",
        "tls/server.crt",
        "tls/server.key",
    }
    PROXY_COLUMNS = (
        "id",
        "name",
        "token_fingerprint",
        "token_seed",
        "enabled",
        "generation",
        "device_limit",
        "traffic_limit_bytes",
        "tx_bytes",
        "rx_bytes",
        "created_at",
        "updated_at",
    )

    def __init__(
        self,
        database,
        hmac_key,
        tls_cert,
        tls_key,
        public_host,
        hysteria_port,
        node_name="Hysteria 2",
        work_dir=Path("/var/lib/hysteria2-panel/backup-restore"),
        runner=subprocess.run,
    ):
        self.database = database
        self.hmac_key = bytes(hmac_key)
        self.tls_cert = Path(tls_cert)
        self.tls_key = Path(tls_key)
        self.public_host = str(public_host).strip()
        self.hysteria_port = int(hysteria_port)
        self.node_name = str(node_name)
        self.work_dir = Path(work_dir)
        self.runner = runner

    @property
    def pending_archive(self):
        return self.work_dir / "pending-restore.zip"

    @staticmethod
    def _sha256(value):
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def _certificate_pin(certificate):
        try:
            pem = certificate.decode("ascii")
            der = ssl.PEM_cert_to_DER_cert(pem)
            return hashlib.sha256(der).hexdigest()
        except (UnicodeDecodeError, ValueError) as exc:
            raise BackupValidationError("证书格式无效") from exc

    def _certificate_details(self, certificate_path, private_key_path):
        certificate_public_key = self.runner(
            ["/usr/bin/openssl", "x509", "-in", str(certificate_path), "-pubkey", "-noout"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        private_public_key = self.runner(
            ["/usr/bin/openssl", "pkey", "-in", str(private_key_path), "-pubout"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if (
            certificate_public_key.returncode != 0
            or private_public_key.returncode != 0
            or not hmac.compare_digest(certificate_public_key.stdout, private_public_key.stdout)
        ):
            raise BackupValidationError("证书与私钥不匹配")
        expiry = self.runner(
            ["/usr/bin/openssl", "x509", "-in", str(certificate_path), "-enddate", "-noout"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if expiry.returncode != 0 or not expiry.stdout.startswith("notAfter="):
            raise BackupValidationError("无法读取证书有效期")
        raw_expiry = expiry.stdout.strip().split("=", 1)[1]
        try:
            expires_at = datetime.datetime.strptime(
                raw_expiry, "%b %d %H:%M:%S %Y %Z"
            ).replace(tzinfo=datetime.timezone.utc)
        except ValueError as exc:
            raise BackupValidationError("证书有效期格式无效") from exc
        return expires_at.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _copy_database(source_path, destination_path):
        with sqlite3.connect(str(source_path), timeout=10) as source:
            with sqlite3.connect(str(destination_path), timeout=10) as destination:
                source.backup(destination)

    @staticmethod
    def _read_bounded(path, maximum):
        with Path(path).open("rb") as source:
            value = source.read(maximum + 1)
        if len(value) > maximum:
            raise BackupValidationError("备份内容超过允许大小")
        return value

    def create_archive(self):
        self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = self.work_dir / "hysteria2-panel-backup-{}-{}.zip".format(
            timestamp, secrets.token_hex(4)
        )
        with tempfile.TemporaryDirectory(dir=str(self.work_dir)) as temporary:
            temporary_path = Path(temporary)
            database_path = temporary_path / "panel.db"
            self._copy_database(self.database.path, database_path)
            with sqlite3.connect(str(database_path)) as connection:
                connection.execute("PRAGMA journal_mode = DELETE")
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("DELETE FROM sessions")
                connection.execute("DELETE FROM admins")
                connection.execute("DELETE FROM audit_log")
            certificate = self._read_bounded(self.tls_cert, self.FILE_LIMITS["tls/server.crt"])
            private_key = self._read_bounded(self.tls_key, self.FILE_LIMITS["tls/server.key"])
            temp_certificate = temporary_path / "server.crt"
            temp_private_key = temporary_path / "server.key"
            temp_certificate.write_bytes(certificate)
            temp_private_key.write_bytes(private_key)
            expires_at = self._certificate_details(temp_certificate, temp_private_key)
            payloads = {
                "data/panel.db": self._read_bounded(
                    database_path, self.FILE_LIMITS["data/panel.db"]
                ),
                "secrets/hmac-key.hex": self.hmac_key.hex().encode("ascii") + b"\n",
                "tls/server.crt": certificate,
                "tls/server.key": private_key,
            }
            with sqlite3.connect(str(database_path)) as connection:
                user_count = connection.execute("SELECT COUNT(*) FROM proxy_users").fetchone()[0]
            manifest = {
                "formatVersion": BACKUP_FORMAT_VERSION,
                "createdAt": datetime.datetime.now(datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "panelVersion": PANEL_VERSION,
                "proxyUserCount": int(user_count),
                "source": {
                    "publicHost": self.public_host,
                    "hysteriaPort": self.hysteria_port,
                    "nodeName": self.node_name,
                },
                "certificate": {
                    "pinSHA256": self._certificate_pin(certificate),
                    "notAfter": expires_at,
                },
                "files": {
                    name: {"sha256": self._sha256(value), "size": len(value)}
                    for name, value in sorted(payloads.items())
                },
            }
            manifest_bytes = json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as package:
                package.writestr("manifest.json", manifest_bytes)
                for name, value in payloads.items():
                    package.writestr(name, value)
        os.chmod(archive_path, 0o600)
        return archive_path

    def _read_archive(self, archive_path):
        archive_path = Path(archive_path)
        try:
            archive_size = archive_path.stat().st_size
        except OSError as exc:
            raise BackupValidationError("无法读取备份文件") from exc
        if archive_size <= 0 or archive_size > MAX_BACKUP_ARCHIVE_BYTES:
            raise BackupValidationError("备份文件大小无效")
        try:
            with zipfile.ZipFile(archive_path) as package:
                entries = package.infolist()
                names = [entry.filename for entry in entries]
                if len(names) != len(set(names)) or set(names) != set(self.FILE_LIMITS):
                    raise BackupValidationError("备份文件结构无效")
                total_size = 0
                payloads = {}
                for entry in entries:
                    mode = (entry.external_attr >> 16) & 0o170000
                    if (
                        entry.is_dir()
                        or mode == stat.S_IFLNK
                        or entry.filename.startswith(("/", "\\"))
                        or ".." in Path(entry.filename).parts
                        or entry.file_size < 0
                        or entry.file_size > self.FILE_LIMITS[entry.filename]
                    ):
                        raise BackupValidationError("备份文件结构无效")
                    total_size += entry.file_size
                    if total_size > MAX_BACKUP_CONTENT_BYTES + 3 * 1024**2:
                        raise BackupValidationError("备份解压内容过大")
                    with package.open(entry) as source:
                        value = source.read(self.FILE_LIMITS[entry.filename] + 1)
                    if len(value) != entry.file_size or len(value) > self.FILE_LIMITS[entry.filename]:
                        raise BackupValidationError("备份内容大小无效")
                    payloads[entry.filename] = value
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            if isinstance(exc, BackupValidationError):
                raise
            raise BackupValidationError("ZIP 备份文件无效") from exc
        try:
            manifest = json.loads(payloads["manifest.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupValidationError("备份清单无效") from exc
        if not isinstance(manifest, dict) or manifest.get("formatVersion") != BACKUP_FORMAT_VERSION:
            raise BackupValidationError("不支持的备份格式版本")
        file_manifest = manifest.get("files")
        if not isinstance(file_manifest, dict) or set(file_manifest) != self.PAYLOAD_NAMES:
            raise BackupValidationError("备份校验清单无效")
        for name in self.PAYLOAD_NAMES:
            details = file_manifest.get(name)
            value = payloads[name]
            if (
                not isinstance(details, dict)
                or details.get("size") != len(value)
                or details.get("sha256") != self._sha256(value)
            ):
                raise BackupValidationError("备份文件校验失败")
        return manifest, payloads

    def _validate_database(self, database_bytes, hmac_key, directory):
        database_path = Path(directory) / "validated.db"
        database_path.write_bytes(database_bytes)
        try:
            with sqlite3.connect(str(database_path)) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise BackupValidationError("用户数据库完整性检查失败")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                if not {"admins", "proxy_users", "sessions", "audit_log"}.issubset(tables):
                    raise BackupValidationError("用户数据库结构不完整")
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(proxy_users)")
                }
                if not set(self.PROXY_COLUMNS).issubset(columns):
                    raise BackupValidationError("用户数据库版本不兼容")
                users = connection.execute(
                    "SELECT id, token_seed, token_fingerprint FROM proxy_users"
                ).fetchall()
            verifier = Database(database_path, hmac_key)
            for user_id, seed, expected_fingerprint in users:
                if seed is None:
                    continue
                token = verifier._token_from_seed(bytes(seed))
                if not hmac.compare_digest(verifier._fingerprint(token), expected_fingerprint):
                    raise BackupValidationError("用户签名密钥与数据库不匹配")
            return len(users)
        except sqlite3.DatabaseError as exc:
            raise BackupValidationError("用户数据库无效") from exc

    def validate_archive(self, archive_path, require_compatible_endpoint=False):
        self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        manifest, payloads = self._read_archive(archive_path)
        hmac_hex = payloads["secrets/hmac-key.hex"].decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{64,256}", hmac_hex) or len(hmac_hex) % 2:
            raise BackupValidationError("签名密钥格式无效")
        hmac_key = bytes.fromhex(hmac_hex)
        source = manifest.get("source")
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("publicHost"), str)
            or not isinstance(source.get("hysteriaPort"), int)
            or not isinstance(source.get("nodeName"), str)
        ):
            raise BackupValidationError("备份来源信息无效")
        if require_compatible_endpoint:
            if source["publicHost"].lower() != self.public_host.lower():
                raise BackupValidationError("备份域名与当前部署域名不一致，旧节点无法无感迁移")
            if source["hysteriaPort"] != self.hysteria_port:
                raise BackupValidationError("备份 UDP 端口与当前部署端口不一致，旧节点无法无感迁移")
        with tempfile.TemporaryDirectory(dir=str(self.work_dir)) as temporary:
            user_count = self._validate_database(payloads["data/panel.db"], hmac_key, temporary)
            certificate_path = Path(temporary) / "server.crt"
            private_key_path = Path(temporary) / "server.key"
            certificate_path.write_bytes(payloads["tls/server.crt"])
            private_key_path.write_bytes(payloads["tls/server.key"])
            expires_at = self._certificate_details(certificate_path, private_key_path)
        certificate = manifest.get("certificate")
        pin = self._certificate_pin(payloads["tls/server.crt"])
        if (
            not isinstance(certificate, dict)
            or certificate.get("pinSHA256") != pin
            or certificate.get("notAfter") != expires_at
            or manifest.get("proxyUserCount") != user_count
        ):
            raise BackupValidationError("证书或用户数量校验失败")
        return manifest

    def stage_archive(self, source, content_length):
        if content_length <= 0 or content_length > MAX_BACKUP_ARCHIVE_BYTES:
            raise BackupValidationError("备份文件大小无效")
        self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".upload-", suffix=".zip", dir=str(self.work_dir)
        )
        remaining = content_length
        try:
            with os.fdopen(descriptor, "wb") as target:
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise BackupValidationError("备份文件上传不完整")
                    target.write(chunk)
                    remaining -= len(chunk)
                target.flush()
                os.fsync(target.fileno())
            manifest = self.validate_archive(
                temporary, require_compatible_endpoint=True
            )
            os.chmod(temporary, 0o600)
            try:
                os.link(temporary, self.pending_archive)
            except FileExistsError as exc:
                raise BackupValidationError("已有恢复任务正在等待或执行") from exc
            return manifest
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _updated_env(original, values):
        lines = original.decode("utf-8").splitlines()
        found = set()
        updated = []
        for line in lines:
            match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
            if match and match.group(1) in values:
                key = match.group(1)
                if key in found:
                    raise BackupValidationError("环境配置包含重复关键项")
                updated.append("{}={}".format(key, values[key]))
                found.add(key)
            else:
                updated.append(line)
        for key, value in values.items():
            if key not in found:
                updated.append("{}={}".format(key, value))
        return ("\n".join(updated) + "\n").encode("utf-8")

    @staticmethod
    def _replace_bytes(path, value):
        path = Path(path)
        existing = path.stat()
        descriptor, temporary = tempfile.mkstemp(prefix=".restore-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(value)
                target.flush()
                os.fsync(target.fileno())
            os.chmod(temporary, stat.S_IMODE(existing.st_mode))
            if hasattr(os, "chown"):
                os.chown(temporary, existing.st_uid, existing.st_gid)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _required_env_value(env_bytes, key):
        try:
            lines = env_bytes.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise BackupValidationError("恢复后的环境配置编码无效") from exc
        values = []
        for line in lines:
            match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
            if match and match.group(1) == key:
                values.append(match.group(2))
        if len(values) != 1:
            raise BackupValidationError("恢复后的环境配置缺少或重复关键项")
        return values[0]

    def _proxy_rows(self, database_path):
        try:
            with sqlite3.connect(str(database_path)) as connection:
                return connection.execute(
                    # Identifiers come only from the fixed PROXY_COLUMNS tuple.
                    "SELECT {} FROM proxy_users ORDER BY id".format(  # nosec B608
                        ",".join(self.PROXY_COLUMNS)
                    )
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise BackupValidationError("恢复后的用户数据库无法读取") from exc

    def _validate_applied_restore(
        self, env_file, restored_hmac, manifest, directory, expected_database
    ):
        database_bytes = self._read_bounded(
            self.database.path, self.FILE_LIMITS["data/panel.db"]
        )
        user_count = self._validate_database(database_bytes, restored_hmac, directory)
        if self._proxy_rows(self.database.path) != self._proxy_rows(expected_database):
            raise BackupValidationError("恢复后的用户数据与备份不一致")
        certificate = self._read_bounded(
            self.tls_cert, self.FILE_LIMITS["tls/server.crt"]
        )
        private_key = self._read_bounded(
            self.tls_key, self.FILE_LIMITS["tls/server.key"]
        )
        certificate_path = Path(directory) / "applied-server.crt"
        private_key_path = Path(directory) / "applied-server.key"
        certificate_path.write_bytes(certificate)
        private_key_path.write_bytes(private_key)
        expires_at = self._certificate_details(certificate_path, private_key_path)
        expected_certificate = manifest["certificate"]
        if (
            user_count != manifest["proxyUserCount"]
            or self._sha256(certificate)
            != manifest["files"]["tls/server.crt"]["sha256"]
            or self._sha256(private_key)
            != manifest["files"]["tls/server.key"]["sha256"]
            or self._certificate_pin(certificate) != expected_certificate["pinSHA256"]
            or expires_at != expected_certificate["notAfter"]
        ):
            raise BackupValidationError("恢复后的节点身份校验失败")
        env_bytes = Path(env_file).read_bytes()
        if not hmac.compare_digest(
            self._required_env_value(env_bytes, "HY2PANEL_HMAC_KEY"),
            restored_hmac.hex(),
        ) or not hmac.compare_digest(
            self._required_env_value(env_bytes, "HY2PANEL_CERT_PIN"),
            expected_certificate["pinSHA256"],
        ):
            raise BackupValidationError("恢复后的签名密钥或证书指纹不一致")

    def apply_archive(self, archive_path, env_file, backup_root):
        self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        manifest = self.validate_archive(archive_path, require_compatible_endpoint=True)
        _, payloads = self._read_archive(archive_path)
        restored_hmac = bytes.fromhex(
            payloads["secrets/hmac-key.hex"].decode("ascii").strip()
        )
        backup_root = Path(backup_root)
        backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup_dir = backup_root / "restore-{}-{}".format(
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            secrets.token_hex(4),
        )
        backup_dir.mkdir(mode=0o700)
        env_file = Path(env_file)
        self._copy_database(self.database.path, backup_dir / "panel.db")
        shutil.copy2(self.tls_cert, backup_dir / "server.crt")
        shutil.copy2(self.tls_key, backup_dir / "server.key")
        shutil.copy2(env_file, backup_dir / "panel.env")
        with tempfile.TemporaryDirectory(dir=str(self.work_dir)) as temporary:
            staged_database = Path(temporary) / "panel.db"
            incoming_database = Path(temporary) / "incoming.db"
            self._copy_database(self.database.path, staged_database)
            incoming_database.write_bytes(payloads["data/panel.db"])
            with sqlite3.connect(str(incoming_database)) as source:
                source.row_factory = sqlite3.Row
                rows = source.execute(
                    # Identifiers come only from the fixed PROXY_COLUMNS tuple.
                    "SELECT {} FROM proxy_users ORDER BY id".format(  # nosec B608
                        ",".join(self.PROXY_COLUMNS)
                    )
                ).fetchall()
            with sqlite3.connect(str(staged_database)) as destination:
                destination.execute("PRAGMA journal_mode = DELETE")
                destination.execute("PRAGMA foreign_keys = ON")
                destination.execute("DELETE FROM sessions")
                destination.execute("DELETE FROM proxy_users")
                destination.executemany(
                    # Identifiers come only from the fixed PROXY_COLUMNS tuple.
                    "INSERT INTO proxy_users ({}) VALUES ({})".format(  # nosec B608
                        ",".join(self.PROXY_COLUMNS),
                        ",".join("?" for _ in self.PROXY_COLUMNS),
                    ),
                    [tuple(row[column] for column in self.PROXY_COLUMNS) for row in rows],
                )
            self._validate_database(
                self._read_bounded(staged_database, self.FILE_LIMITS["data/panel.db"]),
                restored_hmac,
                temporary,
            )
            new_env = self._updated_env(
                env_file.read_bytes(),
                {
                    "HY2PANEL_HMAC_KEY": restored_hmac.hex(),
                    "HY2PANEL_CERT_PIN": manifest["certificate"]["pinSHA256"],
                },
            )
            try:
                self._replace_bytes(
                    self.database.path,
                    self._read_bounded(staged_database, self.FILE_LIMITS["data/panel.db"]),
                )
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(self.database.path) + suffix)
                    if sidecar.exists():
                        sidecar.unlink()
                self._replace_bytes(self.tls_cert, payloads["tls/server.crt"])
                self._replace_bytes(self.tls_key, payloads["tls/server.key"])
                self._replace_bytes(env_file, new_env)
                self._validate_applied_restore(
                    env_file,
                    restored_hmac,
                    manifest,
                    temporary,
                    incoming_database,
                )
            except Exception:
                self._replace_bytes(self.database.path, (backup_dir / "panel.db").read_bytes())
                self._replace_bytes(self.tls_cert, (backup_dir / "server.crt").read_bytes())
                self._replace_bytes(self.tls_key, (backup_dir / "server.key").read_bytes())
                self._replace_bytes(env_file, (backup_dir / "panel.env").read_bytes())
                raise
        result = dict(manifest)
        result["automaticBackup"] = str(backup_dir)
        return result

    def apply_pending_archive(self, env_file, backup_root):
        if not self.pending_archive.is_file():
            raise RuntimeError("no pending restore archive")
        try:
            result = self.apply_archive(
                self.pending_archive,
                env_file=env_file,
                backup_root=backup_root,
            )
        except Exception:
            quarantine = self.work_dir / "failed-restore-{}-{}.zip".format(
                datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                secrets.token_hex(4),
            )
            try:
                os.chmod(self.pending_archive, 0o600)
                os.replace(self.pending_archive, quarantine)
            except OSError:
                LOGGER.exception("failed restore archive could not be quarantined")
            raise
        self.pending_archive.unlink()
        return result


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
        if not isinstance(password, str) or len(password) > 1024:
            return False
        parts = encoded.split("$")
        algorithm = parts[0]
        if algorithm == "scrypt" and len(parts) == 6 and hasattr(hashlib, "scrypt"):
            _, n, r, p, salt_hex, expected_hex = parts
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(expected_hex)
            if (
                (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
                or len(salt) != 16
                or len(expected) != 32
            ):
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=SCRYPT_N,
                r=SCRYPT_R,
                p=SCRYPT_P,
                dklen=32,
            )
        elif algorithm == "pbkdf2_sha256" and len(parts) == 4:
            _, iterations, salt_hex, expected_hex = parts
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(expected_hex)
            if (
                int(iterations) != PBKDF2_ITERATIONS
                or len(salt) != 16
                or len(expected) != 32
            ):
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                PBKDF2_ITERATIONS,
                dklen=32,
            )
        else:
            return False
        return hmac.compare_digest(actual, expected)
    except (AttributeError, TypeError, ValueError):
        return False


@functools.lru_cache(maxsize=1)
def _dummy_admin_password_hash():
    # Use the runtime's preferred KDF so unknown usernames do not take a cheaper path.
    return hash_password(secrets.token_urlsafe(32))


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
        self._dummy_password_hash = _dummy_admin_password_hash()

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
                "SELECT id FROM admins ORDER BY id LIMIT 1"
            ).fetchone()
            if row:
                # The panel has one administrator. Renaming it must not leave an old
                # credential valid, and any credential change revokes every session.
                connection.execute("DELETE FROM sessions")
                connection.execute("DELETE FROM admins WHERE id <> ?", (row["id"],))
                connection.execute(
                    "UPDATE admins SET username = ?, password_hash = ?, updated_at = ? WHERE id = ?",
                    (username, password_hash, now, row["id"]),
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
        password_hash = row["password_hash"] if row else self._dummy_password_hash
        if verify_password(password, password_hash) and row:
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

    def _retry_after(self, address):
        recent = self._recent(address)
        if len(recent) < self.max_attempts:
            return 0
        remaining = recent[0] + self.window_seconds - self.clock()
        whole_seconds = int(remaining)
        return max(1, whole_seconds + (0 if remaining == whole_seconds else 1))

    def retry_after(self, address):
        with self._lock:
            return self._retry_after(address)

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
            return self._retry_after(address)

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

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(
            error,
            (BrokenPipeError, ConnectionAbortedError, ConnectionResetError),
        ):
            return
        super().handle_error(request, client_address)


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
        update_controller=None,
        backup_manager=None,
        restore_controller=None,
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
        self.update_controller = update_controller or UpdateController()
        self.backup_manager = backup_manager
        self.restore_controller = restore_controller or RestoreController()
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
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{}'; connect-src 'self'; "
            "img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'".format(
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

    def _send_html(self, status, body, headers=None):
        encoded = body.encode("utf-8")
        if len(encoded) >= 1024 and self._accepts_gzip():
            encoded = gzip.compress(encoded, compresslevel=5)
            content_encoding = "gzip"
        else:
            content_encoding = ""
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Vary", "Accept-Encoding")
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _accepts_gzip(self):
        for choice in self.headers.get("Accept-Encoding", "").split(","):
            parts = [part.strip() for part in choice.split(";")]
            if not parts or parts[0].lower() != "gzip":
                continue
            quality = 1.0
            for parameter in parts[1:]:
                name, separator, value = parameter.partition("=")
                if separator and name.strip().lower() == "q":
                    try:
                        quality = float(value.strip())
                    except ValueError:
                        quality = 0.0
            return quality > 0
        return False

    def _send_favicon(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(FAVICON_SVG)))
        self.end_headers()
        self.wfile.write(FAVICON_SVG)

    def _send_archive(self, archive_path):
        archive_path = Path(archive_path)
        try:
            size = archive_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="{}"'.format(archive_path.name),
            )
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with archive_path.open("rb") as source:
                shutil.copyfileobj(source, self.wfile, length=64 * 1024)
        finally:
            try:
                archive_path.unlink()
            except FileNotFoundError:
                pass

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
<title>{title} · Hysteria 2 Panel</title><link rel="icon" type="image/svg+xml" href="/favicon.svg"><style>{style}</style></head><body><main>{content}</main>
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
<form class="login-form" method="post" action="/login"><div><label for="username">账号</label><input id="username" name="username" autocomplete="username" required maxlength="64"></div>
<div><label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="1024"></div>
<p class="login-actions"><button type="submit">登录</button></p></form></section>""".format(error=error_html)
        return self._page("登录", content)

    def _dashboard(self, session, sort_by="", sort_order=""):
        try:
            snapshot = self.app.usage_manager.snapshot()
        except Exception:
            LOGGER.exception("stats snapshot failed")
            snapshot = {"traffic": {}, "online": {}, "available": False}
        all_users = self.app.database.list_proxy_users_for_usage()
        sort_by = "traffic" if sort_by == "traffic" else ""
        sort_order = sort_order if sort_order in {"asc", "desc"} else ""
        listed_users = sorted(
            all_users,
            key=lambda item: (item["created_at"], item["id"]),
            reverse=True,
        )
        if sort_by == "traffic" and sort_order:
            listed_users = sorted(
                all_users,
                key=lambda item: item["tx_bytes"] + item["rx_bytes"],
                reverse=sort_order == "desc",
            )
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
                "tcp_congestion_control": "不可用",
                "default_qdisc": "不可用",
            }
        csrf = html.escape(session["csrf_token"], quote=True)
        rows = []
        for user in listed_users:
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
                """<tr data-user-name="{search_name}"><td data-label="名称"><strong>{name}</strong></td>
<td data-label="状态"><span class="status {state_class}">{state}</span></td><td data-label="在线设备">{online} / {device_limit}</td><td data-label="上传 / 下载">{tx} / {rx}</td>
<td class="traffic-cell" data-label="总流量"><progress max="100" value="{percent:.1f}" aria-label="{name} 总流量使用 {percent:.1f}%"></progress><div class="traffic-label"><span>{used} / {limit}</span><span>{percent:.1f}%</span></div></td>
<td data-label="操作"><div class="actions">
<form class="inline" method="post" action="/users/{id}/toggle"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="{action_class}" type="submit">{action}</button></form>
<form class="inline" method="post" action="/users/{id}/rotate" data-confirm="轮换后旧连接地址会立即失效，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="warning" type="submit">轮换密钥</button></form>
<form class="inline" method="post" action="/users/{id}/delete" data-confirm="确定删除用户 {name} 吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="danger" type="submit">删除</button></form>
<form class="inline" method="post" action="/users/{id}/share" data-share-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><input type="hidden" name="inline" value="1"><button class="secondary" type="submit">分享</button></form>
<form class="inline" method="post" action="/users/{id}/reset" data-confirm="确定重置该用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="ghost" type="submit">重置流量</button></form>
</div></td></tr>""".format(
                    name=html.escape(name),
                    search_name=html.escape(name, quote=True),
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
            rows.append('<tr><td colspan="6" class="muted empty-state">暂无用户，请先创建。</td></tr>')
        traffic_sort_next = "asc" if sort_order == "desc" else "desc"
        traffic_sort_mark = "↑" if sort_order == "asc" else "↓" if sort_order == "desc" else "⇅"
        traffic_sort_aria = (
            "ascending" if sort_order == "asc" else "descending" if sort_order == "desc" else "none"
        )
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
            '<div class="rank-row"><span class="rank-number">#{rank}</span><span class="rank-main"><span class="rank-name">{name}</span><span class="rank-traffic">{traffic}</span></span></div>'.format(
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
        update_action = ""
        if update and update["update_available"]:
            update_action = """<form method="post" action="/updates/apply" data-confirm="在线更新会短暂重启面板与 Hysteria 服务，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button success" type="submit">立即更新</button></form>""".format(
                csrf=csrf
            )
        content = """<header class="topbar"><span class="eyebrow brand">HYSTERIA CONTROL CENTER</span><h1>Hysteria 2 用户管理面板</h1><span class="topbar-spacer"></span>
<span class="pill">服务状态 <strong>{service_label}</strong></span><span class="pill">最近刷新 <strong>{refreshed}</strong></span><span class="pill">当前用户 <strong>{total_users}</strong></span>
<button class="secondary topbar-action" type="button" data-dialog-open="migration-dialog">数据迁移</button><form class="logout-form" method="post" action="/logout"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary" type="submit">退出登录</button></form></header>
<section class="metrics" aria-label="服务概览">
<div class="metric"><span>不活跃用户</span><strong>{inactive_users}</strong><small class="muted">上传与下载均为 0</small></div>
<div class="metric"><span>在线设备</span><strong>{online_devices}</strong><small class="muted">按 Hysteria 客户端实例统计</small></div>
<div class="metric"><span>总上传流量</span><strong>{total_tx}</strong><small class="muted">全部用户累计上传</small></div>
<div class="metric"><span>总下载流量</span><strong>{total_rx}</strong><small class="muted">全部用户累计下载</small></div>
</section>
<section class="operations dashboard-trio">
<article class="card"><div class="section-head"><div><h2>服务控制</h2><p class="muted">启停、重启和版本检查集中在这里。</p></div><span class="service-badge{service_class}">{service_label}</span></div>
<div class="button-row"><form method="post" action="/service/start"><input type="hidden" name="csrf" value="{csrf}"><button class="success" type="submit">启动 Hysteria</button></form>
<form method="post" action="/service/restart" data-confirm="确定重启 Hysteria 服务吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="warning" type="submit">重启 Hysteria</button></form>
<form method="post" action="/service/stop" data-confirm="停止后所有连接会中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">停止 Hysteria</button></form><a class="button secondary" href="/">刷新状态</a></div>
<div class="service-details"><div class="detail compact-detail"><span class="muted">流量统计</span><strong class="{stats_class}">{stats}</strong></div><div class="detail compact-detail"><span class="muted">服务端口</span><strong>UDP {port}</strong></div></div>
<div class="service-details version-details"><div class="detail compact-detail bbr-detail"><span class="muted">BBR 状态</span><strong class="ok">Hysteria BBR</strong><small class="muted">standard · 内核 {tcp_cc} / {qdisc}</small></div><div class="detail compact-detail version-panel"><div class="version-row"><div><span class="muted">当前版本</span><strong>v{version}</strong></div><div class="button-row"><form method="post" action="/updates/check"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button" type="submit">检查更新</button></form>{update_action}</div></div><p class="muted">{update_text}</p></div></div></article>
<article class="card"><div class="section-head"><div><h2>系统资源</h2><p class="muted">服务器实时负载与容量。</p></div></div><div class="resource-grid">
<div class="resource"><span class="muted">CPU 使用率</span><strong>{cpu:.1f}%</strong></div><div class="resource"><span class="muted">内存占用</span><strong>{memory:.1f}%</strong><small class="muted">{memory_used} / {memory_total}</small></div>
<div class="resource"><span class="muted">磁盘占用</span><strong>{disk:.1f}%</strong><small class="muted">{disk_used} / {disk_total}</small></div><div class="resource"><span class="muted">运行时长</span><strong>{uptime}</strong></div></div></article>
<article class="card traffic-card"><div class="section-head"><div><h2>高流量用户</h2><p class="muted">当前累计总流量最高的 5 个账号。</p></div></div><div class="rank-list">{rank_rows}</div></article>
</section>
<dialog id="migration-dialog" class="migration-dialog" aria-labelledby="migration-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="migration-title">用户数据迁移</h2><p class="muted">完整备份或恢复节点身份与全部用户数据。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭数据迁移弹窗">×</button></div>
<p class="notice"><strong>重要：</strong>备份包含代理用户、累计流量、签名密钥、证书和私钥，请离线妥善保存。恢复时必须保持节点域名 <code>{public_host}</code> 与 UDP 端口 <code>{port}</code> 不变，旧客户端配置才可继续使用；更换服务器时先通过服务器 IP 登录新面板完成恢复并验证，再切换 DNS。当前面板管理员账号不会被替换。</p>
<div class="migration-grid"><article class="detail"><h3>一键备份</h3><p class="muted">生成经过完整性校验的 ZIP 文件并直接下载。</p><form method="post" action="/backup"><input type="hidden" name="csrf" value="{csrf}"><button type="submit">下载完整备份</button></form></article>
<article class="detail"><h3>一键恢复</h3><p class="muted">上传本面板生成的 ZIP。恢复会短暂重启服务，完成后旧会话失效。</p><form data-restore-form data-csrf="{csrf}"><label for="restore-file">ZIP 备份文件</label><input id="restore-file" type="file" accept=".zip,application/zip" required><p><button class="warning" type="submit">上传并恢复</button></p><p class="muted" data-restore-status role="status"></p></form></article></div></div></dialog>
<dialog id="credentials-dialog" class="migration-dialog credentials-dialog" aria-labelledby="credentials-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="credentials-title" data-credentials-title>节点信息</h2><p class="muted">连接地址包含认证凭据，请只分享给受信任的人。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭节点信息弹窗">×</button></div>
<label for="credentials-uri">Hysteria 2 节点代码</label><textarea id="credentials-uri" rows="5" readonly></textarea><p><button type="button" data-copy-target="credentials-uri">复制节点代码</button></p><p class="notice">关闭弹窗后会刷新当前用户列表。</p></div></dialog>
<dialog id="create-user-dialog" class="migration-dialog create-dialog" aria-labelledby="create-user-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="create-user-title">添加用户</h2><p class="muted">设置用户名称、设备数和总流量限制。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭添加用户弹窗">×</button></div>
<form class="create-grid" method="post" action="/users" data-create-user-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="inline" value="1"><div class="wide"><label for="name">用户名称</label><input id="name" name="name" required maxlength="64" placeholder="例如：Alice 手机" autofocus></div>
<div><label for="device_limit">限制设备数</label><input id="device_limit" name="device_limit" type="number" min="1" max="100" value="3" required></div>
<div><label for="traffic_limit_gb">总流量（GB）</label><input id="traffic_limit_gb" name="traffic_limit_gb" type="number" min="1" max="1048576" value="250" required></div><button type="submit">添加用户</button></form></div></dialog>
<p class="toast" data-page-status role="status" aria-live="polite" hidden></p>
<section class="card"><div class="section-head user-section-head"><div class="user-heading"><h2>用户管理</h2><p class="muted">创建用户并设置并发设备和总流量限制。</p></div>
<div class="user-search"><input id="user-search" type="search" aria-label="搜索用户" placeholder="输入用户名搜索" autocomplete="off" data-user-search></div>
<div class="section-actions"><button type="button" data-dialog-open="create-user-dialog">添加用户</button><form method="post" action="/users/reset-traffic" data-confirm="确定重置所有用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">重置全部流量</button></form></div></div>
<div class="user-tools"><p class="muted search-status" data-search-status role="status" aria-live="polite">共 {user_total} 个用户</p></div>
<div class="table-wrap user-table"><table><thead><tr><th>名称</th><th>状态</th><th>在线设备</th><th>上传 / 下载</th><th aria-sort="{traffic_sort_aria}"><a class="sort-link" href="/?sort=traffic&amp;order={traffic_sort_next}">总流量 {traffic_sort_mark}</a></th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></div></section>""".format(
            port=self.app.hysteria_port,
            public_host=html.escape(self.app.public_host),
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
            update_action=update_action,
            cpu=resources["cpu_percent"],
            memory=resources["memory_percent"],
            memory_used=_human_bytes(resources["memory_used"]),
            memory_total=_human_bytes(resources["memory_total"]),
            disk=resources["disk_percent"],
            disk_used=_human_bytes(resources["disk_used"]),
            disk_total=_human_bytes(resources["disk_total"]),
            uptime=html.escape(resources["uptime"]),
            tcp_cc=html.escape(resources["tcp_congestion_control"]),
            qdisc=html.escape(resources["default_qdisc"]),
            rank_rows=rank_rows,
            rows="".join(rows),
            user_total=len(listed_users),
            traffic_sort_aria=traffic_sort_aria,
            traffic_sort_next=traffic_sort_next,
            traffic_sort_mark=traffic_sort_mark,
        )
        return self._page("控制台", content)

    def _connection_payload(self, credentials):
        return {
            "name": credentials["name"],
            "uri": build_connection_uri(
                self.app.public_host,
                self.app.hysteria_port,
                credentials["token"],
                self.app.pin_sha256,
                self.app.node_name,
            ),
        }

    def _credentials_page(self, session, credentials):
        uri = self._connection_payload(credentials)["uri"]
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
        if path == "/favicon.svg":
            self._send_favicon()
            return
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
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            self._send_html(
                200,
                self._dashboard(
                    session,
                    query.get("sort", [""])[0],
                    query.get("order", [""])[0],
                ),
            )
            return
        self._error_page(404, "页面不存在")

    def do_POST(self):
        path = self._path()
        if path == "/restore":
            self._handle_restore_upload()
            return
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
        if path == "/backup":
            self._handle_backup(session)
            return
        service_match = re.fullmatch(r"/service/(start|stop|restart)", path)
        if service_match:
            self._handle_service_action(session, service_match.group(1))
            return
        if path == "/updates/check":
            self._handle_update_check(session)
            return
        if path == "/updates/apply":
            self._handle_update_apply(session)
            return
        match = re.fullmatch(r"/users/(\d+)/(toggle|rotate|delete|share|reset)", path)
        if match:
            self._handle_user_action(session, int(match.group(1)), match.group(2), form)
            return
        self._error_page(404, "页面不存在")

    def _handle_backup(self, session):
        if self.app.backup_manager is None:
            self._error_page(503, "备份功能尚未配置")
            return
        try:
            with self.app.user_action_lock:
                try:
                    self.app.usage_manager.collect_once()
                except Exception:
                    LOGGER.exception("traffic sync before backup failed")
                archive = self.app.backup_manager.create_archive()
            self._audit_safely(session["username"], "backup_downloaded", "proxy-users")
            self._send_archive(archive)
        except Exception:
            LOGGER.exception("backup creation failed")
            self._error_page(500, "备份生成失败，请检查服务日志")

    def _handle_restore_upload(self):
        session = self._require_session()
        if not session:
            return
        submitted = self.headers.get("X-HY2Panel-CSRF", "")
        if not submitted or not hmac.compare_digest(session["csrf_token"], submitted):
            self._error_page(403, "安全校验失败，请刷新页面后重试")
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/zip":
            self._error_page(400, "仅支持本面板生成的 ZIP 备份文件")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if self.app.backup_manager is None:
            self._error_page(503, "恢复功能尚未配置")
            return
        staged = False
        try:
            with self.app.user_action_lock:
                manifest = self.app.backup_manager.stage_archive(
                    self.rfile, content_length
                )
                staged = True
                self._audit_safely(
                    session["username"], "restore_queued", manifest["createdAt"]
                )
                self.app.restore_controller.queue()
        except BackupValidationError as exc:
            self._error_page(400, str(exc))
            return
        except Exception:
            if staged:
                try:
                    self.app.backup_manager.pending_archive.unlink()
                except FileNotFoundError:
                    pass
            LOGGER.exception("restore queue failed")
            self._error_page(500, "恢复任务启动失败，请检查服务日志")
            return
        content = """<section class="card login"><h1>恢复任务已启动</h1>
<p>面板与 Hysteria 服务将短暂重启。恢复完成后，当前登录会话会失效，请等待约 10 秒后重新登录。</p>
<p class="notice">原节点域名、UDP 端口、签名密钥与证书已通过预检；恢复服务仍会再次独立校验后才替换数据。</p>
<p><a class="button secondary" href="/login">稍后重新登录</a></p></section>"""
        self._send_html(202, self._page("正在恢复", content))

    def _handle_login(self, form):
        address = self.client_address[0]
        retry_after = self.app.rate_limiter.retry_after(address)
        if retry_after:
            self._send_html(
                429,
                self._login_page("尝试次数过多，请 {} 秒后再试".format(retry_after)),
                {"Retry-After": str(retry_after)},
            )
            return
        admin_id = self.app.database.verify_admin(form.get("username", ""), form.get("password", ""))
        if not admin_id:
            retry_after = self.app.rate_limiter.record_failure(address)
            self._audit_safely("anonymous", "login_failed", "admin")
            if retry_after:
                self._audit_safely("anonymous", "login_locked", "admin")
                self._send_html(
                    429,
                    self._login_page("尝试次数过多，请 {} 秒后再试".format(retry_after)),
                    {"Retry-After": str(retry_after)},
                )
                return
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
        inline = form.get("inline") == "1"
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
            if inline:
                self.send_json(400, {"error": str(exc)})
                return
            self._error_page(400, str(exc))
            return
        self._audit_safely(session["username"], "proxy_user_created", credentials["name"])
        if inline:
            self.send_json(201, self._connection_payload(credentials))
            return
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
                        if form.get("inline") == "1":
                            self.send_json(
                                409,
                                {"error": "该用户来自旧版本，请先轮换密钥后再分享"},
                            )
                            return
                        self._error_page(
                            409,
                            "该用户来自旧版本，原密钥不可逆保存；请先点击轮换密钥，再使用分享功能",
                        )
                        return
                    self._audit_safely(session["username"], "proxy_link_shared", user["name"])
                    credentials = {"id": user["id"], "name": user["name"], "token": token}
                    if form.get("inline") == "1":
                        self.send_json(200, self._connection_payload(credentials))
                        return
                    self._send_html(
                        200,
                        self._credentials_page(session, credentials),
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

    def _handle_update_apply(self, session):
        if not self.app.update_result or not self.app.update_result.get("update_available"):
            self._error_page(409, "请先检查更新并确认存在新版本")
            return
        try:
            self.app.update_controller.queue()
            self._audit_safely(
                session["username"],
                "panel_update_queued",
                self.app.update_result["latest"],
            )
        except Exception:
            LOGGER.exception("update queue failed")
            self._error_page(500, "在线更新任务启动失败，请检查服务日志")
            return
        content = """<section class="card login"><h1>在线更新任务已启动</h1>
<p>系统会重新核验最新正式版本，建立升级前备份并保留用户、节点参数、签名密钥、证书和管理员账号。</p>
<p class="notice">面板与 Hysteria 服务会短暂重启。请等待约 30 秒后刷新；失败原因与升级前备份位置会保留在更新服务日志中。</p>
<p><a class="button secondary" href="/">稍后刷新</a></p></section>"""
        self._send_html(202, self._page("正在更新", content))


def make_panel_server(address, application):
    server = BoundedThreadingHTTPServer(address, PanelHandler)
    server.application = application
    return server


class HysteriaStatsClient:
    def __init__(self, base_url, secret, timeout=2):
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Hysteria stats API URL is invalid") from exc
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Hysteria stats API must use plaintext loopback HTTP")
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
        # The constructor restricts the URL to loopback HTTP.
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
            if response.status != 200:
                raise RuntimeError("Hysteria stats API returned {}".format(response.status))
            raw_body = response.read(MAX_STATS_RESPONSE_BYTES + 1)
        if len(raw_body) > MAX_STATS_RESPONSE_BYTES:
            raise ValueError("Hysteria stats API response is too large")
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
        self.kick_many([name])

    def kick_many(self, names):
        names = list(names)
        if names:
            self._request("/kick", names)


class UsageManager:
    def __init__(self, database, stats_client, pending_ttl=5, clock=time.monotonic):
        self.database = database
        self.stats_client = stats_client
        self.pending_ttl = max(1, int(pending_ttl))
        self.clock = clock
        self.lock = threading.Lock()
        self.pending = {}
        self.last_online = {}

    def _collect_locked(self):
        traffic = self.stats_client.collect_and_clear()
        self.database.add_traffic(traffic)
        return traffic

    def _blocked_online_names_locked(self):
        users = {
            user["name"]: user for user in self.database.list_proxy_users_for_usage()
        }
        online = self.stats_client.online()
        blocked = []
        for name, count in online.items():
            user = users.get(name)
            if count > 0 and (
                not user
                or not user["enabled"]
                or user["tx_bytes"] + user["rx_bytes"] >= user["traffic_limit_bytes"]
            ):
                blocked.append(name)
        return sorted(blocked)

    def collect_once(self):
        with self.lock:
            traffic = self._collect_locked()
            try:
                blocked = self._blocked_online_names_locked()
            except Exception:
                LOGGER.exception("online reconciliation failed during traffic sync")
                return traffic
            self.stats_client.kick_many(blocked)
            return traffic

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
            self.pending.pop(user["name"], None)

    def reset_all(self):
        with self.lock:
            self._collect_locked()
            self.database.reset_all_traffic()

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
            raise RuntimeError("update service could not be started")


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
        if not isinstance(payload, dict):
            raise ValueError("release response is invalid")
        if (
            payload.get("draft", False) is not False
            or payload.get("prerelease", False) is not False
        ):
            raise ValueError("release is not a formal release")
        latest = payload.get("tag_name")
        if not isinstance(latest, str):
            raise ValueError("release response is invalid")
        latest_tuple = self._version_tuple(latest)
        return {
            "current": "v{}".format(self.current_version.lstrip("v")),
            "latest": "v{}.{}.{}".format(*latest_tuple),
            "update_available": latest_tuple > self._version_tuple(self.current_version),
            "url": "https://github.com/Elegying/Hysteria2-panel/releases/latest",
        }


class UpdateInstaller:
    INSTALLER_URL = (
        "https://raw.githubusercontent.com/Elegying/Hysteria2-panel/{tag}/install.sh"
    )
    MAX_INSTALLER_BYTES = 512 * 1024
    SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    def __init__(
        self,
        current_version=PANEL_VERSION,
        opener=urllib.request.urlopen,
        runner=subprocess.run,
    ):
        self.current_version = current_version
        self.opener = opener
        self.runner = runner

    def _download_installer(self, tag):
        request = urllib.request.Request(
            self.INSTALLER_URL.format(tag=tag),
            headers={"User-Agent": "Hysteria2-panel"},
        )
        with self.opener(request, timeout=10) as response:
            body = response.read(self.MAX_INSTALLER_BYTES + 1)
        if len(body) > self.MAX_INSTALLER_BYTES:
            raise ValueError("release installer is too large")
        try:
            source = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("release installer is not UTF-8") from exc
        if not source.startswith(("#!/usr/bin/env bash\n", "#!/bin/bash\n")):
            raise ValueError("release installer header is invalid")
        latest = re.search(r'^PANEL_VERSION="(\d+\.\d+\.\d+)"$', source, re.MULTILINE)
        if not latest:
            raise ValueError("release installer version is invalid")
        return body, latest.group(1)

    def apply(self):
        release = UpdateChecker(self.current_version, opener=self.opener).check()
        if not release["update_available"]:
            return {
                "current": release["current"],
                "latest": release["latest"],
                "updated": False,
            }
        tag = release["latest"]
        installer, embedded_version = self._download_installer(tag)
        if "v{}".format(embedded_version) != tag:
            raise ValueError("release installer version does not match release tag")
        with tempfile.TemporaryDirectory(prefix="hysteria2-panel-update.") as directory:
            installer_path = Path(directory) / "install.sh"
            installer_path.write_bytes(installer)
            installer_path.chmod(0o700)
            syntax = self.runner(
                ["/bin/bash", "-n", str(installer_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if syntax.returncode != 0:
                raise ValueError("release installer syntax is invalid")
            environment = {
                "PATH": self.SAFE_PATH,
                "LANG": "C.UTF-8",
                "HY2PANEL_AUTO_UPDATE": "1",
                "PANEL_REF": tag,
            }
            # The interpreter is fixed; the script passed the release and syntax checks above.
            result = self.runner(
                ["/bin/bash", str(installer_path)],
                env=environment,
                text=True,
                timeout=900,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError("online update installer failed")
        return {
            "current": release["current"],
            "latest": release["latest"],
            "updated": True,
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
        panel_scheme = mapping.get("HY2PANEL_PANEL_SCHEME", "http").strip().lower()
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
            # Remote panel access is an explicit deployment feature.
            panel_host=mapping.get("HY2PANEL_PANEL_HOST", "0.0.0.0"),  # nosec B104
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


def run_supervised_services(panel_server, auth_server, usage_manager, panel_scheme):
    stop_event = threading.Event()
    failures = queue.Queue()

    def worker(name, target):
        try:
            target()
        except BaseException as exc:
            failures.put((name, exc))
        else:
            failures.put((name, None))

    workers = [
        threading.Thread(
            target=worker,
            args=("panel-{}".format(panel_scheme), panel_server.serve_forever),
            name="panel-{}".format(panel_scheme),
            daemon=True,
        ),
        threading.Thread(
            target=worker,
            args=("internal-auth", auth_server.serve_forever),
            name="internal-auth",
            daemon=True,
        ),
        threading.Thread(
            target=worker,
            args=("traffic-collector", lambda: usage_manager.run_collector(stop_event)),
            name="traffic-collector",
            daemon=True,
        ),
    ]
    for thread in workers:
        thread.start()
    try:
        failed_worker, error = failures.get()
        message = "{} worker exited unexpectedly".format(failed_worker)
        if error is None:
            raise RuntimeError(message)
        raise RuntimeError(message) from error
    finally:
        stop_event.set()
        for server in (panel_server, auth_server):
            try:
                server.shutdown()
            except Exception:
                LOGGER.exception("local service shutdown failed")
        for thread in workers:
            thread.join(timeout=5)
        for server in (panel_server, auth_server):
            try:
                server.server_close()
            except Exception:
                LOGGER.exception("local service close failed")


def run_service(settings):
    database = Database(settings.database_path, settings.hmac_key)
    database.initialize()
    if not database.has_admin():
        raise RuntimeError("no administrator exists; run init-admin first")
    stats_client = HysteriaStatsClient(settings.stats_url, settings.stats_secret)
    usage_manager = UsageManager(database, stats_client)
    backup_manager = BackupManager(
        database=database,
        hmac_key=settings.hmac_key,
        tls_cert=settings.tls_cert,
        tls_key=settings.tls_key,
        public_host=settings.public_host,
        hysteria_port=settings.hysteria_port,
        node_name=settings.node_name,
        work_dir=settings.database_path.parent / "backup-restore",
    )
    application = PanelApplication(
        database=database,
        public_host=settings.public_host,
        hysteria_port=settings.hysteria_port,
        pin_sha256=settings.cert_pin,
        stats_client=stats_client,
        node_name=settings.node_name,
        secure_cookies=settings.panel_scheme == "https",
        usage_manager=usage_manager,
        backup_manager=backup_manager,
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
    run_supervised_services(
        panel_server,
        auth_server,
        usage_manager,
        panel_scheme=settings.panel_scheme,
    )


def restore_pending(settings):
    manager = BackupManager(
        database=Database(settings.database_path, settings.hmac_key),
        hmac_key=settings.hmac_key,
        tls_cert=settings.tls_cert,
        tls_key=settings.tls_key,
        public_host=settings.public_host,
        hysteria_port=settings.hysteria_port,
        node_name=settings.node_name,
        work_dir=settings.database_path.parent / "backup-restore",
    )
    result = manager.apply_pending_archive(
        env_file=Path("/etc/hysteria2-panel/panel.env"),
        backup_root=Path("/var/backups/hysteria2-panel"),
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "proxyUserCount": result["proxyUserCount"],
                "automaticBackup": result["automaticBackup"],
            },
            separators=(",", ":"),
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hysteria 2 multi-user panel")
    subcommands = parser.add_subparsers(dest="command", required=True)
    init_parser = subcommands.add_parser("init-admin", help="create or update the administrator")
    init_parser.add_argument("--username", required=True)
    init_parser.add_argument("--if-missing", action="store_true")
    subcommands.add_parser("serve", help="run the authentication service and panel")
    subcommands.add_parser("restore-pending", help="apply the staged backup as root")
    subcommands.add_parser("apply-update", help="install the latest formal release as root")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_mapping(os.environ)
        if args.command == "init-admin":
            password = os.environ.get("HY2PANEL_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
            changed = initialize_admin(settings, args.username, password, args.if_missing)
            print(json.dumps({"status": "ok", "adminCreated": changed}, separators=(",", ":")))
            return 0
        if args.command == "restore-pending":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("restore-pending must run as root")
            restore_pending(settings)
            return 0
        if args.command == "apply-update":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("apply-update must run as root")
            result = UpdateInstaller().apply()
            print(json.dumps(result, separators=(",", ":")))
            return 0
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        run_service(settings)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print("hysteria2-panel: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
