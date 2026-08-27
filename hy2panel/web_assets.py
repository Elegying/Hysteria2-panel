"""Static browser assets kept outside the application entrypoint."""

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
.button-row,.actions{display:flex;flex-wrap:wrap;gap:9px}button,.button{display:inline-block;border:1px solid transparent;border-radius:10px;background:var(--accent);color:#fff;padding:10px 15px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer;transition:filter .15s ease,transform .15s ease}button:hover,.button:hover{filter:brightness(1.08);transform:translateY(-1px)}button:active,.button:active{transform:none}button.secondary,.button.secondary{background:#1b2c40;border-color:#34495f}button.success{background:var(--success);color:#082016}button.warning{background:var(--warning);color:#251a05}button.danger{background:var(--danger)}button.ghost{background:transparent;border-color:#3a526b;color:#dce8f8}form.inline{display:inline}.system-actions{flex:0 0 auto}.system-actions button{padding:8px 11px}
.resource-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.resource,.detail{background:var(--surface-2);border:1px solid #283b50;border-radius:14px;padding:18px}.resource{padding:12px}.resource strong{font-size:18px;margin-top:4px}.resource small{font-size:11px}.resource strong,.detail strong{display:block}.certificate-resource{grid-column:1/-1;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:baseline;gap:8px 12px}.certificate-resource strong{margin-top:0}.certificate-resource small{white-space:nowrap}.service-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.compact-detail{padding:12px}.compact-detail strong{font-size:18px;margin-top:4px}.port-detail{display:flex;align-items:center;justify-content:space-between;gap:12px}.port-detail>div strong{white-space:nowrap}.egress-control{display:grid;justify-items:end;gap:3px;margin:0}.egress-state{color:var(--muted);font-size:11px;font-weight:750;white-space:nowrap}.egress-state.on{color:var(--success)}.egress-state.unknown{color:var(--warning)}.egress-switch{display:inline-flex;align-items:center;gap:6px;padding:5px 7px;background:#1b2c40;border-color:#40566f;border-radius:999px;font-size:11px}.egress-switch.on{background:#123833;border-color:#26745d;color:#caffec}.egress-switch.unknown{border-color:#8b6b30}.egress-switch-track{position:relative;width:30px;height:18px;border-radius:999px;background:#52647a;box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}.egress-switch-track>span{position:absolute;top:3px;left:3px;width:12px;height:12px;border-radius:50%;background:#fff;transition:transform .15s ease}.egress-switch.on .egress-switch-track{background:var(--success)}.egress-switch.on .egress-switch-track>span{transform:translateX(12px)}.egress-switch-action{min-width:22px;text-align:center}.bbr-detail strong,.version-row strong{font-size:18px;margin-top:4px}.bbr-detail small{display:block;font-size:11px;margin-top:3px}.version-panel>p{font-size:12px;margin:4px 0 0}.version-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.compact-button{padding:8px 11px}.notice{padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#10233a;color:#c7d6ea}
.rank-list{display:grid;gap:6px}.rank-row{display:grid;grid-template-columns:28px minmax(0,1fr);align-items:center;gap:7px;padding:7px 9px;background:var(--surface-2);border:1px solid #283b50;border-radius:10px}.rank-main{display:flex;align-items:baseline;gap:8px;min-width:0}.rank-number{color:var(--accent);font-weight:800}.rank-name{font-weight:700;overflow:hidden;text-overflow:ellipsis}.rank-traffic{color:var(--muted);font-size:12px;white-space:nowrap}
.create-grid{display:grid;grid-template-columns:2fr 1fr 1fr auto;align-items:end;gap:12px;margin-bottom:22px}.section-actions,.user-tools{display:flex;align-items:center;gap:9px}.user-section-head{display:flex;align-items:center;flex-wrap:wrap}.user-heading{flex:1 1 240px}.user-section-head .section-actions{flex:0 0 auto}.user-tools{justify-content:space-between;margin-bottom:14px}.user-filters{display:grid;grid-template-columns:minmax(220px,2fr) repeat(3,minmax(120px,1fr)) auto;align-items:end;gap:9px;flex:1}.user-filters label{margin-bottom:4px;font-size:12px;color:var(--muted)}.user-filters button{padding:10px 12px}.search-status{margin:0;white-space:nowrap}.filter-empty{margin:0 0 14px;padding:11px 14px;border:1px dashed #3a526b;border-radius:10px;text-align:center}label{display:block;font-weight:650;margin-bottom:6px}input,textarea,select{width:100%;padding:11px 13px;border:1px solid #3a4d63;border-radius:9px;background:#101f31;color:var(--text);font:inherit}input:focus,textarea:focus,select:focus,button:focus-visible,.button:focus-visible{outline:3px solid rgba(95,145,247,.38);outline-offset:2px}button:disabled{cursor:wait;opacity:.65}.table-wrap{overflow-x:auto;scrollbar-gutter:stable}table{width:100%;border-collapse:separate;border-spacing:0;min-width:1050px;font-variant-numeric:tabular-nums}th,td{padding:13px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}th{color:var(--muted);font-size:13px;white-space:nowrap}.user-table th{position:sticky;top:0;z-index:2;background:var(--surface);box-shadow:0 1px 0 var(--line)}.user-table tbody tr{transition:background-color .15s ease}.user-table tbody tr:hover{background:#0f2135}.user-table tr[data-over-device-limit="1"]{background:rgba(255,102,117,.07)}.over-limit-name{color:var(--danger)}.limit-alert{display:block;margin-top:2px;color:var(--danger);font-size:11px;font-weight:700}.sort-link{color:inherit;text-decoration:none}.sort-link:hover{text-decoration:underline}.status{font-weight:750}.enabled{color:var(--success)}.disabled{color:var(--danger)}progress{width:150px;height:10px;accent-color:var(--accent)}.traffic-cell{min-width:190px}.traffic-label{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--muted);margin-top:4px}.actions{min-width:420px}.user-table tr[hidden]{display:none}.update-state{margin-top:6px}.update-state[data-state="failed"]{color:var(--danger)}.update-state[data-state="running"],.update-state[data-state="queued"]{color:var(--warning)}.update-state[data-state="success"]{color:var(--success)}
.checkbox-field{display:flex;align-items:flex-start;gap:10px;margin:0;padding:12px;border:1px solid #3a4d63;border-radius:10px;background:#101f31}.checkbox-field input{width:auto;margin:4px 0 0;flex:0 0 auto}.checkbox-field span{font-weight:650}.checkbox-field small{display:block;margin-top:3px;font-weight:400}
.login{width:min(430px,100%);margin:12vh auto}.login-form{display:grid;gap:12px}.login-actions{margin:4px 0 0}.login-actions button{min-width:110px}.copy-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px;margin-bottom:16px}.error{color:var(--danger)}code{word-break:break-all}
.migration-dialog{width:min(820px,calc(100% - 32px));max-height:min(86vh,760px);padding:0;border:1px solid #35506d;border-radius:18px;background:var(--surface);color:var(--text);box-shadow:0 24px 80px rgba(0,0,0,.55);overflow:auto}.migration-dialog::backdrop{background:rgba(1,8,18,.78);backdrop-filter:blur(4px)}.credentials-dialog{width:min(680px,calc(100% - 32px))}.create-dialog{width:min(560px,calc(100% - 32px))}.create-dialog .create-grid{grid-template-columns:1fr 1fr;margin-bottom:0}.create-dialog .wide,.create-dialog .create-grid>button{grid-column:1/-1}.credentials-dialog textarea{min-height:118px}.qr-panel{display:grid;justify-items:center;gap:8px;margin:16px 0}.qr-panel[hidden]{display:none}.qr-canvas{display:block;width:min(100%,320px);height:auto;border:10px solid #fff;border-radius:8px;background:#fff;image-rendering:pixelated}.credential-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:14px 0}.credential-actions button{width:100%}.dialog-shell{padding:22px}.dialog-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:16px}.dialog-head h2{margin-bottom:4px}.dialog-close{flex:0 0 auto;width:40px;height:40px;padding:0;border-radius:50%;background:#1b2c40;border-color:#34495f;font-size:24px;line-height:1}.migration-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.migration-grid .detail{height:100%}.migration-grid p:last-child{margin-bottom:0}.toast{position:fixed;right:18px;bottom:18px;z-index:20;max-width:min(420px,calc(100% - 36px));margin:0;padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#102846;box-shadow:0 12px 36px rgba(0,0,0,.4)}.toast.error{border-color:#8a3844;color:#ffd5da}.toast[hidden]{display:none}
.node-onboarding-dialog{width:min(900px,calc(100% - 32px))}.node-enrollment-grid{display:grid;grid-template-columns:minmax(190px,1fr) minmax(190px,1fr) minmax(120px,.55fr) auto;align-items:end;gap:10px;margin:16px 0}.enrollment-result{margin:16px 0;padding:14px;border:1px solid #375170;border-radius:12px;background:#0d2035}.enrollment-result[hidden]{display:none}.enrollment-result textarea{min-height:220px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}.node-list-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-top:20px}.node-list{display:grid;gap:8px}.node-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px;padding:11px 12px;border:1px solid #283b50;border-radius:11px;background:var(--surface-2)}.node-row>div:first-child{min-width:0}.node-row strong,.node-row small{display:block}.node-row small{margin-top:2px;overflow-wrap:anywhere}.node-row>span{font-weight:750;white-space:nowrap}.node-actions{display:flex;flex-wrap:wrap;gap:8px}.node-actions form{margin:0}
@media(min-width:641px) and (max-width:1300px){.brand{display:none}.topbar h1{white-space:nowrap}}
@media(max-width:1050px){.topbar{flex-wrap:wrap}.topbar-spacer{display:none}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.operations{grid-template-columns:1fr}.create-grid{grid-template-columns:1fr 1fr}.create-grid .wide{grid-column:1/-1}.node-enrollment-grid{grid-template-columns:1fr 1fr}.node-enrollment-grid>button{width:100%}.user-filters{grid-template-columns:minmax(200px,2fr) repeat(3,minmax(105px,1fr)) auto}}
@media(max-width:640px){.certificate-resource{grid-template-columns:auto minmax(0,1fr)}.certificate-resource small{grid-column:1/-1}main{width:calc(100% - 16px);margin:8px auto 24px}.topbar{padding:16px;border-radius:16px;align-items:flex-start;gap:9px}.topbar h1{font-size:23px;width:100%;order:-2;margin:0 0 5px}.brand{display:none}.pill{flex:1 1 calc(50% - 5px);padding:8px 10px;font-size:12px;text-align:center}.topbar-action,.logout-form{flex:1 1 calc(50% - 5px)}.topbar-action,.logout-form button{width:100%}.metrics{grid-template-columns:1fr 1fr;gap:8px}.metric{padding:14px}.metric strong{font-size:20px}.metric small{font-size:12px}.card{padding:16px;border-radius:14px}.primary-details{grid-template-columns:1fr}.create-grid,.migration-grid,.create-dialog .create-grid,.node-enrollment-grid{grid-template-columns:1fr}.node-enrollment-grid>button{width:100%}.node-list-head{align-items:flex-start;flex-direction:column;gap:2px}.node-row{grid-template-columns:minmax(0,1fr) auto}.node-actions{grid-column:1/-1;display:grid}.node-actions form,.node-actions button{width:100%}.section-head{flex-direction:column;padding-bottom:13px}.user-heading{flex-basis:auto}.section-head>form,.section-head>form button,.create-grid>button{width:100%}.system-actions{width:100%}.section-actions{display:grid;grid-template-columns:1fr 1fr;width:100%}.section-actions form,.section-actions button{width:100%}.section-actions form{grid-column:1/-1}.user-tools{align-items:stretch;flex-direction:column}.user-filters{grid-template-columns:1fr 1fr;width:100%}.user-filters .user-search{grid-column:1/-1}.user-filters button{width:100%}.search-status{white-space:normal}.button-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.button-row form,.button-row button,.button-row .button{width:100%}.bbr-detail,.version-panel{padding:10px}.version-row{gap:6px}.compact-button{padding:7px 6px;font-size:12px;white-space:nowrap}.login{margin:8vh auto}.login-actions button{width:100%}.copy-grid{grid-template-columns:1fr}.copy-grid button{width:100%}.migration-dialog{width:calc(100% - 12px);max-height:calc(100dvh - 12px);border-radius:14px}.dialog-shell{padding:16px}.dialog-head{position:sticky;top:-16px;z-index:1;background:var(--surface);padding-top:16px}.qr-canvas{width:min(100%,288px)}.user-table{overflow:visible}.user-table table,.user-table tbody{display:block;width:100%;min-width:0}.user-table thead{display:none}.user-table tr{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px 10px;margin-bottom:8px;padding:10px;background:var(--surface-2);border:1px solid #283b50;border-radius:12px}.user-table td{display:block;width:auto;min-width:0;padding:0;border-bottom:0}.user-table td:nth-child(1){grid-column:1}.user-table td:nth-child(2){grid-column:2}.user-table td:nth-child(3){grid-column:3}.user-table td:nth-child(4){grid-column:1;font-size:11px;color:var(--muted)}.user-table td:nth-child(5){grid-column:2/4}.user-table td:nth-child(6){grid-column:1/-1;padding-top:2px}.user-table .traffic-cell{min-width:0}.user-table .traffic-label{gap:5px;font-size:10px}.user-table progress{display:block;width:100%;height:8px}.user-table .actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;min-width:0}.user-table .actions form,.user-table .actions button{width:100%;min-width:0}.user-table .actions button{padding:7px 3px;font-size:11px;white-space:nowrap}.user-table .empty-state{grid-column:1/-1!important;text-align:center}.toast{right:8px;bottom:8px;max-width:calc(100% - 16px)}}
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
function clearCredentialsQr() {
  const panel = document.querySelector('[data-qr-panel]');
  const canvas = document.getElementById('credentials-qr');
  const saveButton = document.querySelector('[data-save-qr]');
  if (panel) panel.hidden = true;
  if (saveButton) saveButton.hidden = true;
  if (canvas) {
    canvas.width = 0;
    canvas.height = 0;
    canvas.setAttribute('aria-label', 'Hysteria 2 节点配置二维码');
  }
}
function drawCredentialsQr(rows, name) {
  const size = Array.isArray(rows) ? rows.length : 0;
  const valid = size >= 21 && size <= 177 && (size - 21) % 4 === 0 &&
    rows.every(function(row) {
      return typeof row === 'string' && row.length === size && /^[01]+$/.test(row);
    });
  if (!valid) throw new Error('二维码数据无效，请刷新页面后重试');
  const canvas = document.getElementById('credentials-qr');
  const panel = document.querySelector('[data-qr-panel]');
  const saveButton = document.querySelector('[data-save-qr]');
  if (!canvas || !panel || !saveButton) throw new Error('二维码组件加载失败');
  const quiet = 4;
  const scale = Math.max(3, Math.floor(360 / (size + quiet * 2)));
  canvas.width = (size + quiet * 2) * scale;
  canvas.height = canvas.width;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('浏览器无法绘制二维码');
  context.imageSmoothingEnabled = false;
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#000000';
  rows.forEach(function(row, y) {
    for (let x = 0; x < size; x += 1) {
      if (row[x] === '1') context.fillRect((x + quiet) * scale, (y + quiet) * scale, scale, scale);
    }
  });
  canvas.setAttribute('aria-label', String(name || '用户') + ' 的 Hysteria 2 节点配置二维码');
  panel.hidden = false;
  saveButton.hidden = false;
}
function showCredentials(payload, withQr, refreshOnClose) {
  if (!payload || typeof payload.uri !== 'string' || !payload.uri.startsWith('hysteria2://')) {
    throw new Error('节点代码响应无效');
  }
  const dialog = document.getElementById('credentials-dialog');
  if (!dialog) throw new Error('节点信息弹窗加载失败');
  clearCredentialsQr();
  if (withQr) drawCredentialsQr(payload.qr, payload.name);
  dialog.querySelector('[data-credentials-title]').textContent = String(payload.name || '用户') + ' 的节点信息';
  dialog.querySelector('#credentials-uri').value = payload.uri;
  dialog.querySelector('[data-credentials-notice]').textContent = withQr
    ? '二维码和节点代码都包含认证凭据，请只保存到受信任的设备。'
    : '关闭弹窗后会刷新当前用户列表。';
  dialog.dataset.refreshOnClose = refreshOnClose ? '1' : '0';
  dialog.showModal();
}
function syncEditUserForm() {
  const form = document.querySelector('[data-edit-user-form]');
  if (!form) return;
  const selector = form.querySelector('[data-edit-user-select]');
  const option = selector && selector.options[selector.selectedIndex];
  if (!option || !option.value) return;
  form.action = '/users/' + encodeURIComponent(option.value) + '/edit';
  form.querySelector('[name="generation"]').value = option.dataset.generation;
  form.querySelector('[name="device_limit"]').value = option.dataset.deviceLimit;
  form.querySelector('[name="traffic_limit_gb"]').value = option.dataset.trafficLimitGb;
  form.querySelector('[name="allow_udp_443"]').checked = option.dataset.allowUdp443 === '1';
}
function renderUpdateStatus(payload) {
  const status = document.querySelector('[data-update-status]');
  if (!status) return;
  status.dataset.state = payload.state || 'idle';
  status.textContent = payload.message || '正在读取更新状态…';
}
async function pollUpdateStatus(button, deadline) {
  try {
    const response = await fetch('/updates/status', {
      headers: {'Accept': 'application/json'},
      credentials: 'same-origin',
      cache: 'no-store'
    });
    if (!response.ok) throw new Error('状态读取失败');
    const payload = await response.json();
    renderUpdateStatus(payload);
    if (payload.state === 'success') {
      window.setTimeout(function() { window.location.reload(); }, 900);
      return;
    }
    if (payload.state === 'failed') {
      button.disabled = false;
      button.textContent = '重新更新';
      notify(payload.message || '在线更新失败', true);
      return;
    }
  } catch (_) {
    renderUpdateStatus({state: 'running', message: '面板正在重启，等待恢复连接…'});
  }
  if (Date.now() >= deadline) {
    button.disabled = false;
    button.textContent = '检查状态';
    renderUpdateStatus({state: 'failed', message: '等待更新超时，请刷新页面查看当前版本'});
    return;
  }
  window.setTimeout(function() { pollUpdateStatus(button, deadline); }, 1500);
}
document.addEventListener('click', function(event) {
  const opener = event.target.closest('[data-dialog-open]');
  if (opener) {
    if (opener.dataset.dialogOpen === 'edit-user-dialog') syncEditUserForm();
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
document.addEventListener('click', function(event) {
  const button = event.target.closest('[data-save-qr]');
  if (!button) return;
  const canvas = document.getElementById('credentials-qr');
  if (!canvas || !canvas.width) { notify('二维码尚未生成', true); return; }
  button.disabled = true;
  canvas.toBlob(function(blob) {
    if (!blob) {
      button.disabled = false;
      notify('二维码保存失败，请重试', true);
      return;
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'hysteria2-node-qr.png';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
    button.disabled = false;
    notify('二维码 PNG 已保存', false);
  }, 'image/png');
});
document.addEventListener('submit', function(event) {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
document.addEventListener('submit', function(event) {
  const form = event.target.closest('[data-egress-form]');
  if (!form || event.defaultPrevented) return;
  const button = form.querySelector('button[type="submit"]');
  const state = form.querySelector('[data-egress-state]');
  if (button) button.disabled = true;
  if (state) state.textContent = '正在切换…';
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
  const form = event.target.closest('[data-qr-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '生成中…';
  try {
    const payload = await submitInlineForm(form);
    showCredentials(payload, true, false);
  } catch (error) {
    notify(error.message || '二维码生成失败，请重试', true);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-edit-user-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = '保存中…';
  try {
    const payload = await submitInlineForm(form);
    notify(payload.name + ' 的用户设置已更新', false);
    const dialog = form.closest('dialog');
    if (dialog) dialog.close();
    window.setTimeout(function() { window.location.reload(); }, 700);
  } catch (error) {
    notify(error.message || '用户设置更新失败，请重试', true);
  } finally {
    button.disabled = false;
    button.textContent = '保存修改';
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-update-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = '正在排队…';
  try {
    const payload = await submitInlineForm(form);
    renderUpdateStatus(payload);
    button.textContent = '正在更新…';
    pollUpdateStatus(button, Date.now() + 180000);
  } catch (error) {
    button.disabled = false;
    button.textContent = '立即更新';
    notify(error.message || '在线更新任务启动失败', true);
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
    form.reset();
    const createDialog = form.closest('dialog');
    if (createDialog) createDialog.close();
    showCredentials(payload, false, true);
  } catch (error) {
    notify(error.message || '添加用户失败，请重试', true);
  } finally {
    button.disabled = false;
    button.textContent = '添加用户';
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-node-enrollment-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  const result = document.querySelector('[data-node-enrollment-result]');
  const code = document.getElementById('node-deployment-code');
  const expiry = document.querySelector('[data-node-enrollment-expiry]');
  button.disabled = true;
  button.textContent = '生成中…';
  try {
    const payload = await submitInlineForm(form);
    if (!payload || typeof payload.deploymentCommand !== 'string' || !payload.deploymentCommand.startsWith('set -euo pipefail')) {
      throw new Error('部署代码响应无效');
    }
    code.value = payload.deploymentCommand;
    expiry.textContent = '对接码将在 ' + new Date(Number(payload.expiresAt) * 1000).toLocaleTimeString() + ' 过期，且只能使用一次。';
    result.hidden = false;
    code.focus();
    notify('一键部署代码已生成，请在有效期内使用', false);
  } catch (error) {
    notify(error.message || '生成部署代码失败，请重试', true);
  } finally {
    button.disabled = false;
    button.textContent = '生成部署代码';
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
  const refresh = credentialsDialog.dataset.refreshOnClose === '1';
  credentialsDialog.querySelector('#credentials-uri').value = '';
  clearCredentialsQr();
  if (refresh) window.location.href = '/';
});
const nodeOnboardingDialog = document.getElementById('node-onboarding-dialog');
if (nodeOnboardingDialog) nodeOnboardingDialog.addEventListener('close', function() {
  const code = document.getElementById('node-deployment-code');
  const result = document.querySelector('[data-node-enrollment-result]');
  const expiry = document.querySelector('[data-node-enrollment-expiry]');
  if (code) code.value = '';
  if (expiry) expiry.textContent = '';
  if (result) result.hidden = true;
});
const editUserSelect = document.querySelector('[data-edit-user-select]');
if (editUserSelect) {
  editUserSelect.addEventListener('change', syncEditUserForm);
  syncEditUserForm();
}
const filterForm = document.querySelector('[data-user-filters]');
if (filterForm) {
  const userSearch = filterForm.querySelector('[data-user-search]');
  const statusFilter = filterForm.querySelector('[data-status-filter]');
  const onlineFilter = filterForm.querySelector('[data-online-filter]');
  const udp443Filter = filterForm.querySelector('[data-udp443-filter]');
  const clearFilters = filterForm.querySelector('[data-clear-user-filters]');
  const userRows = Array.from(document.querySelectorAll('[data-user-name]'));
  const searchStatus = document.querySelector('[data-search-status]');
  const filterEmpty = document.querySelector('[data-filter-empty]');
  let filterFrame = 0;
  function syncFilterUrl() {
    const params = new URLSearchParams(new FormData(filterForm));
    const url = new URL(window.location.href);
    ['q', 'status', 'online', 'udp443'].forEach(function(name) {
      const value = params.get(name);
      if (value) url.searchParams.set(name, value);
      else url.searchParams.delete(name);
    });
    history.replaceState(null, '', url.pathname + url.search);
    document.querySelectorAll('.sort-link').forEach(function(link) {
      const sortUrl = new URL(link.href);
      ['q', 'status', 'online', 'udp443'].forEach(function(name) {
        const value = params.get(name);
        if (value) sortUrl.searchParams.set(name, value);
        else sortUrl.searchParams.delete(name);
      });
      link.href = sortUrl.pathname + sortUrl.search;
    });
  }
  function filterUsers() {
    const query = userSearch.value.trim().toLocaleLowerCase();
    let visible = 0;
    userRows.forEach(function(row) {
      const online = Number(row.dataset.online || '0');
      const matchesName = row.dataset.userName.toLocaleLowerCase().includes(query);
      const matchesStatus = !statusFilter.value || row.dataset.enabled === (statusFilter.value === 'enabled' ? '1' : '0');
      const matchesOnline = !onlineFilter.value || (onlineFilter.value === 'active' ? online > 0 : online === 0);
      const matchesUdp443 = !udp443Filter.value || row.dataset.allowUdp443 === (udp443Filter.value === 'allowed' ? '1' : '0');
      const matches = matchesName && matchesStatus && matchesOnline && matchesUdp443;
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    if (filterEmpty) filterEmpty.hidden = visible !== 0 || userRows.length === 0;
    if (searchStatus) searchStatus.textContent = visible === userRows.length ? '共 ' + userRows.length + ' 个用户' : '显示 ' + visible + ' / ' + userRows.length + ' 个用户';
    syncFilterUrl();
  }
  function scheduleFilter() {
    if (filterFrame) window.cancelAnimationFrame(filterFrame);
    filterFrame = window.requestAnimationFrame(filterUsers);
  }
  filterForm.addEventListener('submit', function(event) { event.preventDefault(); filterUsers(); });
  filterForm.addEventListener('input', scheduleFilter);
  filterForm.addEventListener('change', scheduleFilter);
  if (clearFilters) clearFilters.addEventListener('click', function() {
    userSearch.value = '';
    statusFilter.value = '';
    onlineFilter.value = '';
    udp443Filter.value = '';
    filterUsers();
    userSearch.focus();
  });
  filterUsers();
}
"""
