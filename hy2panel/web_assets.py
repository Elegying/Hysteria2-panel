"""Static browser assets kept outside the application entrypoint."""

FAVICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<title>Console</title><rect x="2" y="2" width="60" height="60" rx="14" fill="#0b1a2c" stroke="#284867" stroke-width="2"/>
<rect x="17" y="17" width="12" height="12" rx="3" fill="#4bc493"/>
<rect x="35" y="17" width="12" height="12" rx="3" fill="#f3f7ff"/>
<rect x="17" y="35" width="12" height="12" rx="3" fill="#f3f7ff"/>
<rect x="35" y="35" width="12" height="12" rx="3" fill="#4bc493"/>
</svg>"""

# The public login response does not ship dashboard styles, endpoint names or
# QR/client configuration JavaScript. Authentication and form paths stay stable.
LOGIN_STYLE = """
:root{color-scheme:dark;font-family:system-ui,sans-serif;color:#f3f7ff;background:#07111f}
*{box-sizing:border-box}body{margin:0}main{width:min(480px,calc(100% - 32px));margin:clamp(32px,12vh,120px) auto}
.login{padding:32px;border:1px solid #304967;border-radius:20px;background:#0d1929}
.login-brand{display:flex;align-items:center;gap:16px}.login-brand img{width:54px;height:54px}
h1{font-size:28px;margin:4px 0}.state-kicker,.muted,.login-support{color:#a4b1c2}
.login-form{display:grid;gap:12px}label{display:block;margin-bottom:8px}
input{width:100%;min-height:44px;padding:10px;border:1px solid #536b87;border-radius:8px;background:#121f31;color:inherit;font:inherit}
button{min-height:44px;padding:10px 20px;border:0;border-radius:8px;background:#4169b7;color:white;font:inherit;cursor:pointer}
:focus-visible{outline:3px solid #8ab4ff;outline-offset:3px}.login-actions{margin:0}
.login-support{font-size:13px;line-height:1.6}.error{color:#ff9aaa;overflow-wrap:anywhere}
.skip-link{position:absolute;left:16px;top:-100px;color:white}.skip-link:focus{top:8px}
@media(max-width:480px){.login{padding:24px}button{width:100%}}

"""

PAGE_STYLE = """
.user-group-heading{display:flex;align-items:center;gap:22px;flex-wrap:wrap}.user-group-heading h2{margin:0}.user-group-tabs{display:flex;gap:10px}.user-group-tabs .button[aria-current="page"]{background:var(--accent,#4476c9);color:white}.user-group-tabs .button{white-space:nowrap}

:root{color-scheme:dark;--bg:#06111f;--surface:#0b1a2c;--surface-2:#132438;--text:#f3f7ff;--muted:#9aaac0;--line:#22364b;--accent:#5f91f7;--teal:#25b99a;--success:#4bc493;--warning:#f5b54b;--danger:#ff6675}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;text-rendering:optimizeLegibility}
main{width:min(1420px,calc(100% - 40px));margin:20px auto 42px}.topbar{display:flex;align-items:center;gap:12px;background:#102846;border:1px solid #284867;border-radius:20px;padding:18px 22px;margin-bottom:16px}.brand{min-width:max-content}.eyebrow{display:inline-block;border:1px solid #405b7c;border-radius:999px;padding:7px 13px;color:#c8d7ef;font-size:12px;letter-spacing:.12em}.topbar h1{font-size:28px;margin:0 4px}.topbar-spacer{flex:1}.pill{display:flex;align-items:center;gap:6px;min-height:44px;border:1px solid #34495f;border-radius:10px;padding:9px 14px;background:#1b2c40;color:var(--muted);white-space:nowrap}.pill strong{color:var(--text);margin:0}
h1,h2,h3,p{margin-top:0}h2{font-size:20px;margin-bottom:4px}h3{font-size:16px}.muted{color:var(--muted)}.ok{color:var(--success)}.bad{color:var(--danger)}.warning{color:var(--warning)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}.metric,.card{background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 28px rgba(0,0,0,.12)}.metric{padding:16px 18px;border-top:3px solid var(--teal);min-width:0}.metric>strong{display:block;font-size:26px;margin:7px 0 2px;font-variant-numeric:tabular-nums}.metric span{color:var(--muted)}.metric-warning{display:block;color:var(--warning);font-size:12px}.machine-stats{padding:16px 18px}.machine-stats .section-head{margin-bottom:10px}.machine-section-head{align-items:center;padding-bottom:10px}.machine-section-head p{margin:0;font-size:12px}.machine-count{flex:0 0 auto;padding:5px 9px;border:1px solid #375170;border-radius:999px;color:var(--muted);font-size:11px;white-space:nowrap}.machine-warning{margin-bottom:10px}.machine-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.machine-card{min-width:0;padding:12px;border:1px solid #283b50;border-radius:12px;background:var(--surface-2)}.machine-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.machine-card-head>div{min-width:0}.machine-card-head strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.machine-card-head>span{font-weight:750;white-space:nowrap}.machine-kind{display:block;font-size:11px;margin-top:1px}.machine-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:9px 0}.machine-fact{min-width:0;padding:7px 8px;border:1px solid #2b4056;border-radius:9px;background:#101f31}.machine-fact span,.machine-fact strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.machine-fact span{color:var(--muted);font-size:10px}.machine-fact strong{margin-top:2px;font-size:13px}.machine-budget{padding-top:8px;border-top:1px solid var(--line)}.machine-observed{display:block;margin-top:7px;font-size:10px;text-align:right}
.operations{display:grid;gap:16px;margin-bottom:16px;align-items:start}.dashboard-trio{align-items:stretch;grid-template-columns:minmax(0,1.45fr) minmax(270px,.85fr) minmax(240px,.72fr)}.dashboard-trio>.card{height:100%;margin-bottom:0}.card{padding:20px;margin-bottom:16px}.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:1px solid var(--line);padding-bottom:15px;margin-bottom:16px}.dashboard-trio .section-head{padding-bottom:12px;margin-bottom:12px}.service-badge{border-radius:999px;padding:8px 13px;background:#123833;color:var(--success);font-weight:700;white-space:nowrap}.service-badge.off{background:#3a2028;color:#ff9aa4}
.button-row,.actions{display:flex;flex-wrap:wrap;gap:9px}.service-actions>.button{display:inline-flex;align-items:center;justify-content:center;text-align:center}button,.button{display:inline-block;border:1px solid transparent;border-radius:10px;background:var(--accent);color:#fff;padding:10px 15px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer;transition:filter .15s ease,transform .15s ease}button:hover,.button:hover{filter:brightness(1.08);transform:translateY(-1px)}button:active,.button:active{transform:none}button.secondary,.button.secondary{background:#1b2c40;border-color:#34495f}button.success{background:var(--success);color:#082016}button.warning{background:var(--warning);color:#251a05}button.danger{background:var(--danger)}button.ghost{background:transparent;border-color:#3a526b;color:#dce8f8}form.inline{display:inline}.system-actions{flex:0 0 auto}.system-actions button{padding:8px 11px}
.resource-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.resource,.detail{background:var(--surface-2);border:1px solid #283b50;border-radius:14px;padding:18px}.resource{padding:12px}.resource strong{font-size:18px;margin-top:4px}.resource small{font-size:11px}.resource strong,.detail strong{display:block}.certificate-resource{grid-column:1/-1;display:flex;align-items:baseline;gap:8px;min-width:0}.certificate-resource span{white-space:nowrap}.certificate-resource strong{margin:0;font-size:16px;white-space:nowrap}.service-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.compact-detail{padding:12px}.compact-detail strong{font-size:18px;margin-top:4px}.port-detail{display:flex;align-items:center;justify-content:space-between;gap:12px}.port-detail>div strong{white-space:nowrap}.egress-control{display:grid;justify-items:end;gap:3px;margin:0}.egress-state{color:var(--muted);font-size:11px;font-weight:750;white-space:nowrap}.egress-state.on{color:var(--success)}.egress-state.unknown{color:var(--warning)}.egress-switch{display:inline-flex;align-items:center;gap:6px;padding:5px 7px;background:#1b2c40;border-color:#40566f;border-radius:999px;font-size:11px}.egress-switch.on{background:#123833;border-color:#26745d;color:#caffec}.egress-switch.unknown{border-color:#8b6b30}.egress-switch-track{position:relative;width:30px;height:18px;border-radius:999px;background:#52647a;box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}.egress-switch-track>span{position:absolute;top:3px;left:3px;width:12px;height:12px;border-radius:50%;background:#fff;transition:transform .15s ease}.egress-switch.on .egress-switch-track{background:var(--success)}.egress-switch.on .egress-switch-track>span{transform:translateX(12px)}.egress-switch-action{min-width:22px;text-align:center}.bbr-detail strong,.version-row strong{font-size:18px;margin-top:4px}.bbr-detail small{display:block;font-size:11px;margin-top:3px}.version-panel>p{font-size:12px;margin:4px 0 0}.version-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.version-actions{flex-wrap:nowrap}.version-actions form{margin:0}.compact-button{padding:8px 11px}.notice{padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#10233a;color:#c7d6ea}
.rank-list{display:grid;gap:6px}.rank-row{display:grid;grid-template-columns:28px minmax(0,1fr);align-items:center;gap:7px;padding:7px 9px;background:var(--surface-2);border:1px solid #283b50;border-radius:10px}.rank-main{display:flex;align-items:baseline;gap:8px;min-width:0}.rank-number{color:var(--accent);font-weight:800}.rank-name{font-weight:700;overflow:hidden;text-overflow:ellipsis}.rank-traffic{color:var(--muted);font-size:12px;white-space:nowrap}
.traffic-history-total{font-size:22px;font-weight:750;color:var(--success)}.traffic-history-day{border-top:1px solid var(--line);padding:12px 0}.traffic-history-day summary{cursor:pointer}.traffic-history-line{display:grid;grid-template-columns:minmax(110px,1fr) minmax(90px,1fr) 60px;gap:8px;align-items:center;padding:8px 0;font-variant-numeric:tabular-nums}.traffic-history-line strong{color:var(--success)}.traffic-history-line> :last-child{text-align:right}.traffic-history-day>p{font-size:13px}
.create-grid{display:grid;grid-template-columns:2fr 1fr 1fr auto;align-items:end;gap:12px;margin-bottom:22px}.section-actions,.user-tools{display:flex;align-items:center;gap:9px}.user-section-head{display:flex;align-items:center;flex-wrap:wrap}.user-heading{flex:1 1 240px}.user-section-head .section-actions{flex:0 0 auto}.user-tools{justify-content:space-between;margin-bottom:14px}.user-filters{display:grid;grid-template-columns:minmax(220px,2fr) repeat(3,minmax(120px,1fr)) auto auto;align-items:end;gap:9px;flex:1}.user-filters label{margin-bottom:4px;font-size:12px;color:var(--muted)}.user-filters button{padding:10px 12px}.search-status{margin:0;white-space:nowrap}.filter-empty{margin:0 0 14px;padding:11px 14px;border:1px dashed #3a526b;border-radius:10px;text-align:center}label{display:block;font-weight:650;margin-bottom:6px}input,textarea,select{width:100%;padding:11px 13px;border:1px solid #3a4d63;border-radius:9px;background:#101f31;color:var(--text);font:inherit}input:focus,textarea:focus,select:focus,button:focus-visible,.button:focus-visible{outline:3px solid rgba(95,145,247,.38);outline-offset:2px}button:disabled{cursor:wait;opacity:.65}.table-wrap{overflow-x:auto;scrollbar-gutter:stable}table{width:100%;border-collapse:separate;border-spacing:0;min-width:1050px;font-variant-numeric:tabular-nums}th,td{padding:13px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}th{color:var(--muted);font-size:13px;white-space:nowrap}.user-table th{position:sticky;top:0;z-index:2;background:var(--surface);box-shadow:0 1px 0 var(--line)}.user-table tbody tr{transition:background-color .15s ease}.user-table tbody tr:hover{background:#0f2135}.user-table tr[data-over-device-limit="1"]{background:rgba(255,102,117,.07)}.over-limit-name{color:var(--danger)}.limit-alert{display:block;margin-top:2px;color:var(--danger);font-size:11px;font-weight:700}.limit-alert[hidden]{display:none}.sort-link{color:inherit;text-decoration:none}.sort-link:hover{text-decoration:underline}.status{font-weight:750}.enabled{color:var(--success)}.disabled{color:var(--danger)}progress{width:150px;height:10px;accent-color:var(--accent)}.traffic-cell{min-width:190px}.traffic-label{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--muted);margin-top:4px}.actions{min-width:420px}.user-table tr[hidden]{display:none}.update-state{margin-top:6px}.update-state[data-state="failed"]{color:var(--danger)}.update-state[data-state="running"],.update-state[data-state="queued"]{color:var(--warning)}.update-state[data-state="success"]{color:var(--success)}
.checkbox-field{display:flex;align-items:flex-start;gap:10px;margin:0;padding:12px;border:1px solid #3a4d63;border-radius:10px;background:#101f31}.checkbox-field input{width:auto;margin:4px 0 0;flex:0 0 auto}.checkbox-field span{font-weight:650}.checkbox-field small{display:block;margin-top:3px;font-weight:400}
.login{width:min(430px,100%);margin:12vh auto}.login-form{display:grid;gap:12px}.login-actions{margin:4px 0 0}.login-actions button{min-width:110px}.copy-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px;margin-bottom:16px}.error{color:var(--danger)}code{word-break:break-all}
.migration-dialog{width:min(820px,calc(100% - 32px));max-height:min(86vh,760px);padding:0;border:1px solid #35506d;border-radius:18px;background:var(--surface);color:var(--text);box-shadow:0 24px 80px rgba(0,0,0,.55);overflow:auto}.migration-dialog::backdrop{background:rgba(1,8,18,.78);backdrop-filter:blur(4px)}.credentials-dialog{width:min(680px,calc(100% - 32px))}.create-dialog{width:min(560px,calc(100% - 32px))}.create-dialog .create-grid{grid-template-columns:1fr 1fr;margin-bottom:0}.create-dialog .wide,.create-dialog .create-grid>button{grid-column:1/-1}.credentials-dialog textarea{min-height:118px}.qr-panel{display:grid;justify-items:center;gap:8px;margin:16px 0}.qr-panel[hidden]{display:none}.qr-canvas{display:block;width:min(100%,320px);height:auto;border:10px solid #fff;border-radius:8px;background:#fff;image-rendering:pixelated}.credential-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:14px 0}.credential-actions button{width:100%}.dialog-shell{padding:22px}.dialog-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:16px}.dialog-head h2{margin-bottom:4px}.dialog-close{flex:0 0 auto;width:40px;height:40px;padding:0;border-radius:50%;background:#1b2c40;border-color:#34495f;font-size:24px;line-height:1}.migration-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.migration-grid .detail{height:100%}.migration-grid p:last-child{margin-bottom:0}.toast{position:fixed;right:18px;bottom:18px;z-index:20;max-width:min(420px,calc(100% - 36px));margin:0;padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#102846;box-shadow:0 12px 36px rgba(0,0,0,.4)}.toast.error{border-color:#8a3844;color:#ffd5da}.toast[hidden]{display:none}
.node-onboarding-dialog{width:min(900px,calc(100% - 32px))}.node-enrollment-grid{display:grid;grid-template-columns:minmax(190px,1fr) minmax(190px,1fr) minmax(120px,.55fr) auto;align-items:end;gap:10px;margin:16px 0}.enrollment-result{margin:16px 0;padding:14px;border:1px solid #375170;border-radius:12px;background:#0d2035}.enrollment-result[hidden]{display:none}.enrollment-result textarea{min-height:220px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}.node-list-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-top:20px}.node-list{display:grid;gap:8px}.node-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px;padding:11px 12px;border:1px solid #283b50;border-radius:11px;background:var(--surface-2)}.node-row>div:first-child{min-width:0}.node-row strong,.node-row small{display:block}.node-row small{margin-top:2px;overflow-wrap:anywhere}.node-row>span{font-weight:750;white-space:nowrap}.node-actions{display:flex;flex-wrap:wrap;gap:8px}.node-actions form{margin:0}
.operation-guides{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 18px}.operation-guide{padding:15px;border:1px solid #375170;border-radius:13px;background:#0d2035}.operation-guide h3{margin:0 0 12px}.danger-guide{border-color:#80505a}.numbered-steps{list-style:none;counter-reset:guide-step;display:grid;gap:11px;margin:0;padding:0}.numbered-steps li{counter-increment:guide-step;display:grid;grid-template-columns:34px minmax(0,1fr);column-gap:9px;align-items:start}.numbered-steps li::before{content:counter(guide-step);display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:var(--accent);color:#03101e;font-weight:850;grid-row:1/3}.danger-guide .numbered-steps li::before{background:var(--warning)}.numbered-steps strong,.numbered-steps span{grid-column:2}.numbered-steps span{margin-top:2px;color:var(--muted);font-size:13px;line-height:1.45}.budget-summary{display:grid;gap:2px;min-width:0}.budget-main{display:flex;align-items:baseline;justify-content:space-between;gap:8px}.budget-main span,.budget-main strong{white-space:nowrap}.budget-main strong{font-size:12px}.budget-summary small{font-size:10px;white-space:normal}.budget-editor{margin-top:6px}.budget-editor summary{width:max-content;color:#c8d7ef;font-size:11px;font-weight:750;cursor:pointer}.budget-editor summary:hover{color:var(--text)}.budget-editor[open] summary{margin-bottom:7px}.budget-form{display:grid;grid-template-columns:repeat(4,minmax(80px,1fr)) auto;gap:6px;align-items:end;min-width:0}.budget-form label{font-size:10px;color:var(--muted)}.budget-form input{min-width:0;padding:7px 8px;margin-top:3px}.budget-form button{padding:8px 10px;white-space:nowrap}.legacy-cleanup-form{margin-top:7px}.legacy-cleanup-form button{width:100%}.wide-detail{grid-column:1/-1}
@media(max-width:640px){.operation-guides{grid-template-columns:1fr}}
@media(min-width:641px) and (max-width:1300px){.brand{display:none}.topbar h1{white-space:nowrap}}
@media(max-width:1050px){.topbar{flex-wrap:wrap}.topbar-spacer{display:none}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.operations{grid-template-columns:1fr}.create-grid{grid-template-columns:1fr 1fr}.create-grid .wide{grid-column:1/-1}.node-enrollment-grid{grid-template-columns:1fr 1fr}.node-enrollment-grid>button{width:100%}.user-filters{grid-template-columns:minmax(200px,2fr) repeat(3,minmax(105px,1fr)) auto auto}.budget-form{grid-template-columns:repeat(2,minmax(0,1fr))}.budget-form button{grid-column:1/-1}}
@media(max-width:640px){.certificate-resource{grid-column:1/-1}main{width:calc(100% - 16px);margin:8px auto 24px}.topbar{padding:16px;border-radius:16px;align-items:flex-start;gap:9px}.topbar h1{font-size:23px;width:100%;order:-2;margin:0 0 5px}.brand{display:none}.pill{flex:1 1 calc(50% - 5px);padding:8px 10px;font-size:12px;text-align:center}.topbar-action,.logout-form{flex:1 1 calc(50% - 5px)}.topbar-action,.logout-form button{width:100%}.metrics{grid-template-columns:1fr 1fr;gap:8px}.metric{padding:14px}.metric strong{font-size:20px}.metric small{font-size:12px}.card{padding:16px;border-radius:14px}.primary-details{grid-template-columns:1fr}.create-grid,.migration-grid,.create-dialog .create-grid,.node-enrollment-grid{grid-template-columns:1fr}.node-enrollment-grid>button{width:100%}.node-list-head{align-items:flex-start;flex-direction:column;gap:2px}.node-row{grid-template-columns:minmax(0,1fr) auto}.node-actions{grid-column:1/-1;display:grid}.node-actions form,.node-actions button{width:100%}.section-head{flex-direction:column;padding-bottom:13px}.machine-section-head{gap:7px}.machine-count{align-self:flex-start}.machine-grid{grid-template-columns:1fr}.machine-facts{grid-template-columns:repeat(2,minmax(0,1fr))}.budget-form{grid-template-columns:repeat(2,minmax(0,1fr))}.budget-form button{grid-column:1/-1}.user-heading{flex-basis:auto}.section-head>form,.section-head>form button,.create-grid>button{width:100%}.system-actions{width:100%}.section-actions{display:grid;grid-template-columns:1fr 1fr;width:100%}.section-actions form,.section-actions button{width:100%}.section-actions form{grid-column:1/-1}.user-tools{align-items:stretch;flex-direction:column}.user-filters{grid-template-columns:1fr 1fr;width:100%}.user-filters .user-search{grid-column:1/-1}.user-filters button{width:100%}.search-status{white-space:normal}.button-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.button-row form,.button-row button,.button-row .button{width:100%}.bbr-detail,.version-panel{padding:10px}.version-row{gap:6px}.compact-button{padding:7px 6px;font-size:12px;white-space:nowrap}.login{margin:8vh auto}.login-actions button{width:100%}.copy-grid{grid-template-columns:1fr}.copy-grid button{width:100%}.migration-dialog{width:calc(100% - 12px);max-height:calc(100dvh - 12px);border-radius:14px}.dialog-shell{padding:16px}.dialog-head{position:sticky;top:-16px;z-index:1;background:var(--surface);padding-top:16px}.qr-canvas{width:min(100%,288px)}.user-table{overflow:visible}.user-table table,.user-table tbody{display:block;width:100%;min-width:0}.user-table thead{display:none}.user-table tr{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px 10px;margin-bottom:8px;padding:10px;background:var(--surface-2);border:1px solid #283b50;border-radius:12px}.user-table td{display:block;width:auto;min-width:0;padding:0;border-bottom:0}.user-table td:nth-child(1){grid-column:1}.user-table td:nth-child(2){grid-column:2}.user-table td:nth-child(3){grid-column:3}.user-table td:nth-child(4){grid-column:1;font-size:11px;color:var(--muted)}.user-table td:nth-child(5){grid-column:2/4}.user-table td:nth-child(6){grid-column:1/-1;padding-top:2px}.user-table .traffic-cell{min-width:0}.user-table .traffic-label{gap:5px;font-size:10px}.user-table progress{display:block;width:100%;height:8px}.user-table .actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;min-width:0}.user-table .actions form,.user-table .actions button{width:100%;min-width:0}.user-table .actions button{padding:7px 3px;font-size:11px;white-space:nowrap}.user-table .empty-state{grid-column:1/-1!important;text-align:center}.toast{right:8px;bottom:8px;max-width:calc(100% - 16px)}}
@media(max-width:340px){.metrics{grid-template-columns:1fr}.pill{flex-basis:100%}.version-panel{padding-inline:8px}.version-row{align-items:flex-start;flex-direction:column;gap:4px}.bbr-detail strong,.version-row strong{font-size:16px}.compact-button{padding:7px 5px;font-size:11px;white-space:nowrap}.user-table .actions button{padding-inline:1px;font-size:10px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important}.migration-dialog::backdrop{backdrop-filter:none}}

/* Professional operations-console refinement. This override layer keeps the
   original responsive contract stable while bringing every surface into one
   visual system. */
:root{--bg:#07111f;--surface:#0d1929;--surface-2:#121f31;--surface-3:#17263a;--text:#f7f9fc;--muted:#a4b1c2;--line:#26384e;--line-strong:#36506c;--accent:#78a6ff;--accent-strong:#5689ee;--teal:#38c2a5;--success:#56d29f;--warning:#f3bd62;--danger:#ff7886;--shadow:0 18px 48px rgba(0,0,0,.22)}
html{scroll-behavior:smooth}body{min-height:100vh;background:radial-gradient(circle at 12% -10%,rgba(76,123,199,.17),transparent 34rem),radial-gradient(circle at 92% 0,rgba(37,185,154,.08),transparent 28rem),var(--bg)}body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.22;background-image:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(to bottom,#000,transparent 70%)}::selection{background:rgba(120,166,255,.35);color:#fff}.skip-link{position:fixed;z-index:100;top:12px;left:12px;transform:translateY(-160%);padding:10px 14px;border-radius:10px;background:#fff;color:#07111f;font-weight:800;text-decoration:none}.skip-link:focus{transform:none}
main{position:relative;width:min(1280px,calc(100% - 48px));margin:24px auto 56px}h1,h2,h3{letter-spacing:-.02em}h1{font-size:clamp(25px,2.4vw,32px);line-height:1.15}h2{font-size:21px;line-height:1.25}h3{font-size:16px;line-height:1.3}p{line-height:1.65}
.topbar{position:relative;isolation:isolate;overflow:hidden;min-height:92px;padding:20px 24px;border-color:#315375;border-radius:20px;background:linear-gradient(118deg,#132b49 0%,#10243d 58%,#0e2138 100%);box-shadow:var(--shadow)}.topbar::after{content:"";position:absolute;z-index:-1;top:-80px;right:18%;width:260px;height:190px;border-radius:50%;background:rgba(120,166,255,.13);filter:blur(38px)}.topbar h1{max-width:430px;margin:0 8px}.eyebrow{padding:7px 11px;border-color:#486887;background:rgba(255,255,255,.035);color:#c8d8ee;font-size:10px;font-weight:800}.pill{display:flex;align-items:center;gap:6px;min-height:44px;padding:9px 14px;border-color:#3a506b;border-radius:10px;background:#17273b;font-size:12px}.pill strong{margin:0;color:#fff;font-size:13px}.topbar-action,.logout-form button{min-height:44px}
.metrics{gap:14px;margin-bottom:18px}.metric,.card{border-color:var(--line);background:linear-gradient(180deg,rgba(16,30,48,.98),rgba(12,24,39,.98));box-shadow:0 12px 34px rgba(0,0,0,.16)}.metric{position:relative;overflow:hidden;min-height:132px;padding:20px 21px;border-top:1px solid var(--line)}.metric::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:linear-gradient(var(--teal),rgba(56,194,165,.12))}.metric>span{font-size:12px;font-weight:700;letter-spacing:.03em}.metric>strong{margin:11px 0 5px;font-size:30px;letter-spacing:-.03em}.metric small{display:block;line-height:1.45}.card{padding:22px;border-radius:18px}.section-head{margin-bottom:18px;padding-bottom:16px}.section-head h2{margin-bottom:5px}.section-head p{margin-bottom:0;font-size:13px}
.machine-stats{padding:14px 16px}.machine-grid{gap:12px}.machine-card,.resource,.detail,.rank-row{border-color:#2b4058;background:linear-gradient(180deg,#142338,#111f31)}.machine-card{padding:15px;border-radius:14px}.machine-facts{gap:8px;margin:12px 0}.machine-fact{padding:9px 10px;border-color:#2a415a;background:#0d1b2c}.machine-fact span{font-size:11px}.machine-fact strong{font-size:14px}.machine-observed{margin-top:9px}.budget-editor summary{display:inline-flex;align-items:center;min-height:36px;padding:6px 10px;border:1px solid #39536e;border-radius:8px;background:#13243a;font-size:12px}
.machine-budget-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.machine-budget-row{min-width:0;padding:12px;border:1px solid var(--line);border-radius:10px}.machine-budget-head,.machine-budget-usage,.machine-budget-meta{display:flex;align-items:center;justify-content:space-between;gap:8px}.machine-budget-head>div{min-width:0}.machine-budget-head>div>strong{display:inline;font-size:15px;overflow-wrap:anywhere}.machine-ip{font-size:12px;overflow-wrap:anywhere}.machine-budget-usage>strong{min-width:0;overflow-wrap:anywhere}.machine-budget-head small{display:block;margin-top:3px}.machine-online{flex:0 0 auto;color:#dce5f3;font-size:15px;white-space:nowrap}.machine-online strong{font-size:17px}.machine-budget-row>progress{display:block;width:100%;height:6px;margin:8px 0;background:#344056}.machine-budget-row>progress::-webkit-progress-bar{background:#344056}.machine-budget-row>progress::-webkit-progress-value{background:linear-gradient(90deg,#a9c4ff,#7fa6f8)}.machine-budget-usage{align-items:flex-start;flex-direction:column;gap:2px}.machine-budget-usage>strong{font-size:14px;font-variant-numeric:tabular-nums}.machine-budget-usage>span{font-size:12px;white-space:nowrap}.machine-budget-meta{align-items:center;margin-top:6px}.machine-budget-meta>small{min-width:0;line-height:1.45}.machine-budget-edit,.legacy-cleanup-form{flex:0 0 auto;margin:0}.budget-dialog{width:min(680px,calc(100% - 32px))}.budget-dialog-form{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.budget-dialog-form button{grid-column:1/-1}.budget-dialog-form label{color:var(--muted)}
.dashboard-trio{grid-template-columns:minmax(0,1.35fr) minmax(280px,.82fr) minmax(250px,.74fr);gap:14px}.dashboard-trio>.card{min-width:0}.service-badge{border:1px solid rgba(86,210,159,.3);background:rgba(52,145,109,.15);font-size:12px}.service-badge.off{border-color:rgba(255,120,134,.28);background:rgba(173,58,72,.16)}
button,.button{min-height:42px;padding:9px 14px;border-radius:10px;background:linear-gradient(180deg,#4169b7,#325591);box-shadow:0 5px 14px rgba(34,80,157,.18);transition:background-color .15s ease,border-color .15s ease,box-shadow .15s ease,transform .15s ease}button:hover,.button:hover{filter:none;box-shadow:0 8px 18px rgba(34,80,157,.24);transform:translateY(-1px)}button.secondary,.button.secondary{border-color:#3a506b;background:#17273b;box-shadow:none}button.secondary:hover,.button.secondary:hover,button.ghost:hover{border-color:#58718f;background:#1b3048}button.success{background:linear-gradient(180deg,#5fd9a7,#3dbb8b);box-shadow:0 5px 14px rgba(39,139,101,.18)}button.warning{border-color:rgba(243,189,98,.42);background:rgba(243,189,98,.12);color:#ffd991;box-shadow:none}button.warning:hover{background:rgba(243,189,98,.2)}button.danger{border-color:rgba(255,120,134,.43);background:rgba(255,120,134,.1);color:#ffb4bc;box-shadow:none}button.danger:hover{background:rgba(255,120,134,.18)}button.ghost{border-color:#374e68;background:transparent;box-shadow:none;color:#dce8f8}button:disabled{transform:none;box-shadow:none}.compact-button{min-height:38px}
.service-details{gap:10px;margin-top:14px}.compact-detail{padding:14px}.resource-grid{gap:10px}.resource{min-height:87px;padding:14px}.resource strong{font-size:20px}.certificate-resource{min-height:auto}.rank-list{gap:8px}.rank-row{min-height:44px;padding:9px 11px}.rank-number{font-size:12px}.rank-main{justify-content:space-between}.rank-traffic{font-variant-numeric:tabular-nums}.notice{padding:13px 15px;border-color:#385473;border-radius:12px;background:#10243a;color:#d2def0}.notice strong{color:#fff}code{padding:2px 5px;border:1px solid #314962;border-radius:5px;background:#0a1727;color:#dbe8fb}
.login{position:relative;width:min(480px,100%);margin:clamp(64px,12vh,120px) auto;padding:34px;border-color:#304967;background:linear-gradient(155deg,#13243a,#0c1929);box-shadow:0 30px 90px rgba(0,0,0,.38)}.login::before{content:"H2";display:grid;place-items:center;width:54px;height:54px;margin-bottom:24px;border:1px solid #47688d;border-radius:15px;background:linear-gradient(145deg,#173756,#10233a);color:#82dfc0;font-size:20px;font-weight:900;letter-spacing:-.04em}.login h1{margin-bottom:8px;font-size:29px}.login>.muted{margin-bottom:26px}.login-form{gap:16px}.login-actions{margin-top:4px}.login-actions button{width:100%;min-height:46px}.login-support{display:flex;align-items:flex-start;gap:9px;margin:22px 0 0;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.login-support::before{content:"";flex:0 0 auto;width:8px;height:8px;margin-top:5px;border-radius:50%;background:var(--success);box-shadow:0 0 0 4px rgba(86,210,159,.1)}
.login::before{display:none}.login-brand{display:flex;align-items:center;gap:16px;margin-bottom:18px}.login-brand img{flex:0 0 auto;width:54px;height:54px;border-radius:15px;box-shadow:0 12px 28px rgba(0,0,0,.28)}.login-brand .state-kicker{margin-bottom:7px}.login-brand h1{margin:0}.dialog-close{width:auto;min-width:64px;height:40px;padding:0 14px;border-radius:999px;font-size:13px;line-height:1;white-space:nowrap}
.state-page{width:min(620px,100%);margin:clamp(72px,15vh,150px) auto;padding:34px}.state-kicker{display:inline-flex;margin-bottom:18px;padding:6px 10px;border:1px solid #3d5672;border-radius:999px;background:#12253d;color:#bfd0e8;font-size:11px;font-weight:800;letter-spacing:.08em}.state-page h1{margin-bottom:12px}.state-page .error{padding:14px 16px;border:1px solid rgba(255,120,134,.3);border-radius:12px;background:rgba(255,120,134,.08);color:#ffc2c8}.state-actions{display:flex;gap:10px;margin:24px 0 0}.copy-grid{padding:14px;border:1px solid #2b4058;border-radius:13px;background:#101f31}.copy-grid textarea{background:#0b1828}

label{font-size:13px}input,textarea,select{min-height:44px;padding:10px 12px;border-color:#3a506a;border-radius:10px;background:#0e1c2d}textarea{line-height:1.55}input:hover,textarea:hover,select:hover{border-color:#506987}input:focus,textarea:focus,select:focus,button:focus-visible,.button:focus-visible,summary:focus-visible{outline:3px solid rgba(120,166,255,.34);outline-offset:2px;border-color:#79a7ff}
.user-tools{align-items:flex-end;padding:14px;border:1px solid #273c54;border-radius:14px;background:#0d1b2c}.user-filters{gap:10px}.search-status{padding-bottom:10px;font-size:12px}.table-wrap{border:1px solid #273b52;border-radius:14px}.user-table table{min-width:1080px}.user-table th{top:0;padding:12px 11px;background:#101f31;color:#b3c0d1;font-size:11px;letter-spacing:.03em}.user-table td{padding:12px 11px}.user-table tbody tr:last-child td{border-bottom:0}.user-table tbody tr:hover{background:#122338}.status{display:inline-flex;align-items:center;min-height:28px;padding:4px 9px;border-radius:999px;font-size:12px}.status.enabled{background:rgba(86,210,159,.1)}.status.disabled{background:rgba(255,120,134,.1)}progress{overflow:hidden;height:7px;border:0;border-radius:999px;background:#22364d}progress::-webkit-progress-bar{background:#22364d;border-radius:999px}progress::-webkit-progress-value{border-radius:999px;background:linear-gradient(90deg,var(--teal),var(--accent))}.traffic-label{margin-top:6px;font-size:11px}
.actions{align-items:center;min-width:360px;gap:6px}.actions button{min-height:36px;padding:7px 10px;font-size:12px}
.migration-dialog{border-color:#3b5674;border-radius:20px;background:#0d1a2b;box-shadow:0 28px 100px rgba(0,0,0,.62)}.migration-dialog::backdrop{background:rgba(2,8,17,.82)}.dialog-shell{padding:0 24px 24px}.dialog-head{position:sticky;z-index:4;top:0;margin:0 -24px 20px;padding:22px 24px 17px;border-color:#263b52;background:rgba(13,26,43,.96);backdrop-filter:blur(14px)}.dialog-head h2{font-size:23px}.dialog-close{width:44px;height:44px;border-color:#405a77;background:#17293f;box-shadow:none}.operation-guide{padding:17px;border-color:#38526f;border-radius:14px;background:#102138}.danger-guide{border-color:#73505a;background:#201c2b}.numbered-steps{gap:13px}.numbered-steps li{grid-template-columns:36px minmax(0,1fr)}.numbered-steps li::before{width:32px;height:32px;background:#79a7ff;color:#06101e}.numbered-steps span{font-size:12px}.node-enrollment-grid{padding:16px;border:1px solid #2c435c;border-radius:14px;background:#0b1929}.node-row{padding:14px;border-radius:13px}.migration-grid{gap:14px}.migration-grid .detail{padding:20px}.credential-actions{gap:10px}.toast{padding:13px 16px;border-color:#3e5a7a;border-radius:12px;background:#142b49;box-shadow:var(--shadow)}.toast:not(.error){color:#dff8ed}.toast.error{background:#321c28}
@media(max-width:1050px){main{width:min(920px,calc(100% - 32px))}.dashboard-trio{grid-template-columns:1fr;gap:14px}.topbar h1{max-width:none}.user-tools{align-items:stretch}.actions{min-width:330px}}
@media(max-width:640px){body::before{display:none}main{width:calc(100% - 24px);margin:12px auto 32px}.topbar{min-height:0;padding:18px;border-radius:18px}.topbar h1{font-size:24px;line-height:1.2}.pill{justify-content:center;min-height:44px;text-align:center}.metrics{gap:10px}.metric{min-height:112px;padding:16px}.metric>strong{font-size:24px}.card{padding:18px;border-radius:16px}.machine-stats{padding:12px}.machine-card{padding:14px}.section-head{gap:10px}.button-row{gap:8px}.button-row button,.button-row .button{min-height:44px}.user-tools{padding:12px}.user-table{border:0}.user-table tr{grid-template-columns:minmax(0,1fr) auto auto;padding:10px;gap:6px 8px;border-radius:12px}.user-table td:nth-child(1){grid-column:1}.user-table td:nth-child(2){grid-column:2}.user-table td:nth-child(3){grid-column:3;white-space:nowrap}.user-table td:nth-child(4){grid-column:1;font-size:10px;color:var(--muted);white-space:nowrap}.user-table td:nth-child(5){grid-column:2/4}.user-table td:nth-child(6){grid-column:1/-1;margin-top:0;padding-top:8px;border-top:1px solid #2b4058}.user-table td:nth-child(3)::before,.user-table td:nth-child(4)::before{display:inline;margin-right:4px;color:var(--muted);font-size:9px;font-weight:700;letter-spacing:.02em}.user-table td:nth-child(3)::before{content:"在线"}.user-table td:nth-child(4)::before{content:"上下行"}.user-table progress{height:6px}.user-table .traffic-label{margin-top:3px;font-size:10px}.user-table .actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));min-width:0;gap:4px}.user-table .actions form,.user-table .actions button{width:100%}.user-table .actions button{min-height:32px;padding:5px 4px;font-size:11px}.login{margin:36px auto;padding:26px}.state-page{margin:44px auto;padding:24px}.state-actions{display:grid}.dialog-shell{padding:0 18px 18px}.dialog-head{top:0;margin:0 -18px 18px;padding:18px}.dialog-head h2{font-size:21px}.operation-guides{gap:10px}.operation-guide{padding:14px}.node-enrollment-grid{padding:13px}.migration-grid .detail{padding:16px}.toast{left:12px;right:12px;bottom:12px;max-width:none}}
@media(max-width:960px){.machine-budget-list{grid-template-columns:1fr}}
@media(max-width:640px){.machine-section-head{flex-direction:row;align-items:center;gap:8px}.machine-section-head h2{font-size:17px}.machine-count{align-self:center}.machine-budget-row{padding:10px}.machine-budget-head>div>strong{font-size:15px}.machine-online{font-size:12px}.machine-online strong{font-size:17px}.machine-budget-meta{gap:8px}.machine-budget-meta>small{font-size:12px}.machine-budget-edit{width:auto;min-height:32px;padding:6px 9px}.budget-dialog-form{grid-template-columns:1fr}}
@media(max-width:360px){main{width:calc(100% - 16px)}.metrics{grid-template-columns:1fr}.section-actions{grid-template-columns:1fr}.section-actions form{grid-column:auto}.user-filters{grid-template-columns:1fr}.user-filters .user-search{grid-column:auto}.login{padding:22px}}
@media(prefers-contrast:more){:root{--line:#536b87;--line-strong:#7890aa;--muted:#c3cddd}.card,.metric,.machine-card,.machine-budget-row,.resource,.detail,input,textarea,select{border-width:2px}}
@media(forced-colors:active){button,.button,.status,.service-badge,.eyebrow,.pill{forced-color-adjust:auto}.metric::before{display:none}}
@media(max-width:640px){.user-table table,.user-table tbody{display:block;width:100%;min-width:0}}
@media(max-width:640px){.user-table td{padding:0}.user-table td:nth-child(6){padding-top:8px}}
@media(max-width:640px){.version-row{display:grid;grid-template-columns:1fr;align-items:start;gap:8px}.version-actions{grid-template-columns:1fr;width:100%}.version-actions form,.version-actions button{width:100%}}
.service-badge.pending{border-color:rgba(243,189,98,.34);background:rgba(243,189,98,.12);color:var(--warning)}.service-badge.failed{border-color:rgba(255,120,134,.34);background:rgba(255,120,134,.13);color:#ffabb4}.user-table td:first-child strong,.node-row strong{overflow-wrap:anywhere;word-break:break-word}.topbar .pill,.topbar .topbar-action,.topbar .logout-form button{border:1px solid #3a506b;border-radius:10px;background:#17273b;box-shadow:none}
@media(max-width:640px){.user-table td:first-child strong{display:block;max-width:100%}}
#overview,#nodes,#users{scroll-margin-top:16px}.advanced-help{margin-top:12px}.migration-guide{display:grid;gap:12px}.migration-guide p{margin:8px 0;line-height:1.65}.migration-guide h3{margin:0}.migration-guide code{white-space:nowrap}.egress-help{font-size:13px;line-height:1.6}.user-filters{grid-template-columns:minmax(160px,2fr) repeat(3,minmax(90px,1fr)) auto auto}
@media(max-width:640px){.user-filters{grid-template-columns:1fr 1fr}.user-table .actions{gap:8px}.user-table .actions button{min-height:44px;font-size:14px;padding:10px 6px;text-align:center}.user-table .traffic-label,.user-table td:nth-child(4){font-size:12px}.section-actions button{min-height:44px}.user-filters button[type="submit"]{grid-column:1}.user-table td:nth-child(4){white-space:normal}}
.edit-lookup{display:flex;gap:8px}.edit-lookup input{min-width:0;flex:1}.edit-lookup button{flex-shrink:0}.edit-fields{border:0;padding:0;min-width:0}.dialog-head>div{min-width:0}#edit-user-title{overflow-wrap:anywhere}
.dialog-status{margin:0 22px 22px;padding:12px 14px;border:1px solid #8a3844;border-radius:10px;background:#34202b;color:#ffd5da;overflow-wrap:anywhere}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important}.migration-dialog::backdrop,.dialog-head{backdrop-filter:none}}
.subscription-node-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:16px;margin:12px 0;border:1px solid #3d5672;border-radius:12px;min-width:0}.subscription-node-row label{min-width:0}.subscription-node-row input{width:100%}.subscription-node-row input[type=checkbox]{width:auto}.subscription-url{overflow-wrap:anywhere}@media(max-width:600px){.subscription-node-row{grid-template-columns:1fr}}
[data-live-user-name]{position:relative}
[data-live-user-name]>strong{transform:translateY(-4px)}
.expiry-note{position:absolute;left:11px;right:2px;top:calc(50% + 8px);font-size:10px;line-height:12px;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:auto}
@media(max-width:640px){.expiry-note{left:0;top:calc(50% + 2px);font-size:9px;line-height:11px}[data-live-user-name]>strong{transform:translateY(-5px)}}

/* Aligned management dialogs share the panel's existing colors and controls. */
.node-management-dialog{width:min(960px,calc(100% - 32px));max-height:min(90dvh,900px)}
.node-management-dialog .dialog-head{align-items:center;padding-top:20px;padding-bottom:18px;margin-bottom:20px}
.node-management-dialog .dialog-head h2{font-size:22px;line-height:1.35;margin:0 0 6px}
.node-management-dialog .dialog-head p{font-size:13px;line-height:1.6;margin:0;max-width:650px}
.node-management-dialog .management-notice{padding:12px 16px;margin:0 0 18px;background:#102237;border:1px solid #2c465f;border-radius:12px;font-size:13px;line-height:1.65}
.management-notice strong{display:block;color:#dce8f8;font-size:13px;margin-bottom:3px}.management-notice p{margin:0;color:var(--muted)}
.management-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.management-section-head h3{font-size:15px;margin:0}.management-section-head>span{font-size:12px}.management-section-head p{font-size:12px;margin:4px 0 0}
.node-management-dialog .node-enrollment-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start;margin:0 0 24px;padding:20px;border-color:#2b4058;border-radius:14px}
.node-enrollment-grid>.management-section-head{grid-column:1/-1;padding-bottom:14px;border-bottom:1px solid #253b52;margin-bottom:2px}
.node-management-dialog .node-enrollment-grid>div{min-width:0}.node-management-dialog label{font-size:13px;font-weight:600}
.node-management-dialog input:not([type=checkbox]),.node-management-dialog select{height:44px;padding:10px 12px;font-size:14px;border-color:#36506a;border-radius:9px}
.node-management-dialog textarea{padding:11px 12px;border-color:#36506a;border-radius:10px;font-size:13px;line-height:1.6;resize:vertical}
.node-management-dialog button{min-height:40px;padding:9px 14px;font-size:13px;white-space:nowrap}
.node-management-dialog .dialog-close{min-width:64px;height:38px;min-height:38px;border-radius:10px;padding:8px 14px;font-size:13px}
.management-form-footer{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:16px;border-top:1px solid #253b52;font-size:12px}.management-form-footer button{min-width:132px}
.node-management-dialog .node-list-head{margin:0 0 12px;align-items:center}.node-list-head h3{margin:0;font-size:15px}.node-list-head>span{font-size:12px}
.node-management-dialog .node-list{gap:12px}.node-management-dialog .node-row{grid-template-columns:minmax(0,1fr) auto;gap:12px 16px;padding:16px;background:#101f31;border-color:#2b4058}
.node-management-dialog .node-row strong{font-size:14px;overflow-wrap:anywhere}.node-management-dialog .node-row small{font-size:12px;line-height:1.65;margin-top:5px}
.node-management-dialog .node-row>span{font-size:12px;padding:5px 9px;border-radius:7px;background:#152e36;align-self:start;white-space:normal;text-align:center}
.node-management-dialog .node-actions{grid-column:1/-1;display:flex;justify-content:flex-end;gap:8px;padding-top:12px;border-top:1px solid #25394e;align-items:flex-start}
.node-management-dialog .node-actions form{width:auto}.node-management-dialog .node-actions button{min-height:36px;padding:7px 12px;font-size:12px}
.node-line-settings{min-width:0}.node-line-settings summary{cursor:pointer;list-style:none;border:1px solid #344e68;border-radius:9px;padding:7px 12px;min-height:36px;font-size:12px;background:#192c40;font-weight:650}.node-line-settings summary::marker{content:""}.node-line-settings summary::-webkit-details-marker{display:none}.node-line-settings summary::after{content:" +";color:var(--muted)}.node-line-settings[open]{flex-basis:100%;margin-top:4px}.node-line-settings[open] summary::after{content:" −"}
.node-management-dialog .node-line-form{display:grid;grid-template-columns:1fr 1.2fr .5fr;gap:12px;padding:16px 0 0}.node-line-form small{grid-column:1/-1}.node-line-form button{grid-column:1/-1;justify-self:end}
.external-editor{border:0;margin:0;padding:0;min-width:0}.external-import{padding:18px 20px;border:1px solid #2b4058;border-radius:14px;background:#0b1929}.external-import .management-section-head{margin-bottom:14px}.external-input-label{margin:0}.external-input-label textarea{display:block;min-height:104px;margin-top:7px}
.external-import-toolbar{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-top:14px}.external-import-toolbar label{width:min(100%,300px);margin:0}.external-import-toolbar select{display:block;margin-top:6px}.external-import-toolbar button{height:44px}
.external-list-heading{margin:24px 0 12px}.external-count{flex-shrink:0;font-size:12px;border:1px solid #324b64;border-radius:7px;background:#13283d;padding:4px 9px;color:#afc3dc;font-variant-numeric:tabular-nums}
.external-node-list{display:grid;gap:12px}.external-node-list:empty::before{content:"暂无外部节点，请先导入链接";padding:28px 16px;text-align:center;color:var(--muted);border:1px dashed #36506a;border-radius:12px;font-size:13px}
.external-node-card{min-width:0;border:1px solid #2b4058;border-radius:13px;background:#101f31;padding:16px 18px}.external-node-heading{display:flex;align-items:center;gap:10px;margin-bottom:14px;min-width:0}.external-protocol{color:#9bc3ff;font-size:10px;letter-spacing:.04em;font-weight:700;background:#18314d;border:1px solid #2e4b6c;padding:3px 7px;border-radius:5px}.external-node-heading code{font-size:12px;color:var(--muted);overflow-wrap:anywhere;min-width:0}
.external-node-fields{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.4fr);gap:16px}.external-node-fields label{margin:0;min-width:0}.external-node-fields input,.external-node-fields textarea{display:block;margin-top:7px}.external-node-fields textarea{min-height:76px}.field-optional{font-size:11px;color:var(--muted);font-weight:400;margin-left:5px}
.external-node-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:14px;padding-top:12px;border-top:1px solid #25394e}.node-management-dialog .external-enabled{display:flex;align-items:center;gap:8px;margin:0;font-size:12px;white-space:nowrap}.external-enabled input[type=checkbox]{width:16px;height:16px;min-height:0;margin:0;accent-color:var(--accent)}
.external-node-actions{display:flex;gap:6px}.node-management-dialog .external-node-actions button{min-height:32px;padding:5px 10px;font-size:12px}.node-management-dialog .external-remove{color:#e8a5b0;background:transparent;border-color:#63414f}
.external-preview-result{font-size:13px;overflow-wrap:anywhere;line-height:1.65}.external-preview-result:not(:empty){padding:14px 16px;margin-top:16px;background:#10283a;border:1px solid #2d4a62;border-radius:10px}.external-preview-result p{margin:0}.external-preview-result ul{margin:8px 0 0;padding-left:20px}
.external-publish-bar{position:sticky;bottom:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:20px -24px -24px;padding:16px 24px;border-top:1px solid #2b4058;background:#102034;box-shadow:0 -8px 24px rgba(4,12,23,.18)}.external-publish-bar p{margin:0;font-size:12px}.external-publish-bar p span{font-size:11px;color:#8195ad}.external-publish-bar>div{display:flex;gap:8px}
@media(max-width:760px){.node-management-dialog .node-enrollment-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.node-management-dialog .node-list-head{align-items:flex-start}.node-management-dialog .node-line-form{grid-template-columns:1fr 1fr}.node-line-form label:last-of-type{grid-column:1/-1}}
@media(max-width:540px){.node-management-dialog{width:calc(100% - 16px);max-height:calc(100dvh - 16px)}.node-management-dialog .dialog-head{padding:16px 18px;margin-bottom:16px}.node-management-dialog .dialog-head h2{font-size:19px}.node-management-dialog .dialog-head p{font-size:12px}.node-management-dialog .node-enrollment-grid{grid-template-columns:1fr;gap:14px;padding:16px}.management-section-head{align-items:flex-start}.management-section-head>span{font-size:11px;text-align:right}.management-form-footer{flex-direction:column;align-items:stretch;gap:10px}.management-form-footer button{width:100%}.node-management-dialog .node-list-head{gap:5px}.node-management-dialog .node-row{padding:14px;gap:10px}.node-management-dialog .node-actions{justify-content:flex-start;flex-wrap:wrap}.node-management-dialog .node-actions form{flex:1 1 auto}.node-management-dialog .node-actions form button{width:100%}.node-line-settings{flex:1 1 auto}.node-line-settings summary{text-align:center}.node-management-dialog .node-line-form{grid-template-columns:1fr}.external-import{padding:16px}.external-import-toolbar{flex-direction:column;align-items:stretch;gap:12px}.external-import-toolbar label{width:100%}.external-node-card{padding:14px}.external-node-fields{grid-template-columns:1fr;gap:12px}.external-node-heading{gap:8px}.external-node-heading code{font-size:11px}.external-node-footer{flex-wrap:wrap;gap:10px}.external-node-actions{margin-left:auto}.external-publish-bar{bottom:0;margin:18px -18px -18px;padding:14px 18px;flex-direction:column;align-items:stretch;gap:10px}.external-publish-bar p br,.external-publish-bar p span{display:none}.external-publish-bar>div{display:grid;grid-template-columns:1fr 1.3fr}.external-publish-bar button{padding:9px 8px}.external-list-heading{margin-top:20px}}

.machine-budget-head{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(145px,1fr) auto;gap:16px;align-items:center}.machine-budget-head>div:first-child{min-width:0}.machine-ip{overflow-wrap:anywhere}.machine-speed{min-width:0}.machine-speed-values{display:flex;justify-content:space-between;gap:8px;font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap}.machine-speed-values [data-speed-rx]{color:#58d6bd}.machine-speed-values [data-speed-tx]{color:#a6bbff}.machine-speed svg{display:block;width:100%;height:42px;overflow:visible}.machine-speed svg path{fill:none;vector-effect:non-scaling-stroke}.speed-grid{stroke:#283c53;stroke-width:.7}.speed-rx-line{stroke:#58d6bd;stroke-width:1.6}.speed-tx-line{stroke:#a6bbff;stroke-width:1.6}.machine-speed small{font-size:10px!important;color:#8fa1b7;text-align:right;line-height:1.2}.machine-speed[data-stale="true"] svg{opacity:.35}.machine-reset-check{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.line-check-button{font-size:12px;min-height:30px;padding:4px 9px;background:#16283d;border:1px solid #304760;color:#b7c8df;border-radius:8px}.line-check-button.ok{color:#58d6bd;border-color:#357c6b;background:#132d2c}.line-check-button.warning{color:#f1ce82}.line-check-button.bad{color:#ffacb5;border-color:#85404b;background:#351e2a}.line-check-dialog{width:min(740px,calc(100% - 24px));max-height:calc(100dvh - 32px)}.line-check-dialog .dialog-shell{overflow:auto}.line-check-dialog h3{font-size:15px;margin:0 0 8px}.line-check-dialog p{font-size:13px;line-height:1.7}.line-check-sections{display:grid;grid-template-columns:1fr 1fr;gap:20px}.line-check-sections section{min-width:0}.line-check-evidence{font-size:12px;line-height:1.8;margin:7px 0;overflow-wrap:anywhere}.line-check-dialog form{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.line-check-dialog [data-check-action]{font-size:12px}
@media(max-width:1150px) and (min-width:961px){.machine-budget-head{grid-template-columns:minmax(0,1fr) auto}.machine-speed{grid-row:2;grid-column:1/-1}.machine-speed svg{height:36px}}
@media(max-width:600px){.machine-budget-head{grid-template-columns:minmax(0,1fr) auto;gap:10px}.machine-speed{grid-row:2;grid-column:1/-1}.machine-speed svg{height:42px}.line-check-sections{grid-template-columns:1fr}.machine-reset-check{gap:4px}.line-check-button{font-size:11px}.line-check-dialog .dialog-shell{padding:18px}}
/* Selected deep-blue console: scoped to the authenticated dashboard. */
body:has(.console-sidebar){background:#081326;--surface:#0d1b30;--surface-2:#122239;--accent:#6456db;--line:#273954;--success:#39d6b5}
body:has(.console-sidebar) main{width:auto;max-width:1800px;margin:0 24px 40px 230px}
.console-sidebar{position:fixed;inset:0 auto 0 0;width:206px;padding:25px 14px;background:#0c1730;border-right:1px solid #293d60;display:flex;flex-direction:column;z-index:5}
.console-brand{color:#f3f7ff;font-size:21px;font-weight:750;text-decoration:none;white-space:nowrap}.console-brand b{color:#60deed;font-size:30px;font-style:italic;margin-right:5px}.console-sidebar p{font-size:12px;color:#b6c4dc;margin:4px 0 32px 8px}.console-sidebar nav{display:grid;gap:9px}.console-sidebar nav a{display:block;border:1px solid transparent;border-radius:10px;padding:12px 20px;color:#cdd7ec;text-decoration:none;font-size:15px}.console-sidebar nav a:hover{background:#162640}.console-sidebar nav a[aria-current=page]{background:#292968;border-color:#47429a;color:white}.console-sidebar>small{margin-top:auto;padding:16px 8px;color:#8c9dbb;font-size:11px}
body:has(.console-sidebar) .topbar{background:transparent;border:0;border-bottom:1px solid var(--line);border-radius:0;padding:15px 0;margin:0;gap:14px;flex-wrap:wrap}body:has(.console-sidebar) .topbar h1{font-size:28px;margin:0}.topbar .pill{font-size:11px;border:0;background:transparent;min-height:30px;padding:3px}.topbar button{font-size:12px;padding:7px 10px}.topbar .topbar-action{display:none}
[data-console-views]{display:none!important}body[data-console-view=overview] [data-console-views~=overview],body[data-console-view=nodes] [data-console-views~=nodes],body[data-console-view=users] [data-console-views~=users],body[data-console-view=subscriptions] [data-console-views~=subscriptions],body[data-console-view=servers] [data-console-views~=servers],body[data-console-view=settings] [data-console-views~=settings]{display:block!important}
body[data-console-view=overview] .metrics{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr));gap:0;margin:12px 0 18px}.metrics .metric{border:0;border-radius:0;box-shadow:none;background:transparent;padding:8px 24px;position:relative}.metrics .metric+ .metric{border-left:1px solid #334a70}.metrics .metric>strong{font-size:27px;margin:0;white-space:nowrap}.metrics .metric small{font-size:10px}.rate-rx{color:#55e1db}.rate-tx{color:#b6a0ff}
.aggregate-chart{padding:14px 18px!important}.aggregate-chart .section-head{border:0;padding:0;margin-bottom:12px;align-items:center}.aggregate-chart h2{font-size:18px}.aggregate-chart h2 small{font-size:13px;font-weight:400}.aggregate-chart .section-head>span{font-size:12px}.aggregate-plot{position:relative;padding-left:58px}.aggregate-plot>span{position:absolute;left:0;top:0;font-size:10px;color:var(--muted);max-width:55px}.aggregate-plot svg{width:100%;height:160px;display:block}.aggregate-plot path{fill:none;vector-effect:non-scaling-stroke}.aggregate-plot .speed-rx-line,.aggregate-plot .speed-tx-line{stroke-width:2}.aggregate-legend{display:flex;gap:18px;justify-content:flex-end;font-size:10px;color:var(--muted);margin-top:8px}.aggregate-legend>span:first-child{margin-right:auto}
body:has(.console-sidebar) .card{border-radius:12px}.machine-stats{padding:0!important;background:transparent;border:0;box-shadow:none}.machine-stats .machine-section-head{border:0;padding:5px 0;margin:0 0 10px;align-items:center}.machine-section-head h2{font-size:19px}.machine-count{border:0}.machine-budget-list{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:12px!important}.machine-budget-row{background:var(--surface)!important;border-radius:12px!important;padding:14px!important;overflow:hidden}.machine-budget-head{grid-template-columns:minmax(0,1fr) auto;gap:8px!important}.machine-budget-head>div:first-child>strong{font-size:16px}.machine-budget-head>div:first-child>small{font-size:10px}.machine-ip{font-size:10px;display:block}.machine-online{font-size:11px!important}.machine-online strong{font-size:17px}.machine-speed{grid-column:1/-1;grid-row:2;width:100%;margin:6px 0}.machine-speed-values{font-size:12px}.machine-speed svg{height:46px}.machine-budget-usage>strong{font-size:12px!important}.machine-budget-usage>span{font-size:10px!important}.machine-budget-meta{gap:6px!important;margin-top:10px!important;align-items:flex-end!important}.machine-reset-check{gap:6px}.machine-reset-check small{font-size:10px!important}.machine-budget-meta>button{font-size:11px!important;padding:6px 9px!important;white-space:nowrap}.machine-budget-row progress{height:6px!important}.machine-budget-usage [data-machine-forecast]{font-size:10px;font-weight:400}.line-check-button{font-size:10px;min-height:26px;padding:3px 7px}
.traffic-card{padding:14px!important}.traffic-card .section-head{border:0;margin:0 0 8px;padding:0}.traffic-card h2{font-size:19px}.traffic-card p{font-size:11px;margin:0}.rank-list{gap:0}.rank-row{grid-template-columns:60px minmax(100px,1fr) 65px 125px minmax(100px,2fr);border:0;border-bottom:1px solid #20334e;background:transparent;border-radius:0;padding:7px 10px;gap:12px;font-size:13px}.rank-header{background:#15243c;color:var(--muted);font-size:11px}.rank-number{background:#4b407b;border-radius:5px;width:32px;text-align:center;font-size:12px}.rank-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rank-type{color:#cab6f1;font-size:11px}.rank-traffic{white-space:nowrap}.rank-row progress{width:100%;height:7px;accent-color:#9270ec}.rank-row progress::-webkit-progress-value{background:#9270ec}
body[data-console-view=servers] .dashboard-trio{display:grid!important;grid-template-columns:1.3fr 1fr;margin-top:20px}.server-scope,.server-maintenance{grid-column:1/-1}.server-scope{margin:0}.server-maintenance p{font-size:12px}.server-maintenance p:last-child{margin:16px 0 0}#users,#subscriptions,#settings{margin-top:20px}.console-sidebar~#nodes{scroll-margin-top:15px}
@media(min-width:1800px){body:has(.console-sidebar) main{margin-left:250px}}
@media(max-width:1180px){.machine-budget-list{grid-template-columns:repeat(2,minmax(0,1fr))!important}.metrics .metric{padding:8px 12px}.metrics .metric>strong{font-size:21px}.topbar .pill{display:none}body[data-console-view=servers] .dashboard-trio{grid-template-columns:1fr}.rank-row{grid-template-columns:40px minmax(70px,1fr) 48px 100px minmax(60px,1fr);gap:8px}}
@media(max-width:760px){body:has(.console-sidebar) main{margin:0 12px 24px}.console-sidebar{position:static;width:auto;padding:12px 0;border:0;background:transparent}.console-brand{font-size:19px}.console-sidebar p,.console-sidebar>small{display:none}.console-sidebar nav{display:flex;gap:6px;overflow-x:auto;margin-top:10px;padding-bottom:4px}.console-sidebar nav a{padding:9px 12px;white-space:nowrap;font-size:12px}.console-sidebar~.topbar{padding:6px 0 12px}.topbar h1{font-size:24px!important}.metrics .metric{padding:6px 8px}.metrics .metric>strong{font-size:18px}.metrics .metric small{display:none}.metrics .metric>span{font-size:11px}.aggregate-chart .section-head{align-items:flex-start;flex-direction:column;gap:2px}.aggregate-plot svg{height:130px}.aggregate-legend{gap:9px}.machine-budget-list{grid-template-columns:1fr!important}.rank-row{grid-template-columns:30px minmax(55px,1fr) 40px 90px;gap:5px;padding:8px 4px}.rank-row>progress,.rank-header>span:last-child{display:none}.rank-row{font-size:11px}.traffic-card .section-head p{font-size:10px}.machine-section-head .button-row{gap:2px}.machine-section-head h2{font-size:16px}.machine-count{font-size:10px;padding:2px}body[data-console-view=overview] .metrics{grid-template-columns:repeat(3,minmax(0,1fr));row-gap:10px}.metrics .metric:nth-child(4){border-left:0}.aggregate-legend>span:last-child{max-width:120px;text-align:right}.server-scope{font-size:12px}}

body:has(.console-sidebar) .topbar{min-height:60px;box-shadow:none}.topbar::after,body:has(.console-sidebar)::before,.metrics .metric::before{display:none}.metrics .metric{min-height:70px}.rank-row{min-height:32px}.topbar .pill{border:0;background:transparent}.topbar .pill:last-of-type{display:none}.console-sidebar nav a{display:flex;align-items:center;gap:14px}.console-sidebar nav svg{width:20px;height:20px;flex-shrink:0}.machine-speed svg{max-height:46px}body:has(.console-sidebar) button:not(.secondary):not(.danger):not(.warning):not(.success):not(.ghost):not(.line-check-button){background:#5e50cc}.aggregate-chart{background:#0d1b30}.machine-section-head h2{font-size:19px}.traffic-card{background:#0d1b30}.skip-link:not(:focus){clip-path:inset(100%)}

body:has(.console-sidebar) .topbar{padding:8px 0}.metrics .metric>small:not(.metric-warning){display:none}.metrics .metric-warning{font-size:9px}.machine-speed small{display:none}.machine-speed svg{height:34px;max-height:34px}.machine-speed{margin:2px 0}.machine-budget-row{padding:12px!important}.machine-budget-head{gap:6px!important}.machine-budget-head>div:first-child>small{font-size:9px}.machine-budget-meta>button{min-height:30px}.aggregate-plot svg{height:150px}.console-sidebar{isolation:isolate}.console-brand{flex-shrink:0}.console-sidebar nav a{min-height:44px}

@media(max-width:760px){.console-sidebar nav{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));overflow:visible;gap:4px}.console-sidebar nav a{padding:9px 6px;font-size:12px;gap:6px;justify-content:center}.console-sidebar nav svg{width:17px;height:17px}.console-sidebar~.topbar{align-items:center}.console-sidebar~.topbar h1{width:auto;order:0}.console-sidebar~.topbar .logout-form{flex:0 0 auto}.machine-budget-meta>button,.line-check-button{min-height:44px}.aggregate-chart .section-head{margin-bottom:8px}}

/* Desktop rate charts follow the selected reference: labeled area plot and
   compact per-node chart with rates in a separate right-hand column. */
@media(min-width:761px){
.aggregate-chart{padding:13px 20px 10px!important;position:relative}.aggregate-chart .section-head{margin-bottom:18px;align-items:center}.aggregate-chart h2{font-size:20px;margin:0}.aggregate-chart h2 small{font-size:14px}.aggregate-current{display:flex;align-items:center;gap:18px;font-size:12px}.aggregate-current>span+span{padding-left:18px;border-left:1px solid #344664}.aggregate-current strong{font-size:14px}.aggregate-plot{display:grid;grid-template-columns:68px minmax(0,1fr) 66px;gap:0;padding:0;margin:0 0 2px}.aggregate-y-axis{position:relative;height:140px}.aggregate-y-axis>span{position:absolute;right:10px;transform:translateY(-50%);font-size:11px;white-space:nowrap;color:#c6d1e5}.aggregate-canvas{min-width:0}.aggregate-canvas svg{height:140px;width:100%;overflow:visible;border:1px solid #263c59}.aggregate-canvas .speed-grid{stroke:#354968;stroke-dasharray:3 3;stroke-width:.7}.aggregate-canvas .speed-rx-line{stroke:#00ddc7;stroke-width:2.5}.aggregate-canvas .speed-tx-line{stroke:#b49bff;stroke-width:2.5}.aggregate-plot .aggregate-rx-area{fill:url(#aggregate-rx-fill);stroke:none}.aggregate-plot .aggregate-tx-area{fill:url(#aggregate-tx-fill);stroke:none}.aggregate-x-axis{position:relative;height:26px;margin-top:5px}.aggregate-x-axis>span{position:absolute;transform:translateX(-50%);color:#c6d1e5;font-size:11px}.aggregate-series-key{display:flex;flex-direction:column;gap:10px;padding:0 0 0 16px;font-size:12px}.aggregate-series-key>span{display:flex;align-items:center;gap:6px;white-space:nowrap}.aggregate-series-key>span::before{content:"";width:18px;height:3px;background:currentColor;border-radius:3px}.aggregate-state{display:block;text-align:right;font-size:10px;line-height:14px}.machine-speed{grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);display:grid;gap:16px;align-items:center;margin:12px 0 8px}.machine-speed-values{grid-column:2;grid-row:1;display:flex;flex-direction:column;gap:3px;border-left:1px solid #314665;padding-left:16px;justify-content:center;font-size:15px;font-weight:700;line-height:1.4}.machine-speed svg{grid-column:1;grid-row:1;height:48px;max-height:48px;min-width:0;width:100%;overflow:hidden}.machine-speed svg .speed-grid{stroke:#283b55;stroke-dasharray:none}.machine-speed svg .speed-rx-area{fill:#00ddc7;fill-opacity:.08}.machine-speed svg .speed-tx-area{fill:#b49bff;fill-opacity:.1}.machine-speed svg .speed-rx-line{stroke:#00ddc7;stroke-width:2}.machine-speed svg .speed-tx-line{stroke:#b49bff;stroke-width:2}.machine-speed-values [data-speed-rx]{color:#00ddc7}.machine-speed-values [data-speed-tx]{color:#b49bff}
}

@media(min-width:761px){body[data-console-view=overview] .machine-forecast-detail,body[data-console-view=overview] .machine-budget-usage>span{display:none}.aggregate-chart .section-head{margin-bottom:14px}.aggregate-state{line-height:12px}.machine-section-head{margin-bottom:8px!important}.console-sidebar~#nodes .machine-stats{margin-bottom:14px}}

@media(min-width:761px){.console-config-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.console-config-grid>.card{margin:0;display:flex;flex-direction:column;align-items:flex-start;padding:24px}.console-config-grid h2{font-size:21px;margin:8px 0 14px}.console-config-grid p{font-size:14px;line-height:1.8;margin:0 0 24px}.console-config-grid button,.console-config-grid .button{margin-top:auto;min-width:150px}.config-kicker{font-size:10px;font-weight:700;letter-spacing:.12em;color:#a59aff}.module-intro{margin:24px 0 20px;font-size:14px}.console-settings-list{width:100%;margin:0 0 24px}.console-settings-list>div{display:flex;gap:16px;justify-content:space-between;border-bottom:1px solid #233650;padding:14px 0;font-size:14px}.console-settings-list dt{color:var(--muted)}.console-settings-list dd{margin:0;text-align:right;overflow-wrap:anywhere}body[data-console-view=nodes] .machine-section-head h2,body[data-console-view=users] .user-group-heading>h2{display:none}body[data-console-view=nodes] .machine-section-head{justify-content:flex-end;margin-top:12px}.user-section-head{align-items:center}}

@media(min-width:761px){.rank-row{font-size:14px}.rank-header{font-size:12px}.machine-budget-usage>strong{font-size:14px!important}.aggregate-y-axis>span,.aggregate-x-axis>span{font-size:12px}.aggregate-series-key{font-size:13px}}


/* Desktop node operations and compact enrollment. */
.node-server-tools{display:none}
body[data-console-view=nodes] .node-server-tools{display:block;border-top:1px solid #2b4058;margin-top:18px;padding-top:16px}
.node-resource-head{display:flex;justify-content:space-between;align-items:center;font-size:13px;margin-bottom:14px}.node-resource-head a{font-size:12px;color:#b6a0ff}
.node-resource-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-bottom:10px}.node-resource-grid>div{display:grid;gap:8px}.node-resource-grid span{font-size:12px}.node-resource-grid strong{font-size:21px}.node-resource-grid progress,.resource-empty{height:4px;width:100%;border-radius:4px;background:#293c56}.node-quick-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}.node-quick-actions button{font-size:12px!important;padding:9px 12px!important;min-height:36px}.node-quick-actions form{margin:0}.node-server-tools>small{font-size:11px}
@media(min-width:761px){body[data-console-view=nodes] .machine-budget-list{grid-template-columns:repeat(2,minmax(0,1fr))!important}body[data-console-view=nodes] .machine-budget-row{padding:22px!important}.node-onboarding-dialog{width:min(1040px,94vw)}.node-onboarding-dialog .dialog-shell{padding:0 28px 28px}.node-onboarding-dialog .dialog-head{margin:0 -28px 20px;padding:24px 28px}.node-onboarding-dialog .dialog-head h2{font-size:24px}.node-onboarding-dialog .dialog-head p{font-size:13px;margin:8px 0 0}.node-onboarding-dialog .notice{padding:14px 18px;font-size:13px;line-height:1.7;margin:0 0 20px}.node-onboarding-dialog .notice strong{margin-right:8px}.node-onboarding-dialog .node-enrollment-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 24px;align-items:start;padding:22px;margin:0 0 26px}.node-enrollment-grid>div{min-width:0}.node-onboarding-dialog label{font-size:13px;margin:0 0 8px}.node-onboarding-dialog input,.node-onboarding-dialog select{width:100%;height:44px;font-size:14px;padding:10px 12px}.node-onboarding-dialog .node-enrollment-grid small{font-size:11px}.node-onboarding-dialog .node-enrollment-grid>button{order:7;grid-column:1/-1;justify-self:end;padding:12px 28px;margin:0}.node-onboarding-dialog .node-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px 20px;padding:18px}.node-onboarding-dialog .node-row>div:first-child{grid-column:1}.node-onboarding-dialog .node-row>span{grid-column:2;grid-row:1}.node-onboarding-dialog .node-actions{grid-column:1/-1;justify-content:flex-end;border-top:1px solid #2b4058;padding-top:12px}.node-onboarding-dialog .node-row strong{font-size:15px}.node-onboarding-dialog .node-row small{font-size:12px;line-height:1.7}.node-onboarding-dialog .node-list-head{align-items:center;margin-bottom:12px}.node-onboarding-dialog .node-list-head span{font-size:11px}.server-details-dialog{width:min(1100px,94vw)}.server-details-dialog .dashboard-trio{display:grid;grid-template-columns:1fr;gap:16px}.server-details-dialog .server-scope{font-size:13px}}

@media(min-width:761px){body[data-console-view=nodes] .machine-budget-list{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:12px}body[data-console-view=nodes] .machine-budget-row{padding:16px!important}.node-server-tools{margin-top:12px!important;padding-top:12px!important}.node-resource-head{margin-bottom:10px}.node-resource-grid{gap:12px;margin-bottom:8px}.node-resource-grid>div{gap:5px}.node-resource-grid strong{font-size:17px}.node-quick-actions{gap:6px;margin-top:12px}.node-quick-actions button{font-size:11px!important;min-height:30px;padding:6px 8px!important}.node-server-tools>small{display:block;font-size:10px;line-height:1.5}[data-operation-status]{margin-top:6px;color:#b6a0ff}.machine-budget-usage>span{font-size:10px!important}.machine-budget-head{margin-bottom:12px!important}
#edit-user-dialog{width:min(720px,92vw)}#edit-user-dialog .dialog-shell,#subscription-dialog .dialog-shell{padding:0 24px 24px}#edit-user-dialog .dialog-head,#subscription-dialog .dialog-head{margin:0 -24px 20px;padding:20px 24px}#edit-user-dialog .dialog-head h2,#subscription-dialog .dialog-head h2{font-size:23px}#edit-user-dialog .dialog-head p,#subscription-dialog .dialog-head p{font-size:13px;margin:6px 0 0}#edit-user-dialog label,#subscription-dialog label{font-size:13px;margin:0 0 7px}#edit-user-dialog input,#subscription-dialog input{min-height:42px;padding:10px 12px;font-size:14px}#edit-user-dialog .create-grid{gap:16px;align-items:start}#edit-user-dialog .edit-fields{padding:0;margin:0;border:0;align-items:start}#edit-user-dialog small,#edit-user-dialog [data-edit-user-status]{font-size:11px;line-height:1.5;margin:6px 0 0}#edit-user-dialog .notice{font-size:11px;padding:10px 12px;margin:14px 0 0}#edit-user-dialog .wide[type=submit]{justify-self:end;width:auto;min-width:140px}#edit-user-dialog .edit-lookup{display:grid;grid-template-columns:1fr auto;gap:10px}#edit-user-dialog button,#subscription-dialog button{font-size:13px;padding:10px 18px;min-height:40px}#subscription-dialog{width:min(900px,94vw)}.subscription-intro{font-size:12px;line-height:1.6;color:var(--muted);margin:0 0 14px}.hopping-settings{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 18px!important;margin:0 0 18px!important;font-size:13px}.hopping-settings small{display:block;font-size:11px;margin-top:5px;color:var(--muted)}.subscription-node-row{padding:18px;gap:14px 20px;margin:12px 0}.subscription-node-row legend{font-size:13px}.subscription-node-row label:has(input[type=checkbox]){display:flex;align-items:center;gap:8px;margin:0}.subscription-node-row input[type=checkbox]{min-height:0;width:16px;height:16px}.subscription-node-row [data-sub-node-remove]{justify-self:end;padding:8px 12px;color:#e7a0b3;background:transparent;min-height:34px}#subscription-dialog .credential-actions{justify-content:flex-end}#subscription-dialog .credential-actions button{flex:0 0 auto}}

@media(min-width:761px){body[data-console-view=overview] .metrics{grid-template-columns:repeat(8,minmax(0,1fr))}.metrics .metric{padding:8px 12px}.metrics .metric>strong{font-size:20px}.metrics .metric>span{font-size:12px}.metrics .metric small{font-size:9px}.machine-budget-usage>strong{display:flex;justify-content:space-between;align-items:center;gap:10px;width:100%}.machine-budget-usage [data-machine-budget-usage]{flex:0 0 auto}body[data-console-view=overview] .machine-forecast-detail,.machine-forecast-detail{display:block!important;font-size:10px;font-weight:400;text-align:right;line-height:1.5;max-width:46%;color:var(--muted)}.panel-control{margin-top:18px;padding:18px 22px}.panel-control h2{font-size:18px}.panel-control .section-head{margin-bottom:14px}.panel-control-body{display:flex;align-items:center;gap:28px}.panel-control button{font-size:12px;padding:8px 18px;min-height:34px}.panel-control-info{flex:1;display:grid;grid-template-columns:1fr 1fr 1.5fr;gap:20px}.panel-control-info>div{display:grid;gap:5px;border-left:1px solid #2b4058;padding-left:20px}.panel-control-info span,.panel-control-info small{font-size:11px;color:var(--muted)}.panel-control-info strong{font-size:14px}.node-resource-grid>div{grid-template-rows:16px 23px 4px 15px;align-content:start}.node-resource-grid [data-resource-detail]{font-size:10px;color:var(--muted);line-height:1.5;white-space:nowrap}.resource-uptime{display:flex;gap:10px;align-items:center;font-size:10px;color:var(--muted);margin:2px 0 8px}.resource-uptime strong{font-weight:500;color:#c5d3e5}}
@media(min-width:761px) and (max-width:1440px){body[data-console-view=overview] .metrics{grid-template-columns:repeat(4,minmax(0,1fr));row-gap:12px}.metrics .metric:nth-child(5){border-left:0}.node-resource-grid{grid-template-columns:.65fr 1fr 1fr;gap:8px}.panel-control-body{gap:16px}}

@media(min-width:761px){.panel-port-action{display:flex;align-items:center;gap:10px}.panel-port-action button{padding:5px 10px!important;min-height:28px!important;font-size:11px!important;white-space:nowrap}.unified-port-bar{display:grid;grid-template-columns:auto 110px auto;align-items:center;justify-content:start;gap:10px 14px;margin:14px 0 18px;padding:14px 16px;background:#102238;border-radius:10px}.unified-port-bar label{margin:0!important}.unified-port-bar small{grid-column:1/-1;font-size:11px;color:var(--muted)}
#migration-dialog{width:min(960px,94vw)}#migration-dialog .dialog-shell{padding:0 24px 22px}#migration-dialog .dialog-head{margin:0 -24px 18px;padding:20px 24px}#migration-dialog .dialog-head h2{font-size:23px}#migration-dialog .dialog-head p{font-size:13px;margin:6px 0 0}.backup-summary{display:flex;gap:14px;align-items:baseline;font-size:12px;line-height:1.7;padding:12px 16px;background:#19283b;border:1px solid #354862;border-radius:10px;margin-bottom:18px}.backup-summary strong{white-space:nowrap;color:#ebc68b}.backup-summary span{color:#c3cede}#migration-dialog .migration-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:0}.backup-action-card{display:flex;flex-direction:column;padding:20px!important;min-width:0}#migration-dialog .backup-action-card h3{font-size:19px;margin:8px 0 10px}#migration-dialog .backup-action-card p{font-size:12px;line-height:1.7;margin:0 0 14px}.backup-kicker{color:#b5a6ff;font-size:11px}.backup-content-note{font-size:12px;color:#b5c2d4;line-height:1.8;margin-bottom:18px}.backup-action-card form{margin-top:auto;display:flex;flex-direction:column;gap:10px;align-items:flex-start}#migration-dialog button{font-size:13px;min-height:40px;padding:10px 18px}#migration-dialog label{font-size:12px;margin:0}#migration-dialog input[type=file]{font-size:12px;min-height:42px;padding:9px;width:100%;margin:0 0 4px}#migration-dialog input::file-selector-button{font-size:12px;padding:5px 8px;border:0;border-radius:5px;margin-right:8px}#migration-dialog [data-restore-form]{width:100%}#migration-dialog [data-restore-status]:empty{display:none}.backup-help{margin:18px 0;border:1px solid #2c4059;border-radius:10px;padding:14px 16px;font-size:12px}.backup-help summary{cursor:pointer;font-weight:600}.backup-help .migration-guide{display:block;margin-top:14px}.backup-help h3{font-size:13px;margin:14px 0 6px}.backup-help p,.backup-help li{font-size:12px;line-height:1.8;margin:6px 0}.backup-help ol{padding-left:20px}.offsite-backup-row{padding:0 4px;font-size:12px}.offsite-backup-row>div{display:flex;justify-content:space-between;gap:16px}.offsite-backup-row .advanced-help{margin-top:10px}.offsite-backup-row p{font-size:11px;line-height:1.7;overflow-wrap:anywhere}}

.chart-title-range{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.chart-range-buttons{display:flex;border:1px solid #334963;border-radius:8px;padding:3px;gap:3px}.chart-range-buttons button{font-size:11px;padding:5px 10px;min-height:26px;border:0!important;box-shadow:none!important;background:transparent!important}.chart-range-buttons button[aria-pressed=true]{background:#5143ac!important;color:white}.aggregate-canvas svg,.machine-speed svg{shape-rendering:geometricPrecision}
/* Selected panoramic chart: typography and geometry follow the desktop concept. */
@media(min-width:761px){
.aggregate-chart{padding:16px 20px 12px!important;border-radius:18px;background:#0b1c2d;border-color:#324f6c}
.aggregate-chart .section-head{gap:20px;margin-bottom:20px;flex-wrap:wrap}
.chart-title-range{gap:22px;flex-wrap:nowrap}.aggregate-chart h2{font-size:20px;white-space:nowrap}
.chart-range-buttons{padding:4px;border-radius:13px}.chart-range-buttons button{font-size:13px;padding:6px 12px;min-height:32px;border-radius:10px}
.chart-refresh{font-size:13px;color:#a7b9d0;border-left:1px solid #36516e;padding-left:20px;white-space:nowrap}
.aggregate-current{gap:20px;font-size:15px;margin-left:auto;white-space:nowrap}.aggregate-current strong{font-size:20px;letter-spacing:-.4px;font-variant-numeric:tabular-nums}.aggregate-current>span+span{padding-left:20px}
.aggregate-plot{grid-template-columns:78px minmax(0,1fr) 68px}.aggregate-canvas svg,.aggregate-y-axis{height:160px}
.aggregate-y-axis>span,.aggregate-x-axis>span{font-size:13px}.aggregate-canvas .speed-rx-line,.aggregate-canvas .speed-tx-line{stroke-width:2.6;stroke-linejoin:miter}
.aggregate-series-key{font-size:14px;gap:18px;padding-left:16px}.aggregate-x-axis{height:28px;margin-top:10px}
.aggregate-footer{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:6px;color:#9fb2cc}.aggregate-footer time{font-size:13px;white-space:nowrap}.aggregate-state{font-size:11px;line-height:16px}
}
@media(min-width:761px) and (max-width:1400px){.chart-refresh{display:none}.aggregate-current strong{font-size:20px}.chart-title-range{gap:16px}}

"""

PAGE_SCRIPT = """// Hash navigation preserves existing links and form endpoints.
function selectConsoleView() {
  if (!document.querySelector('.console-sidebar')) return;
  const titles = {overview:'总览',nodes:'节点管理',users:'用户管理',subscriptions:'订阅管理',settings:'设置'};
  let view = location.hash.slice(1);
  if (view === 'servers') { view = 'nodes'; history.replaceState(null, '', location.pathname+location.search+'#nodes'); }
  try {
    const returned = sessionStorage.getItem('hy2-console-return');
    sessionStorage.removeItem('hy2-console-return');
    if (!view && returned && Object.prototype.hasOwnProperty.call(titles, returned)) {
      view = returned; history.replaceState(null, '', location.pathname+location.search+'#'+view);
    }
  } catch (_) {}
  if (!Object.prototype.hasOwnProperty.call(titles, view)) view = location.search ? 'users' : 'overview';
  document.body.dataset.consoleView = view;
  window.dispatchEvent(new Event('consoleviewchange'));
  document.querySelector('[data-console-title]').textContent = titles[view];
  document.querySelectorAll('[data-console-nav]').forEach(function(link) {
    if (link.dataset.consoleNav === view) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  });
}
if (document.querySelector('.console-sidebar')) {
selectConsoleView();
window.addEventListener('hashchange', selectConsoleView);
window.addEventListener('popstate', selectConsoleView);
window.addEventListener('submit', function(event) {
  if (!event.defaultPrevented && event.target.method === 'post' && event.target.action.indexOf('/logout') === -1) {
    try { sessionStorage.setItem('hy2-console-return', document.body.dataset.consoleView || 'overview'); } catch (_) {}
  }
});
document.addEventListener('click', function(event) {
  const nav = event.target.closest('[data-console-nav]');
  if (nav && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault(); history.pushState(null, '', '#'+nav.dataset.consoleNav); selectConsoleView(); window.scrollTo({top:0,behavior:'instant'});
  }
  if (event.target.closest('[data-console-refresh]')) { event.preventDefault(); location.reload(); }
});
}
let chartRange = '5m';
let chartRangeVersion = 0;
function applyAggregateNetwork(payload) {
  const target = document.querySelector('[data-aggregate-rx]'); if (!target) return;
  const ids = Array.from(document.querySelectorAll('.machine-budget-row')).filter(function(card) { return card.querySelector('.machine-speed'); }).map(function(card) { return card.dataset.originId; });
  const streams = ids.map(function(id) { return payload.network[id]; });
  const now = Date.now()/1000;
  const dateLabel=document.querySelector('[data-chart-date]');if(dateLabel)dateLabel.textContent=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(now*1000));
  const valid = function(n) { return Number.isFinite(n) && n >= 0; };
  const fresh = streams.filter(function(n) { return n && n.fresh && Number.isFinite(n.observedAt) && valid(n.rx) && valid(n.tx) && now-n.observedAt >= -5 && now-n.observedAt <= 20; });
  const complete = streams.length > 0 && fresh.length === streams.length;
  ['rx','tx'].forEach(function(dir) {
    const rate = complete ? networkRate(fresh.reduce(function(sum,n) { return sum+n[dir]; },0)) : '—';
    document.querySelector('[data-total-'+dir+']').textContent = rate;
    document.querySelector('[data-chart-'+dir+']').textContent = rate;
  });
  document.querySelector('[data-aggregate-state]').textContent = complete ? '全部 '+streams.length+' 台 · 每 5 秒刷新' : '数据不完整 · '+fresh.length+'/'+streams.length+' 台可用';
  const daily = chartRange === 'today';
  const history = daily && payload.today ? payload.today : null;
  // Align the viewport to 60 sample slots, rather than wall-clock padding.
  const lastTimes=streams.map(n=>n && Array.isArray(n.points) && n.points.length ? n.points[n.points.length-1].at : NaN);
  const end=!daily && complete && lastTimes.every(Number.isFinite) ? Math.min(now,...lastTimes) : now;
  const start = daily ? (history ? history.start : Math.floor((now+28800)/86400)*86400-28800) : end-295;
  const span = Math.max(60, end-start);
  const interval = daily ? 60 : 5;
  const plotStreams = daily ? ids.map(id=>history && history.network[id]) : streams;
  if(daily) document.querySelector('[data-aggregate-state]').textContent += ' · 北京时间今日 · 分钟采样均值 · 无数据处留空';
  // Only sum aligned samples from every participating node. Gaps stay gaps.
  const dailyMaps=plotStreams.map(n=>new Map(n && Array.isArray(n.points)?n.points.map(p=>[p.at,p]):[]));
  const series = [];
  for (let at = start; at <= end+.001; at+=interval) {
    const samples = plotStreams.map(function(n,index) { if(daily){const p=dailyMaps[index].get(at);return p && valid(p.rx) && valid(p.tx)?p:null;} const point=n && Array.isArray(n.points) ? n.points.filter(function(p) { return p && p.at <= at && at-p.at < 10; }).sort(function(a,b) { return b.at-a.at; })[0] : null; return point && valid(point.rx) && valid(point.tx) ? point : null; });
    series.push({at:at, rx:samples.length && samples.every(Boolean) ? samples.reduce(function(s,p){return s+p.rx;},0) : null, tx:samples.length && samples.every(Boolean) ? samples.reduce(function(s,p){return s+p.tx;},0) : null});
  }
  const maximum = Math.max(1,...series.flatMap(function(p){return [p.rx,p.tx].filter(valid);}));
  const hasData = series.some(function(p) { return valid(p.rx); });
  const axis = document.querySelector('[data-aggregate-axis]');
  const times = document.querySelector('[data-aggregate-times]');
  axis.replaceChildren();
  times.replaceChildren();
  if (!hasData) {
    document.querySelectorAll('[data-aggregate-rx],[data-aggregate-tx],[data-aggregate-rx-area],[data-aggregate-tx-area],[data-aggregate-grid]').forEach(p=>p.setAttribute('d',''));
    document.querySelector('[data-aggregate-state]').textContent += ' · 当前范围暂无速率样本';
    return;
  }
  const unit = maximum*8 >= 1000000 ? 1000000 : 1000;
  const displayMax = maximum*8/unit;
  const magnitude = Math.pow(10, Math.floor(Math.log10(displayMax/6)));
  const step = [1,2,5,10].map(function(n) { return n*magnitude; }).find(function(n) { return n>=displayMax/6; });
  const ceiling = Math.ceil(displayMax/step)*step;
  const scale = ceiling*unit/8;
  let grid = '';
  for (let value=0; value<=ceiling+step/2; value+=step) {
    const position = 100-value/ceiling*100;
    const tick = document.createElement('span'); tick.style.top=position+'%';
    tick.textContent = Number(value.toPrecision(3))+' '+(unit===1000000?'Mbps':'Kbps');
    axis.appendChild(tick);
    grid+='M0 '+(position*1.6).toFixed(2)+'H1000 ';
  }
  const tickStep = daily ? (span>43200?14400:span>10800?3600:span>1800?1800:300) : 60;
  const firstTick = daily ? start : Math.ceil(start/60)*60;
  for (let at=firstTick; at<=end; at+=tickStep) {
    const x=(at-start)/span*100;
    if (x<0 || x>100) continue;
    const label=document.createElement('span');label.style.left=x+'%';
    label.textContent=new Date(at*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai'});times.appendChild(label);
    grid+='M'+(x*10).toFixed(2)+' 0V160 ';
  }
  document.querySelector('[data-aggregate-grid]').setAttribute('d',grid);
  ['rx','tx'].forEach(function(dir) {
    let path='', prior=false;
    series.forEach(function(p) { if (!valid(p[dir])) {prior=false;return;} path+=(prior?'L':'M')+((p.at-start)/span*1000).toFixed(1)+' '+(160-p[dir]/scale*160).toFixed(1)+' ';prior=true; });
    document.querySelector('[data-aggregate-'+dir+']').setAttribute('d',path);
    document.querySelector('[data-aggregate-'+dir+'-area]').setAttribute('d',chartArea(path,160));
  });
}
document.addEventListener('click', function(event) {
  const button=event.target.closest('[data-chart-range]');if(!button || button.dataset.chartRange===chartRange)return;
  chartRange=button.dataset.chartRange;chartRangeVersion++;
  document.querySelectorAll('[data-chart-range]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.chartRange===chartRange)));
  document.querySelector('[data-chart-range-label]').textContent=chartRange==='today'?'（今日）':'（近 5 分钟）';
  document.querySelector('[data-aggregate-state]').textContent='正在加载…';
  document.querySelectorAll('[data-aggregate-rx],[data-aggregate-tx],[data-aggregate-rx-area],[data-aggregate-tx-area],[data-aggregate-grid]').forEach(p=>p.setAttribute('d',''));
  document.querySelector('[data-aggregate-axis]').replaceChildren();document.querySelector('[data-aggregate-times]').replaceChildren();
  document.querySelector('.aggregate-canvas svg').setAttribute('aria-label',chartRange==='today'?'今日全网网卡入站和出站速率':'最近 5 分钟全网网卡入站和出站速率');
  refreshLineMonitor();
});
function chartArea(path, baseline) {
  // Each continuous segment closes separately; never fill a telemetry gap.
  return (path.match(/M[^M]+/g)||[]).map(function(segment) {
    const numbers=segment.trim().split(/[ML ]+/).filter(Boolean).map(Number);
    return segment+'L'+numbers[numbers.length-2]+' '+baseline+'L'+numbers[0]+' '+baseline+'Z';
  }).join(' ');

}

let noticeTimer;
function notify(message, isError) {
  const dialogs = Array.from(document.querySelectorAll('dialog[open]'));
  const dialog = dialogs[dialogs.length - 1];
  if (isError && dialog) {
    let status = dialog.querySelector('[data-dialog-status]');
    if (!status) {
      status = document.createElement('p');
      status.dataset.dialogStatus = '';
      status.className = 'dialog-status';
      status.setAttribute('role', 'alert');
      dialog.appendChild(status);
    }
    status.textContent = message;
    status.scrollIntoView({block: 'nearest'});
    return;
  }
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
  const focused = document.activeElement;
  const dialogs = Array.from(document.querySelectorAll('dialog[open]'));
  (dialogs[dialogs.length - 1] || document.body).appendChild(buffer);
  try {
    buffer.focus();
    buffer.select();
    return document.execCommand('copy');
  } catch (_) {
    return false;
  } finally {
    buffer.remove();
    if (focused && focused.isConnected) focused.focus();
  }
}
class UnconfirmedRequestError extends Error {
  constructor() {
    super('连接中断或响应异常，操作结果尚未确认；请刷新页面核对状态后再操作');
  }
}
async function postJson(url, options, timeoutMs = 45000) {
  document.querySelectorAll('dialog[open] [data-dialog-status]').forEach(function(status) {
    status.remove();
  });
  const controller = new AbortController();
  const timeout = window.setTimeout(function() { controller.abort(); }, timeoutMs);
  try {
    let response;
    try {
      response = await fetch(url, {
        method: 'POST', credentials: 'same-origin', ...options, signal: controller.signal
      });
    } catch (_) {
      throw new UnconfirmedRequestError();
    }
    if (response.status === 401) {
      window.location.assign('/login');
      throw new Error('登录已失效，正在返回登录页');
    }
    if (response.redirected) throw new Error('登录状态已变化，请重新登录');
    const contentType = response.headers.get('Content-Type') || '';
    if (!contentType.toLowerCase().includes('application/json')) {
      throw new UnconfirmedRequestError();
    }
    let payload;
    try { payload = await response.json(); } catch (_) { throw new UnconfirmedRequestError(); }
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new UnconfirmedRequestError();
    if (!response.ok) throw new Error(payload.error || '操作失败，请刷新页面后重试');
    return payload;
  } finally {
    window.clearTimeout(timeout);
  }
}
function submitInlineForm(form) {
  return postJson(form.action, {
    headers: {'Accept': 'application/json'},
    body: new URLSearchParams(new FormData(form))
  });
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
    canvas.setAttribute('aria-label', '订阅链接二维码');
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
  canvas.setAttribute('aria-label', String(name || '用户') + ' 的 订阅链接二维码');
  panel.hidden = false;
  saveButton.hidden = false;
}
function showCredentials(payload, withQr, refreshOnClose) {
  if (!payload || typeof payload.uri !== 'string' || !(payload.uri.startsWith('https://') || payload.uri.startsWith('http://'))) {
    throw new Error('订阅链接响应无效');
  }
  const dialog = document.getElementById('credentials-dialog');
  if (!dialog) throw new Error('订阅信息弹窗加载失败');
  clearCredentialsQr();
  if (withQr) drawCredentialsQr(payload.qr, payload.name);
  dialog.querySelector('[data-credentials-title]').textContent = String(payload.name || '用户') + ' 的订阅信息';
  dialog.querySelector('#credentials-uri').value = payload.uri;
  dialog.querySelector('[data-credentials-notice]').textContent = withQr
    ? '在客户端添加订阅；刷新可同步节点配置和剩余流量。链接仅供该用户使用。'
    : '关闭弹窗后会刷新当前用户列表。';
  dialog.dataset.refreshOnClose = refreshOnClose ? '1' : '0';
  dialog.showModal();
}
let editBaseline = '';
let editSelectedId = '';
let editLoadedName = '';
let editLoadSequence = 0;
function editValues() {
  const form = document.querySelector('[data-edit-user-form]');
  return JSON.stringify(['device_limit', 'traffic_limit_gb', 'used_traffic_gib', 'expires_at', 'starts_at'].map(function(name) {
    const field = form.elements.namedItem(name);
    return field ? (field.type === 'checkbox' ? field.checked : field.value) : null;
  }));
}
function canDiscardEdit() {
  if (document.querySelector('[data-edit-user-form]').dataset.saving === '1') return false;
  return !editSelectedId || editValues() === editBaseline || window.confirm('此用户有未保存的修改，确定放弃吗？');
}
function closeUserDialog(dialog) {
  if (dialog.id === 'edit-user-dialog' && !canDiscardEdit()) return;
  const creating = dialog.querySelector('[data-create-user-form]');
  if (creating && creating.dataset.saving === '1') return;
  dialog.close();
}
function clearEditUser() {
  editLoadSequence += 1;
  editSelectedId = '';
  editLoadedName = '';
  const form = document.querySelector('[data-edit-user-form]');
  form.action = '/users/0/edit';
  form.querySelector('[data-edit-user-name-input]').value = '';
  form.querySelector('[data-edit-user-fields]').disabled = true;
  form.querySelector('button[type="submit"]').disabled = true;
  form.querySelector('[data-edit-user-status]').textContent = '输入完整用户名后加载设置。';
  document.getElementById('edit-user-title').textContent = '编辑用户';
}
async function loadEditUser() {
  const form = document.querySelector('[data-edit-user-form]');
  const input = form.querySelector('[data-edit-user-name-input]');
  const status = form.querySelector('[data-edit-user-status]');
  if (form.dataset.saving === '1') return;
  if (!canDiscardEdit()) {
    input.value = editLoadedName;
    form.querySelector('button[type="submit"]').disabled = !editSelectedId;
    return;
  }
  const name = input.value.trim();
  if (!name) { status.textContent = '请输入完整用户名'; input.focus(); return; }
  const sequence = ++editLoadSequence;
  editSelectedId = '';
  editLoadedName = '';
  form.querySelector('[data-edit-user-fields]').disabled = true;
  form.querySelector('button[type="submit"]').disabled = true;
  status.textContent = '正在加载用户…';
  try {
    const user = await postJson('/users/lookup?name=' + encodeURIComponent(name), {method: 'GET'}, 15000);
    if (sequence !== editLoadSequence || !form.closest('dialog').open) return;
    editSelectedId = String(user.id);
    editLoadedName = user.name;
    input.value = user.name;
    document.getElementById('edit-user-title').textContent = '编辑 · ' + user.name;
    form.action = '/users/' + encodeURIComponent(user.id) + '/edit';
    ['generation', 'device_limit', 'traffic_limit_gb', 'used_traffic_gib'].forEach(function(key) {
      form.elements.namedItem(key).value = user[key];
    });
    const startsField = form.elements.namedItem('starts_at');
    if (startsField) startsField.value = user.starts_date || '';
    const expiresField = form.elements.namedItem('expires_at');
    if (expiresField) {
      expiresField.value = user.expires_date || '';
    }
    const used = form.elements.namedItem('used_traffic_gib');
    used.dataset.initialValue = used.value;

    editBaseline = editValues();
    form.querySelector('[data-edit-user-fields]').disabled = false;
    form.querySelector('button[type="submit"]').disabled = false;
    status.textContent = '已加载 ' + user.name + ' 的设置';
  } catch (error) {
    if (sequence === editLoadSequence) status.textContent = error.message || '加载失败，请重试';
  }
}
function renderUpdateStatus(payload) {
  const status = document.querySelector('[data-update-status]');
  if (!status) return;
  status.dataset.state = payload.state || 'idle';
  status.textContent = payload.message || '正在读取更新状态…';
}
function enablePageRefresh(button) {
  button.disabled = false;
  button.type = 'button';
  button.textContent = '刷新状态';
  button.onclick = function() { window.location.reload(); };
}
async function pollUpdateStatus(button, deadline) {
  const controller = new AbortController();
  const timeout = window.setTimeout(function() { controller.abort(); }, 8000);
  try {
    const response = await fetch('/updates/status', {
      headers: {'Accept': 'application/json'},
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal
    });
    if (response.status === 401) {
      window.location.assign('/login');
      return;
    }
    if (!response.ok) throw new Error('状态读取失败');
    const payload = await response.json();
    renderUpdateStatus(payload);
    if (['queued', 'running'].includes(payload.state)) button.textContent = '正在更新…';
    if (payload.state === 'success') {
      window.setTimeout(function() { window.location.reload(); }, 900);
      return;
    }
    if (payload.state === 'failed') {
      enablePageRefresh(button);
      notify(payload.message || '在线更新失败', true);
      return;
    }
  } catch (_) {
    renderUpdateStatus({state: 'unknown', message: '暂时无法读取更新状态，正在重试…'});
  } finally {
    window.clearTimeout(timeout);
  }
  if (Date.now() >= deadline) {
    enablePageRefresh(button);
    renderUpdateStatus({state: 'unknown', message: '暂时无法确认更新结果，请刷新页面查看当前版本'});
    return;
  }
  window.setTimeout(function() { pollUpdateStatus(button, deadline); }, 1500);
}
const updateForm = document.querySelector('[data-update-form]');
const updateStatus = document.querySelector('[data-update-status]');
if (updateForm && updateStatus && ['queued', 'running'].includes(updateStatus.dataset.state)) {
  const button = updateForm.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = '正在更新…';
  pollUpdateStatus(button, Date.now() + 180000);
}
const dialogOpeners = new WeakMap();
let trafficHistoryRequest = null;
const trafficHistoryDialog = document.getElementById('traffic-history-dialog');
function trafficBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return bytes + ' B';
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  const index = Math.min(3, Math.floor(Math.log(bytes) / Math.log(1024)) - 1);
  return (bytes / Math.pow(1024, index + 1)).toFixed(2) + ' ' + units[index];
}
function trafficLine(label, record) {
  const line = document.createElement('div');
  line.className = 'traffic-history-line';
  const title = document.createElement('span'); title.textContent = label;
  const total = document.createElement('strong'); total.textContent = trafficBytes(record.totalBytes);
  const percent = document.createElement('span'); percent.textContent = Number(record.percent).toFixed(1) + '%';
  line.append(title, total, percent);
  return line;
}
if (trafficHistoryDialog) trafficHistoryDialog.addEventListener('close', function() {
  if (trafficHistoryDialog.open) return;
  if (trafficHistoryRequest) trafficHistoryRequest.abort();
  trafficHistoryRequest = null;
  trafficHistoryDialog.querySelector('[data-traffic-history-content]').replaceChildren();
});
document.addEventListener('click', async function(event) {
  const button = event.target.closest('[data-traffic-user-id]');
  if (!button || !trafficHistoryDialog) return;
  if (trafficHistoryRequest) trafficHistoryRequest.abort();
  const request = new AbortController(); trafficHistoryRequest = request;
  const content = trafficHistoryDialog.querySelector('[data-traffic-history-content]');
  content.textContent = '正在读取流量记录…';
  document.getElementById('traffic-history-title').textContent = '用户流量';
  if (!trafficHistoryDialog.open) {
    dialogOpeners.set(trafficHistoryDialog, button);
    trafficHistoryDialog.showModal();
  }
  const timeout = window.setTimeout(function() { request.abort(); }, 15000);
  try {
    const response = await fetch('/api/v1/users/' + encodeURIComponent(button.dataset.trafficUserId) + '/traffic-history', {
      credentials: 'same-origin', headers: {'Accept': 'application/json'}, signal: request.signal
    });
    if (response.redirected || response.status === 401) throw new Error('登录已失效，请重新登录后重试');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '读取失败，请重试');
    if (trafficHistoryRequest !== request || !trafficHistoryDialog.open) return;
    document.getElementById('traffic-history-title').textContent = data.name + ' · ' + data.month + ' 流量';
    content.replaceChildren();
    const total = document.createElement('p');
    total.className = 'traffic-history-total'; total.textContent = '本月已记录 ' + trafficBytes(data.totalBytes);
    content.append(total);
    for (const day of data.days) {
      const detail = document.createElement('details'); detail.className = 'traffic-history-day';
      const summary = document.createElement('summary');
      summary.append(trafficLine(day.date, day));
      detail.append(summary);
      const info = document.createElement('p'); info.className = 'muted';
      info.textContent = day.hasRecords ? '上传 ' + trafficBytes(day.txBytes) + ' · 下载 ' + trafficBytes(day.rxBytes) : '当天暂无采集记录';
      detail.append(info);
      let rendered = false;
      detail.addEventListener('toggle', function() {
        if (!detail.open || rendered) return;
        rendered = true;
        for (const hour of day.hours) {
          const slot = String(hour.hour).padStart(2, '0') + ':00–' + String(hour.hour + 1).padStart(2, '0') + ':00';
          const row = trafficLine(slot, hour);
          row.title = '上传 ' + trafficBytes(hour.txBytes) + ' · 下载 ' + trafficBytes(hour.rxBytes);
          detail.append(row);
        }
      });
      content.append(detail);
    }
  } catch (error) {
    if (trafficHistoryRequest !== request || !trafficHistoryDialog.open) return;
    content.textContent = request.signal.aborted ? '读取超时，请关闭后重试' : (error.message || '读取失败，请关闭后重试');
    const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = '重试';
    retry.dataset.trafficUserId = button.dataset.trafficUserId; content.append(document.createElement('br'), retry);
  } finally {
    window.clearTimeout(timeout);
  }
});

document.addEventListener('click', function(event) {
  const opener = event.target.closest('[data-dialog-open]');
  if (opener) {
    if (opener.dataset.dialogOpen === 'edit-user-dialog') {
      clearEditUser();
      if (opener.dataset.editUserName) {
        document.querySelector('[data-edit-user-name-input]').value = opener.dataset.editUserName;
        loadEditUser();
      }
    }
    const dialog = document.getElementById(opener.dataset.dialogOpen);
    if (dialog && typeof dialog.showModal === 'function') {
      const status = dialog.querySelector('[data-dialog-status]');
      if (status) status.remove();
      dialogOpeners.set(dialog, opener);
      dialog.showModal();
    }
    return;
  }
  const closer = event.target.closest('[data-dialog-close]');
  if (closer) {
    const dialog = closer.closest('dialog');
    if (dialog) closeUserDialog(dialog);
  }
});
document.addEventListener('keydown', function(event) {
  if (event.key !== 'Escape') return;
  const dialogs = Array.from(document.querySelectorAll('dialog[open]'));
  const dialog = dialogs[dialogs.length - 1];
  if (!dialog) return;
  event.preventDefault();
  closeUserDialog(dialog);
});
document.addEventListener('cancel', function(event) {
  if (!['edit-user-dialog', 'create-user-dialog'].includes(event.target.id)) return;
  event.preventDefault();
  closeUserDialog(event.target);
}, true);
document.addEventListener('close', function(event) {
  const dialog = event.target;
  if (!(dialog instanceof HTMLDialogElement) || dialog.open) return;
  if (dialog.id === 'edit-user-dialog' && !dialog.open) editLoadSequence += 1;
  const opener = dialogOpeners.get(dialog);
  dialogOpeners.delete(dialog);
  if (opener && opener.isConnected) opener.focus();
}, true);
document.addEventListener('click', async function(event) {
  const button = event.target.closest('[data-copy-target]');
  if (!button) return;
  const target = document.getElementById(button.dataset.copyTarget);
  if (!target) return;
  const copied = await copyText(target.value);
  button.textContent = copied ? '已复制' : '复制失败，请手动选择';
  notify(copied ? '订阅链接已复制' : '自动复制失败，请手动选择订阅链接', !copied);
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
    notify(copied ? payload.name + ' 的订阅链接已复制' : '自动复制失败，请重试', !copied);
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
  if (button.disabled || !editSelectedId || form.querySelector('[data-edit-user-name-input]').value.trim() !== editLoadedName) return;
  form.dataset.saving = '1';
  button.disabled = true;
  button.textContent = '保存中…';
  const used = form.querySelector('[name="used_traffic_gib"]');
  used.disabled = used.value === used.dataset.initialValue;
  try {
    const payload = await submitInlineForm(form);
    notify(payload.name + ' 的用户设置已更新', false);
    const dialog = form.closest('dialog');
    if (dialog) dialog.close();
    window.setTimeout(function() { window.location.reload(); }, 700);
  } catch (error) {
    notify(error.message || '用户设置更新失败，请重试', true);
  } finally {
    delete form.dataset.saving;
    used.disabled = false;
    button.disabled = !editSelectedId || form.querySelector('[data-edit-user-name-input]').value.trim() !== editLoadedName;
    button.textContent = '保存修改';
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-update-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  if (!button || button.disabled) return;
  button.disabled = true;
  button.textContent = '正在排队…';
  try {
    const payload = await submitInlineForm(form);
    renderUpdateStatus(payload);
    button.textContent = '正在更新…';
    pollUpdateStatus(button, Date.now() + 180000);
  } catch (error) {
    if (error instanceof UnconfirmedRequestError) {
      button.textContent = '正在确认状态…';
      renderUpdateStatus({state: 'unknown', message: error.message});
      pollUpdateStatus(button, Date.now() + 180000);
    } else {
      button.disabled = false;
      button.textContent = '立即更新';
    }
    notify(error.message || '在线更新任务启动失败', true);
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-create-user-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  if (!button || button.disabled) return;
  const closer = form.closest('dialog').querySelector('[data-dialog-close]');
  form.dataset.saving = '1';
  if (closer) closer.disabled = true;
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
    delete form.dataset.saving;
    if (closer) closer.disabled = false;
    button.disabled = false;
    button.textContent = '添加用户';
  }
});
let nodeEnrollmentGeneration = 0;
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-node-enrollment-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  const result = document.querySelector('[data-node-enrollment-result]');
  const code = document.getElementById('node-deployment-code');
  const expiry = document.querySelector('[data-node-enrollment-expiry]');
  const generation = ++nodeEnrollmentGeneration;
  const dialog = form.closest('dialog');
  button.disabled = true;
  button.textContent = '生成中…';
  try {
    const payload = await submitInlineForm(form);
    if (generation !== nodeEnrollmentGeneration || !dialog.open) return;
    if (!payload || typeof payload.deploymentCommand !== 'string' || !(payload.deploymentCommand.startsWith('(\\nset -euo pipefail') || payload.deploymentCommand.startsWith('(export HY2PANEL_PANEL_URL='))) {
      throw new Error('部署代码响应无效');
    }
    code.value = payload.deploymentCommand;
    expiry.textContent = (payload.restoredProfile ? '已沿用该地区原有证书，节点配置以本次填写为准。' : '') + '对接码将在 ' + new Date(Number(payload.expiresAt) * 1000).toLocaleTimeString() + ' 过期，且只能使用一次。';
    result.hidden = false;
    let copied = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(payload.deploymentCommand);
        copied = true;
      }
    } catch (_error) {}
    code.focus();
    code.select();
    notify(copied ? '对接代码已生成并复制，请到目标服务器粘贴运行' : '对接代码已生成，请复制到目标服务器运行', false);
  } catch (error) {
    notify(error.message || '生成部署代码失败，请重试', true);
  } finally {
    button.disabled = false;
    button.textContent = '生成对接命令';
  }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-restore-form]');
  if (!form || event.defaultPrevented) return;
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  if (!button || button.disabled) return;
  const file = form.querySelector('input[type="file"]');
  const status = form.querySelector('[data-restore-status]');
  if (!file || !file.files.length) { status.textContent = '请选择 ZIP 备份文件'; return; }
  if (!window.confirm('恢复会替换全部代理用户、签名密钥和证书，并短暂重启服务。确定继续吗？')) return;
  button.disabled = true;
  button.textContent = '正在上传…';
  status.textContent = '正在校验并上传备份…';
  try {
    const payload = await postJson('/restore', {
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/zip',
        'X-HY2Panel-CSRF': form.dataset.csrf
      },
      body: file.files[0]
    }, 16 * 60 * 1000);
    if (payload.status !== 'queued') throw new UnconfirmedRequestError();
    button.textContent = '恢复已启动';
    status.textContent = '恢复任务已启动，服务将在数秒后重启；请稍后重新登录。';
  } catch (error) {
    if (error instanceof UnconfirmedRequestError) {
      enablePageRefresh(button);
    } else {
      button.disabled = false;
      button.textContent = '上传并恢复';
    }
    status.textContent = error.message || '恢复上传失败，请重试';
  }
});
const credentialsDialog = document.getElementById('credentials-dialog');
if (credentialsDialog) credentialsDialog.addEventListener('close', function() {
  const refresh = credentialsDialog.dataset.refreshOnClose === '1';
  credentialsDialog.querySelector('#credentials-uri').value = '';
  clearCredentialsQr();
  if (refresh) {
    const target = new URLSearchParams(window.location.search).get('type') === 'premium' ? '/?type=premium#users' : '/#users';
    if (location.href === new URL(target, location.origin).href) location.reload(); else location.assign(target);
  }
});
const nodeOnboardingDialog = document.getElementById('node-onboarding-dialog');
if (nodeOnboardingDialog) nodeOnboardingDialog.addEventListener('close', function() {
  nodeEnrollmentGeneration += 1;
  const code = document.getElementById('node-deployment-code');
  const result = document.querySelector('[data-node-enrollment-result]');
  const expiry = document.querySelector('[data-node-enrollment-expiry]');
  if (code) code.value = '';
  if (expiry) expiry.textContent = '';
  if (result) result.hidden = true;
});
const editNameInput = document.querySelector('[data-edit-user-name-input]');
if (editNameInput) {
  document.querySelector('[data-edit-user-load]').addEventListener('click', loadEditUser);
  editNameInput.addEventListener('keydown', function(event) {
    if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); loadEditUser(); }
  });
  editNameInput.addEventListener('input', function() {
    editLoadSequence += 1;
    document.querySelector('[data-edit-user-form] button[type="submit"]').disabled =
      !editSelectedId || editNameInput.value.trim() !== editLoadedName;
  });
}
const filterForm = document.querySelector('[data-user-filters]');
if (filterForm) {
  const userSearch = filterForm.querySelector('[data-user-search]');
  const clearFilters = filterForm.querySelector('[data-clear-user-filters]');
  let composing = false;
  function applyServerFilters() {
    const params = new URLSearchParams(new FormData(filterForm));
    const url = new URL(window.location.href);
    ['q', 'status', 'online', 'udp443', 'type'].forEach(function(name) {
      const value = params.get(name);
      if (value) url.searchParams.set(name, value);
      else url.searchParams.delete(name);
    });
    url.searchParams.delete('page');
    window.location.assign(url.pathname + url.search + '#users');
  }
  filterForm.addEventListener('submit', function(event) {
    event.preventDefault();
    if (!composing) applyServerFilters();
  });
  userSearch.addEventListener('compositionstart', function() { composing = true; });
  userSearch.addEventListener('compositionend', function() { composing = false; });
  if (window.location.hash === '#users') window.addEventListener('load', function() {
    userSearch.focus({preventScroll: true});
  }, {once: true});
  if (clearFilters) clearFilters.addEventListener('click', function() {
    ['q', 'status', 'online', 'udp443'].forEach(function(name) {
      const field = filterForm.elements.namedItem(name);
      if (field) field.value = '';
    });
    applyServerFilters();
  });
}

function isOnlineCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}
function dashboardOnlinePayload(value) {
  const states = new Set(['fresh', 'stale', 'standby', 'revoked', 'unavailable', 'history']);
  if (!value || typeof value !== 'object' || !isOnlineCount(value.observedAt) ||
      typeof value.onlineComplete !== 'boolean' || !isOnlineCount(value.onlineDevices) ||
      !Array.isArray(value.users) || !Array.isArray(value.machines)) return null;
  if (!value.users.every(function(user) {
    return user && typeof user.name === 'string' && isOnlineCount(user.onlineDevices);
  })) return null;
  if (!value.machines.every(function(machine) {
    return machine && typeof machine.originId === 'string' &&
      (machine.onlineDevices === null || isOnlineCount(machine.onlineDevices)) &&
      isOnlineCount(machine.lastKnownOnlineDevices) && states.has(machine.onlineState) &&
      (machine.observedAt === null || isOnlineCount(machine.observedAt));
  })) return null;
  if (value.activeNodeIds !== undefined &&
      (!Array.isArray(value.activeNodeIds) || !value.activeNodeIds.every(function(id) {
        return typeof id === 'string' && /^[0-9a-f]{32}$/.test(id);
      }))) return null;
  return value;
}
function liveTime(timestamp, dateOnly) {
  const date = new Date(timestamp * 1000);
  if (!Number.isFinite(date.getTime())) return '尚未上报';
  if (dateOnly) return date.toLocaleString('zh-CN', {hour12: false});
  return date.toLocaleTimeString('zh-CN', {hour12: false});
}
function sortOnlineUserRows() {
  const params = new URL(window.location.href).searchParams;
  if (params.get('sort') !== 'online' || !['asc', 'desc'].includes(params.get('order'))) return;
  const rows = Array.from(document.querySelectorAll('[data-user-name]'));
  const body = rows.length ? rows[0].parentElement : null;
  if (!body) return;
  const direction = params.get('order') === 'asc' ? 1 : -1;
  rows.sort(function(left, right) {
    return direction * (Number(left.dataset.online || '0') - Number(right.dataset.online || '0'));
  });
  rows.forEach(function(row) { body.appendChild(row); });
}
function applyOnlineStatus(payload) {
  if (Array.isArray(payload.activeNodeIds)) {
    const activeNodes = new Set(payload.activeNodeIds);
    document.querySelectorAll('[data-pairing-node-id]').forEach(function(row) {
      if (!activeNodes.has(row.dataset.pairingNodeId)) row.remove();
    });
  }
  if (payload.machineForecasts && typeof payload.machineForecasts === 'object') {
    document.querySelectorAll('[data-origin-id]').forEach(function(card) {
      if (Array.isArray(payload.activeNodeIds) && card.dataset.originId.startsWith('node:') &&
          !payload.activeNodeIds.includes(card.dataset.originId.slice(5))) {
        card.remove();
        return;
      }
      const forecast = payload.machineForecasts[card.dataset.originId];
      if (!forecast || typeof forecast.text !== 'string' || typeof forecast.basis !== 'string') return;
      const text = card.querySelector('[data-machine-forecast]');
      if (text) text.textContent = forecast.text;
      const budget = forecast.budget;
      if (budget && Number.isFinite(budget.percent) && Number.isFinite(budget.used_bytes) &&
          Number.isFinite(budget.limit_bytes)) {
        const bytes = function(value) {
          const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
          let index = 0;
          while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
          return (index ? value.toFixed(1) : String(value)) + ' ' + units[index];
        };
        const usage = card.querySelector('[data-machine-budget-usage]');
        const period = card.querySelector('[data-machine-budget-period]');
        const progress = card.querySelector('progress');
        if (usage) {
          usage.textContent = bytes(budget.used_bytes) + ' / ' +
            (budget.limit_bytes ? bytes(budget.limit_bytes) : '不限') + ' · ' + budget.percent.toFixed(1) + '%';
          usage.parentElement.className = ({disabled:'muted',normal:'ok',warning:'warning',exhausted:'bad'})[budget.status] || 'warning';
        }
        if (progress) progress.value = Math.max(0, Math.min(100, budget.percent));
        if (period && Number.isInteger(budget.reset_days) && budget.reset_days >= 0) {
          period.textContent = '剩余 ' + budget.reset_days + ' 天重置';
        }
      }
    });
    const count = document.querySelector('.machine-count');
    if (count) count.textContent = String(document.querySelectorAll(
      '.machine-budget-row[data-origin-id^="local:"], .machine-budget-row[data-origin-id^="node:"]'
    ).length) + ' 台机器';
  }
  const pageParams = new URL(window.location.href).searchParams;
  if (pageParams.get('sort') === 'online' || pageParams.has('online')) {
    const renderedNames = new Set(
      Array.from(document.querySelectorAll('[data-user-name]')).map(function(row) {
        return row.dataset.userName;
      })
    );
    const liveNames = new Set(payload.users.map(function(user) { return user.name; }));
    if (renderedNames.size !== liveNames.size ||
        Array.from(renderedNames).some(function(name) { return !liveNames.has(name); })) {
      window.location.reload();
      return;
    }
  }
  const total = document.querySelector('[data-live-online-total]');
  const refreshed = document.querySelector('[data-live-refreshed]');
  const note = document.querySelector('[data-live-online-note]');
  if (total && total.textContent !== String(payload.onlineDevices)) {
    total.textContent = String(payload.onlineDevices);
  }
  if (refreshed) refreshed.textContent = liveTime(payload.observedAt, false);
  if (note) {
    note.className = payload.onlineComplete ? 'muted' : 'metric-warning';
    note.textContent = payload.onlineComplete
      ? '按 Hysteria 客户端实例统计'
      : '设备统计暂不完整：部分节点上报已过期';
  }

  const users = new Map(payload.users.map(function(user) { return [user.name, user.onlineDevices]; }));
  let userCountsChanged = false;
  document.querySelectorAll('[data-user-name]').forEach(function(row) {
    if (!users.has(row.dataset.userName)) return;
    const count = users.get(row.dataset.userName);
    const oldCount = Number(row.dataset.online || '0');
    row.dataset.online = String(count);
    const online = row.querySelector('[data-live-user-online]');
    if (online && online.textContent !== String(count)) online.textContent = String(count);
    const limit = Number(row.dataset.deviceLimit || '0');
    const overLimit = count > limit;
    row.dataset.overDeviceLimit = overLimit ? '1' : '0';
    const name = row.querySelector('[data-live-user-name] strong');
    const alert = row.querySelector('[data-live-limit-alert]');
    if (name) name.classList.toggle('over-limit-name', overLimit);
    if (alert) alert.hidden = !overLimit;
    if (oldCount !== count) userCountsChanged = true;
  });
  if (userCountsChanged && filterForm) {
    sortOnlineUserRows();
  }

  const machineStates = {
    fresh: ['新鲜', 'ok'], stale: ['数据过期', 'warning'], standby: ['已停用', 'muted'],
    revoked: ['已撤销', 'bad'], unavailable: ['等待上报', 'warning'], history: ['历史记录', 'muted']
  };
  const machines = new Map(
    Array.from(document.querySelectorAll('[data-origin-id]')).map(function(card) {
      return [card.dataset.originId, card];
    })
  );
  const actualMachines = payload.machines.filter(function(m) { return m.onlineState !== 'history' && m.onlineState !== 'revoked'; });
  const nodeCount = document.querySelector('[data-console-node-count]');
  if (nodeCount) nodeCount.textContent = actualMachines.filter(function(m) { return m.onlineState === 'fresh'; }).length + ' / ' + actualMachines.length;
  const allOnline = document.querySelector('[data-console-online]');
  if (allOnline) allOnline.textContent = actualMachines.reduce(function(sum,m) { return sum+(m.onlineDevices || 0); },0);
  payload.machines.forEach(function(machine) {
    const card = machines.get(machine.originId);
    if (!card) return;
    const online = card.querySelector('[data-live-machine-online]');
    const state = card.querySelector('[data-live-machine-state]');
    const observed = card.querySelector('[data-live-machine-observed]');
    const onlineText = machine.onlineDevices === null
      ? (machine.lastKnownOnlineDevices ? '—（上次 ' + machine.lastKnownOnlineDevices + '）' : '—')
      : String(machine.onlineDevices);
    if (online) online.textContent = onlineText;
    if (state) {
      state.textContent = machineStates[machine.onlineState][0];
      state.className = machineStates[machine.onlineState][1];
    }
    if (observed) {
      observed.textContent = machine.observedAt === null
        ? '尚未上报'
        : liveTime(machine.observedAt, true);
    }
  });
}
async function refreshOnlineStatus() {
  const startedAt = Date.now();
  const controller = new AbortController();
  const timeout = window.setTimeout(function() { controller.abort(); }, 1800);
  try {
    const onlineUrl = '/api/v1/dashboard-online' + window.location.search;
    const response = await fetch(onlineUrl, {
      headers: {'Accept': 'application/json'},
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal
    });
    if (response.status === 401) {
      window.location.assign('/login');
      return;
    }
    if (!response.ok) throw new Error('在线设备状态读取失败');
    const payload = dashboardOnlinePayload(await response.json());
    if (!payload) throw new Error('在线设备状态响应无效');
    applyOnlineStatus(payload);
  } catch (_) {
    // 短暂断网或面板重启时保留最后一次可信数据，下一轮自动重试。
  }
  window.clearTimeout(timeout);
  window.setTimeout(
    refreshOnlineStatus,
    Math.max(0, 2000 - (Date.now() - startedAt))
  );
}
if (document.querySelector('[data-live-online-total], [data-console-online]')) {
  window.setTimeout(refreshOnlineStatus, 2000);
}
const subscriptionDialog = document.getElementById('subscription-dialog');
let subscriptionRequest = null;
function subscriptionCsrf() {
  const field = subscriptionDialog && subscriptionDialog.querySelector('[data-subscription-csrf]');
  return field ? field.value : '';
}
function escapeHtmlAttr(value) {
  return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function subscriptionNodeRow(node) {
  return '<fieldset class="subscription-node-row"><legend>节点配置</legend>' +
    '<label>名称<input data-sub-node-label maxlength="80" value="' + escapeHtmlAttr(node.label) + '" required></label>' +
    '<label>服务器地址<input data-sub-node-host value="' + escapeHtmlAttr(node.host) + '" required></label>' +
    '<label>UDP 端口<input type="number" data-sub-node-port min="1" max="65535" value="' + (node.port || 443) + '" required></label>' +
    '<label>证书 SHA-256 指纹<input data-sub-node-pin value="' + escapeHtmlAttr(node.pin_sha256) + '" required></label>' +
    '<label><input type="checkbox" data-sub-node-enabled' + (node.enabled === false ? '' : ' checked') + '>启用</label>' +
    '<button type="button" class="secondary" data-sub-node-remove>移除此节点</button></fieldset>';
}
const externalDialog = document.getElementById('external-nodes-dialog');
let externalRevision = 0;
let externalPreview = null;
let externalLoading = false;
let externalGeneration = 0;
function externalRow(node) {
  return '<section class="external-node-card" data-external-row' + (node.id == null ? '' : ' data-id="' + node.id + '"') + '>' +
    '<div class="external-node-heading"><span class="external-protocol">AnyTLS</span><code>' + escapeHtmlAttr(node.host ? node.host + ':' + node.port : '新节点 · 校验后显示地址') + '</code></div>' +
    '<div class="external-node-fields"><label>展示名称<input data-ext-label maxlength="80" value="' + escapeHtmlAttr(node.label) + '"></label>' +
    '<label>替换链接 <span class="field-optional">可选</span><textarea data-ext-uri rows="2" autocomplete="off" spellcheck="false" placeholder="留空保留原配置；粘贴新 AnyTLS 链接可替换">' + escapeHtmlAttr(node.uri || '') + '</textarea></label></div>' +
    '<div class="external-node-footer"><label class="external-enabled"><input type="checkbox" data-ext-enabled' + (node.enabled === false ? '' : ' checked') + '>启用节点</label>' +
    '<div class="external-node-actions"><button type="button" class="secondary" data-ext-move="up">上移</button><button type="button" class="secondary" data-ext-move="down">下移</button><button type="button" class="secondary external-remove" data-ext-remove>移除</button></div></div></section>';
}
function invalidateExternalPreview() {
  externalPreview = null;
  if (!externalDialog) return;
  const count = externalDialog.querySelector('[data-ext-count]');
  const rows = externalDialog.querySelector('[data-ext-rows]');
  if (count && rows) count.textContent = rows.children.length + ' / 32';
  const publish = externalDialog.querySelector('[data-ext-publish]');
  if (publish) publish.disabled = true;
  const preview = externalDialog.querySelector('[data-ext-preview-result]');
  if (preview) preview.textContent = '修改尚未发布，请先校验预览。';
}
async function loadExternalNodes() {
  if (!externalDialog || externalLoading) return;
  externalLoading = true;
  const generation = externalGeneration;
  externalPreview = null;
  if (!externalDialog.open) externalDialog.showModal();
  const content = externalDialog.querySelector('[data-external-content]');
  content.textContent = '正在加载…';
  try {
    const response = await fetch('/subscriptions/external', {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
    if (response.redirected || !response.ok) throw new Error('读取失败，请检查登录状态');
    const data = await response.json();
    if (!externalDialog.open || generation !== externalGeneration) return;
    externalRevision = data.revision;
    content.innerHTML = '<fieldset data-ext-editor class="external-editor"><section class="external-import"><div class="management-section-head"><h3>批量导入</h3><span class="muted">每行一个链接</span></div>' +
      '<label class="external-input-label">AnyTLS 链接<textarea data-ext-batch rows="3" autocomplete="off" spellcheck="false" placeholder="在此粘贴 anytls:// 链接，每行一个"></textarea></label>' +
      '<div class="external-import-toolbar"><label>导入方式<select data-ext-mode><option value="append">追加到当前外部节点</option><option value="replace">替换全部外部节点</option></select></label>' +
      '<button type="button" class="secondary" data-ext-import>导入到草稿</button></div></section>' +
      '<div class="management-section-head external-list-heading"><div><h3>节点列表</h3><p class="muted">可改名、排序或替换链接。已有密码不回显。</p></div><span class="external-count" data-ext-count>' + data.nodes.length + ' / 32</span></div>' +
      '<div class="external-node-list" data-ext-rows>' + data.nodes.map(externalRow).join('') + '</div>' +
      '<div class="external-preview-result" data-ext-preview-result role="status" aria-live="polite"></div>' +
      '<div class="external-publish-bar"><p class="muted">修改后先预览，再发布<br><span>关闭窗口会丢弃未发布草稿</span></p><div><button type="button" class="secondary" data-ext-preview>校验并预览</button><button type="button" data-ext-publish disabled>发布给专线用户</button></div></div></fieldset>';
  } catch (error) { content.textContent = error.message || '读取失败'; }
  finally { externalLoading = false; }
}
if (externalDialog) {
  externalDialog.addEventListener('input', invalidateExternalPreview);
  externalDialog.addEventListener('change', invalidateExternalPreview);
  externalDialog.addEventListener('close', function() {
    externalGeneration += 1;
    externalPreview = null;
    externalDialog.querySelector('[data-external-content]').textContent = '';
  });
  externalDialog.addEventListener('click', async function(event) {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    const rows = externalDialog.querySelector('[data-ext-rows]');
    if (button.hasAttribute('data-ext-import')) {
      const input = externalDialog.querySelector('[data-ext-batch]');
      const links = input.value.split(/\\r?\\n/).map(x => x.trim()).filter(Boolean);
      const replace = externalDialog.querySelector('[data-ext-mode]').value === 'replace';
      if (!links.length || links.length + (replace ? 0 : rows.children.length) > 32) { notify('请输入链接，总数最多 32 个', true); return; }
      const draft = links.map(function(uri, index) {
        let label = '外部节点 ' + (index + 1);
        try { const fragment = new URL(uri).hash.slice(1); if (fragment) label = decodeURIComponent(fragment); } catch (_) {}
        return externalRow({uri: uri, label: label});
      }).join('');
      if (replace) rows.innerHTML = draft; else rows.insertAdjacentHTML('beforeend', draft);
      input.value = ''; invalidateExternalPreview(); return;
    }
    const row = button.closest('[data-external-row]');
    if (button.hasAttribute('data-ext-remove')) { row.remove(); invalidateExternalPreview(); return; }
    if (button.hasAttribute('data-ext-move')) {
      if (button.dataset.extMove === 'up' && row.previousElementSibling) rows.insertBefore(row, row.previousElementSibling);
      else if (button.dataset.extMove === 'down' && row.nextElementSibling) rows.insertBefore(row.nextElementSibling, row);
      invalidateExternalPreview(); return;
    }
    const publish = button.hasAttribute('data-ext-publish');
    if (!publish && !button.hasAttribute('data-ext-preview')) return;
    if (externalDialog.querySelector('[data-ext-batch]').value.trim()) { notify('请先将批量链接导入到草稿', true); return; }
    const nodes = Array.from(rows.children).map(function(row) {
      const node = {label: row.querySelector('[data-ext-label]').value.trim(), uri: row.querySelector('[data-ext-uri]').value.trim(), enabled: row.querySelector('[data-ext-enabled]').checked};
      if (row.hasAttribute('data-id')) node.id = Number(row.dataset.id);
      return node;
    });
    const snapshot = JSON.stringify(nodes);
    if (publish && snapshot !== externalPreview) { invalidateExternalPreview(); return; }
    const editor = externalDialog.querySelector('[data-ext-editor]');
    editor.disabled = true;
    const generation = externalGeneration;
    try {
      const response = await fetch('/subscriptions/external' + (publish ? '' : '/preview'), {
        method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({csrf: subscriptionCsrf(), revision: String(externalRevision), nodes: snapshot}).toString()
      });
      if (response.redirected) throw new Error('登录已失效，请重新登录');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '操作失败');
      if (!externalDialog.open || generation !== externalGeneration) return;
      if (publish) {
        notify('已发布，专线用户刷新原订阅即可获取；自建节点不变', false);
        await loadExternalNodes();
      } else {
        externalPreview = snapshot;
        externalDialog.querySelector('[data-ext-preview-result]').innerHTML = '<p>发布后：' + data.nodes.filter(n => n.enabled).length + ' 个启用的外部节点，追加到所有有效专线用户订阅。自建节点统计不变。</p>' +
          '<ul>' + data.nodes.map(n => '<li>' + escapeHtmlAttr(n.label) + ' · ' + escapeHtmlAttr(n.host) + ':' + n.port + (n.enabled ? ' · 启用' : ' · 停用') + (n.insecure ? ' · 跳过证书验证' : '') + '</li>').join('') + '</ul>';
        externalDialog.querySelector('[data-ext-publish]').disabled = false;
      }
    } catch (error) { invalidateExternalPreview(); notify(error.message || '操作失败', true); }
    finally { editor.disabled = false; }
  });
}
document.addEventListener('click', function(event) {
  if (event.target.closest('[data-external-open]')) loadExternalNodes();
});

async function loadSubscription(userId) {
  if (!subscriptionDialog) return;
  const content = subscriptionDialog.querySelector('[data-subscription-content]');
  if (!subscriptionDialog.open) subscriptionDialog.showModal();
  if (subscriptionRequest) subscriptionRequest.abort();
  const request = new AbortController(); subscriptionRequest = request;
  const timeout = window.setTimeout(function() { request.abort(); }, 15000);
  content.dataset.userId = userId || '';
  content.textContent = '正在加载…';
  try {
    const response = await fetch(userId ? '/subscriptions/user/' + encodeURIComponent(userId) : '/subscriptions/defaults',
      {credentials: 'same-origin', signal: request.signal, headers: {'Accept': 'application/json'}});
    if (subscriptionRequest !== request || !subscriptionDialog.open) return;
    if (response.redirected || response.status === 401) throw new Error('登录已失效，请重新登录');
    if (response.status === 404 && userId) {
      content.innerHTML = '<p>创建后获得固定订阅链接，默认使用统一节点。</p><button type="button" data-sub-action="create">创建订阅</button>';
      return;
    }
    const data = await response.json();
    if (subscriptionRequest !== request || !subscriptionDialog.open) return;
    if (!response.ok) throw new Error(data.error || '读取失败');
    content.dataset.subscriptionId = data.id || '';
    if (userId) {
      const url = new URL(data.url, window.location.origin).href;
      content.innerHTML = '<label>固定订阅链接<textarea class="subscription-url" readonly>' + escapeHtmlAttr(url) + '</textarea></label>' +
        '<button type="button" data-sub-action="copy">复制订阅链接</button>' +
        '<p>在客户端添加订阅。刷新后更新节点、已用和剩余流量；支持 Mihomo / Clash Meta 和通用 Base64 订阅。</p>' +
        (data.user_type === 1 ? '<p class="muted">流量信息仅统计自建节点；外部节点用量和剩余流量未知。</p>' : '') +
        '<p>状态：' + (data.enabled ? '启用' : '停用') + ' · ' + (data.user_type === 1 ? '高级专线 · 已就绪 ' + data.premium_ready_count + '/4 地区，共享套餐' : (data.uses_defaults ? '跟随普通节点设置' : '独立节点配置')) + '</p>' +
        (data.user_type === 1 || data.uses_defaults ? '' : '<button type="button" data-sub-action="inherit">改为跟随统一节点</button>') +
        '<p><button class="secondary" type="button" data-sub-action="toggle">' + (data.enabled ? '停用订阅' : '启用订阅') + '</button></p>' +
        '<details><summary>链接泄露处理</summary><p>重置会同时更换订阅链接和该用户的节点密码，并断开旧连接；请重新发送订阅。修改端口不需要重置。</p><button class="warning" type="button" data-sub-action="regenerate">重置订阅链接</button></details>';
    } else {
      const unifiedPort = data.nodes.length && data.nodes.every(n=>n.port===data.nodes[0].port) ? Number(data.nodes[0].port) : "";
      content.innerHTML = '<p class="subscription-intro">订阅链接不变。更换端口前，请先在服务器监听并放行对应 UDP 端口。</p>' +
        '<div class="notice hopping-settings"><div><strong>本机端口跳跃</strong><small>UDP ' + data.hopping.ports + ' → ' + data.hopping.target + ' · 每 30 秒切换</small></div><button type="button" data-hop-toggle="' + (data.hopping.enabled ? 'disable' : 'enable') + '">' + (data.hopping.enabled ? '关闭端口跳跃' : '开启端口跳跃') + '</button></div>' +
        '<div class="unified-port-bar"><label for="unified-node-port">统一 UDP 端口</label><input id="unified-node-port" type="number" min="1" max="65535" value="' + unifiedPort + '" required><button type="button" class="secondary" data-apply-unified-port>应用到下方节点</button><small>应用后点击保存；不会修改服务器监听端口。</small></div>' +
        '<form data-sub-defaults-form><div data-sub-node-rows>' + data.nodes.map(subscriptionNodeRow).join('') + '</div>' +
        '<div class="credential-actions"><button class="secondary" type="button" data-sub-action="add">添加节点</button><button type="submit">保存统一节点配置</button></div></form>';
    }
  } catch (error) {
    if (subscriptionRequest === request) content.textContent = error.name === 'AbortError' ? '请求超时，请关闭后重试' : error.message;
  } finally { window.clearTimeout(timeout); }
}
document.addEventListener('click', async function(event) {
  const unified = event.target.closest('[data-apply-unified-port]');
  if (unified) {
    const input = document.getElementById('unified-node-port');
    if (!input.reportValidity()) return;
    document.querySelectorAll('[data-sub-defaults-form] [data-sub-node-port]').forEach(field => field.value = input.value);
    notify('端口已填入，请点击保存统一节点配置', false);
    return;
  }
  const hop = event.target.closest('[data-hop-toggle]');
  if (hop) {
    hop.disabled = true;
    try {
      await postJson('/port-hopping/' + hop.dataset.hopToggle, {body: new URLSearchParams({csrf: subscriptionCsrf()}).toString(), headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
      notify('端口跳跃已更新，请刷新订阅', false); await loadSubscription('');
    } catch (error) { notify(error.message || '设置失败', true); }
    finally { hop.disabled = false; }
    return;
  }
  const defaults = event.target.closest('[data-subscription-defaults]');
  if (defaults) { loadSubscription(''); return; }
  const open = event.target.closest('[data-subscription-user-id]');
  if (open) { loadSubscription(open.dataset.subscriptionUserId); return; }
  const remove = event.target.closest('[data-sub-node-remove]');
  if (remove) { remove.closest('.subscription-node-row').remove(); return; }
  const button = event.target.closest('[data-sub-action]');
  if (!button) return;
  const action = button.dataset.subAction;
  const content = button.closest('[data-subscription-content]');
  const userId = content.dataset.userId;
  const id = content.dataset.subscriptionId;
  if (action === 'add') {
    content.querySelector('[data-sub-node-rows]').insertAdjacentHTML('beforeend', subscriptionNodeRow({port:443})); return;
  }
  if (action === 'copy') {
    const copied = await copyText(content.querySelector('.subscription-url').value);
    notify(copied ? '订阅链接已复制' : '请手动复制订阅链接', !copied); return;
  }
  if (action === 'regenerate' && !window.confirm('旧订阅链接和节点密码都将失效，并断开该用户的旧连接，确认重置？')) return;
  button.disabled = true;
  try {
    let path = '/subscriptions/' + id + '/' + action;
    const form = new URLSearchParams({csrf: subscriptionCsrf()});
    if (action === 'create') { path = '/subscriptions'; form.set('user_id', userId); }
    if (action === 'inherit') { path = '/subscriptions/' + id + '/nodes'; form.set('nodes', '[]'); }
    await postJson(path, {body: form.toString(), headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
    notify('订阅已更新', false); await loadSubscription(userId);
  } catch (error) { notify(error.message || '操作失败', true); }
  finally { button.disabled = false; }
});
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-sub-defaults-form]');
  if (!form) return;
  event.preventDefault();
  const nodes = Array.from(form.querySelectorAll('.subscription-node-row')).map(function(row) {
    return {label: row.querySelector('[data-sub-node-label]').value.trim(), host: row.querySelector('[data-sub-node-host]').value.trim(),
      port: Number(row.querySelector('[data-sub-node-port]').value), pin_sha256: row.querySelector('[data-sub-node-pin]').value.trim(),
      enabled: row.querySelector('[data-sub-node-enabled]').checked};
  });
  const button = form.querySelector('[type=submit]'); button.disabled = true;
  try {
    await postJson('/subscriptions/defaults', {body: new URLSearchParams({csrf: subscriptionCsrf(), nodes: JSON.stringify(nodes)}).toString(),
      headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
    const portDisplay = document.querySelector('[data-subscription-port]');
    if (portDisplay) portDisplay.textContent = 'UDP ' + Array.from(new Set(nodes.filter(n => n.enabled).map(n => String(n.port)))).join(' / ');
    notify('已保存，用户刷新原订阅链接即可获取最新配置', false);
  } catch (error) { notify(error.message || '保存失败', true); }
  finally { button.disabled = false; }
});


const premiumUserSelect = document.querySelector('[data-user-type-select]');
if (premiumUserSelect) {
  const selectedGroup = new URLSearchParams(window.location.search).get('type');
  if (selectedGroup === 'premium') premiumUserSelect.value = '1';
  function applyUserPlan() {
    const form = premiumUserSelect.closest('form');
    if (premiumUserSelect.value === '1') {
      form.elements.namedItem('device_limit').value = '100';
      form.elements.namedItem('traffic_limit_gb').value = '250';
    }
  }
  premiumUserSelect.addEventListener('change', applyUserPlan);
  applyUserPlan();
}
const lineForm = document.querySelector('[data-node-enrollment-form]');
if (lineForm) {
  if (new URLSearchParams(window.location.search).get('type') === 'premium') lineForm.elements.namedItem('tier').value = 'premium';
  function fillRegionDefaults() {
    const region = lineForm.elements.namedItem('region').value;
    const premium = lineForm.elements.namedItem('tier').value === 'premium';
    const names = {hk:'香港', us:'美国', jp:'日本', sg:'新加坡'};
    if (premium && names[region]) {
      lineForm.elements.namedItem('name').value = '私家车-' + names[region] + '-专线';
    }
    lineForm.elements.namedItem('region').required = premium;
    lineForm.elements.namedItem('subscription_host').required = premium;
  }
  fillRegionDefaults();
  lineForm.elements.namedItem('region').addEventListener('change', fillRegionDefaults);
  lineForm.elements.namedItem('tier').addEventListener('change', fillRegionDefaults);
}
function lineTcpVerdict(check) {
  if (check && check.running) return {text:'正在检测…', kind:'muted'};
  if (!check || !check.checkedAt) return {text:'线路待检测', kind:'muted'};
  if (check.stale) return {text:'结果已过期 · 请重测', kind:'muted'};
  const rows = (check.domestic || []).flatMap(function(group) { return group.rows || []; });
  if (rows.some(function(row) { return row.state === 'fail'; })) return {text:'TCP阻断', kind:'bad'};
  if (rows.length === 3 * (check.expectedPorts || 2) && rows.every(function(row) { return row.state === 'pass'; }) && !check.domesticError) return {text:'TCP 可达', kind:'ok'};
  return {text:'检测不完整 · 请重测', kind:'muted'};
}
function lineVerdict(check) {
  if (!check || !check.checkedAt || check.stale || check.running) return lineTcpVerdict(check);
  const rows = (check.domestic || []).flatMap(function(group) { return group.rows || []; });
  const proxy = check.proxy || [];
  if (proxy.some(function(row) { return row.state === 'fail'; })) return {text:'代理实测异常', kind:'bad'};
  if (check.dns === 'fail') return {text:'域名未包含本节点', kind:'bad'};
  if (rows.some(function(row) { return row.state === 'fail'; })) return {
    text:check.failureRounds >= 2 && (check.tcpReference || []).length === (check.expectedPorts || 2) && check.tcpReference.every(function(row) { return row.state === 'pass'; }) && proxy.length && proxy.some(function(row) { return row.state === 'pass'; }) && proxy.every(function(row) { return row.state === 'pass' || row.state === 'unknown'; }) ? '疑似国内路径受阻' : '国内 TCP 异常 · 待复测', kind:'bad'};
  return lineTcpVerdict(check);
}
function networkRate(value) {
  if (!Number.isFinite(value) || value < 0) return '—';
  const mbps = value * 8 / 1000000;
  return mbps >= 1 ? mbps.toFixed(2) + ' Mbps' : (value * 8 / 1000).toFixed(1) + ' Kbps';
}
function applyLineMonitor(payload) {
  if (!payload || typeof payload.network !== 'object' || typeof payload.checks !== 'object') return;
  applyAggregateNetwork(payload);
  document.querySelectorAll('.machine-budget-row[data-origin-id]').forEach(function(card) {
    const id = card.dataset.originId;
    const network = payload.network[id] || {fresh:false,points:[]};
    const fresh = network.fresh === true && Number.isFinite(network.observedAt);
    const speed = card.querySelector('.machine-speed');
    if (speed) {
      speed.dataset.stale = String(!fresh);
      speed.querySelector('[data-speed-rx]').textContent = '↓ ' + networkRate(fresh ? network.rx : null);
      speed.querySelector('[data-speed-tx]').textContent = '↑ ' + networkRate(fresh ? network.tx : null);
      speed.querySelector('[data-speed-time]').textContent = fresh ? '最近 5 分钟 · ' + liveTime(network.observedAt, false) : '网卡速度 · 数据缺失';
      const now = Date.now() / 1000;
      const points = (Array.isArray(network.points) ? network.points : []).filter(function(p) {
        return p && Number.isFinite(p.at) && now - p.at >= -5 && now - p.at <= 300;
      });
      const valid = function(value) { return Number.isFinite(value) && value >= 0; };
      const scale = Math.max(1, ...points.flatMap(function(p) { return [p.rx, p.tx].filter(valid); }));
      ['rx','tx'].forEach(function(direction) {
        let path = '', previous = null;
        points.forEach(function(p) {
          if (!valid(p[direction])) { previous = null; return; }
          const x = Math.max(0, Math.min(240, 240 - (now - p.at) * .8));
          const y = 40 - p[direction] / scale * 36;
          path += (previous !== null && p.at - previous <= 20 ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2) + ' ';
          previous = p.at;
        });
        speed.querySelector('[data-speed-' + direction + '-line]').setAttribute('d', path);
        const area = speed.querySelector('[data-speed-' + direction + '-area]');
        if (area) area.setAttribute('d',chartArea(path,42));
      });
      speed.querySelector('svg').setAttribute('aria-label', '最近 5 分钟网卡速度，入站 ' + networkRate(fresh ? network.rx : null) + '，出站 ' + networkRate(fresh ? network.tx : null));
    }
    const check = payload.checks[id];
    const verdict = lineVerdict(check);
    const tcpVerdict = lineTcpVerdict(check);
    const status = card.querySelector('[data-line-status]');
    if (status) { status.textContent = tcpVerdict.text; status.parentElement.className = 'line-check-button ' + tcpVerdict.kind; }
    const dialog = Array.from(document.querySelectorAll('[data-line-dialog]')).find(function(d) { return d.dataset.lineDialog === id; });
    if (!dialog || !check || !check.checkedAt) return;
    dialog.querySelector('[data-check-time]').textContent = '检测时间：' + liveTime(check.checkedAt, true) + (check.stale ? ' · 已过期' : '');
    dialog.querySelector('[data-check-verdict]').textContent = verdict.text + '。国内 Hysteria2 实际连接仍未验证，不能据此承诺所有用户可用。';
    const domestic = dialog.querySelector('[data-check-domestic]');
    domestic.replaceChildren();
    (check.domestic || []).forEach(function(group) {
      (group.rows || []).forEach(function(row) {
        const line = document.createElement('p');
        line.className = 'line-check-evidence ' + ({pass:'ok',fail:'bad',unknown:'muted'}[row.state] || 'muted');
        line.textContent = row.operator + (row.city ? ' · ' + row.city : '') + ' · TCP ' + row.port + '：' + ({pass:'可达',fail:'无响应',unknown:'未取得有效结果'}[row.state] || '未验证') +
          (Number.isFinite(row.latencyMs) ? ' · ' + row.latencyMs.toFixed(1) + ' ms' : '') + (Number.isFinite(row.loss) ? ' · 丢包 ' + row.loss + '%' : '');
        domestic.appendChild(line);
      });
      if (typeof group.measurementId === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(group.measurementId)) {
        const link = document.createElement('a');
        link.href = 'https://api.globalping.io/v1/measurements/' + group.measurementId;
        link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = '查看原始探测证据'; link.className = 'line-check-evidence'; domestic.appendChild(link);
      }
    });
    if (check.domesticError) { const line = document.createElement('p'); line.className = 'line-check-evidence warning'; line.textContent = check.domesticError; domestic.appendChild(line); }
    const proxy = dialog.querySelector('[data-check-proxy]');
    proxy.replaceChildren();
    const source = document.createElement('p'); source.className = 'line-check-evidence muted'; source.textContent = '探测来源：' + check.source; proxy.appendChild(source);
    (check.tcpReference || []).forEach(function(row) {
      const line = document.createElement('p'); line.className = 'line-check-evidence muted';
      line.textContent = '面板侧 TCP ' + row.port + ' 基准：' + (row.state === 'pass' ? '可达' : '失败，不能据此推断国内封锁'); proxy.appendChild(line);
    });
    (check.proxy || []).forEach(function(row) {
      const line = document.createElement('p'); line.className = 'line-check-evidence ' + ({pass:'ok',fail:'bad',unknown:'muted'}[row.state] || 'muted');
      line.textContent = 'UDP ' + row.port + '：' + (row.state === 'pass' ? '代理认证与 HTTPS 出网成功' : (row.reason || '连接或出网失败')); proxy.appendChild(line);
    });
    dialog.querySelector('[data-check-dns]').textContent = '面板侧域名解析：' + ({pass:'包含当前节点 IP',fail:'未包含当前节点 IP',unknown:'未取得结果'}[check.dns] || '未验证');
  });
}
let lineMonitorBusy = false;
async function refreshLineMonitor() {
  if (lineMonitorBusy || document.hidden || !document.querySelector('[data-speed-chart]')) return;
  lineMonitorBusy = true;
  const controller = new AbortController(); const timer = setTimeout(function() { controller.abort(); }, 3000);
  const requestedRangeVersion=chartRangeVersion;
  try {
    const response = await fetch('/api/v1/line-monitor?range='+chartRange, {credentials:'same-origin',cache:'no-store',signal:controller.signal});
    if (!response.ok) throw new Error('unavailable');
    const payload=await response.json();
    if(requestedRangeVersion===chartRangeVersion) applyLineMonitor(payload);
  } catch (error) {
    if(requestedRangeVersion!==chartRangeVersion) return;
    applyAggregateNetwork({network:{}});
    document.querySelectorAll('.machine-speed').forEach(function(speed) {
      speed.dataset.stale = 'true'; speed.querySelector('[data-speed-rx]').textContent = '↓ 入站 —'; speed.querySelector('[data-speed-tx]').textContent = '↑ 出站 —'; speed.querySelector('[data-speed-time]').textContent = '实时数据暂不可用';
    });
    document.querySelectorAll('[data-line-status]').forEach(function(status) { status.textContent = '检测状态暂不可用'; });
  } finally { clearTimeout(timer); lineMonitorBusy = false; if(requestedRangeVersion!==chartRangeVersion) refreshLineMonitor(); }
}
document.addEventListener('submit', async function(event) {
  const form = event.target.closest('[data-line-check-form]'); if (!form) return;
  event.preventDefault(); const button = form.querySelector('button[type="submit"]'); const feedback = form.querySelector('[data-check-action]');
  if (button.disabled) return; button.disabled = true;
  const controller = new AbortController(); const timer = setTimeout(function() { controller.abort(); }, 10000);
  try {
    const response = await fetch(form.action, {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(new FormData(form)),signal:controller.signal});
    const result = await response.json(); feedback.textContent = result.message || '检测请求未完成'; await refreshLineMonitor();
  } catch (error) { feedback.textContent = '请求未完成，请稍后查看检测结果'; }
  finally { clearTimeout(timer); button.disabled = false; }
});
if (document.querySelector('[data-speed-chart]')) { refreshLineMonitor(); setInterval(refreshLineMonitor, 5000); document.addEventListener('visibilitychange', refreshLineMonitor); }

"""

PAGE_SCRIPT += """
function resourceBytes(value){if(!Number.isFinite(value)||value<0)return '—';const unit=value>=1073741824?'GiB':'MiB';return (value/(unit==='GiB'?1073741824:1048576)).toFixed(1)+' '+unit;}
function resourceUptime(seconds){if(!Number.isFinite(seconds)||seconds<0)return '—';return Math.floor(seconds/86400)+'天 '+Math.floor(seconds%86400/3600)+'小时 '+Math.floor(seconds%3600/60)+'分钟';}
document.addEventListener('click',event=>{if(event.target.closest('[data-resource-refresh]')){event.preventDefault();refreshServerMonitor();}});
let serverMonitorBusy = false;
async function refreshServerMonitor() {
  if (serverMonitorBusy || document.hidden || document.body.dataset.consoleView !== 'nodes') return;
  serverMonitorBusy = true;
  const controller = new AbortController(); const timer = setTimeout(()=>controller.abort(), 8000);
  try {
    const response = await fetch('/api/v1/server-monitor', {credentials:'same-origin',cache:'no-store',signal:controller.signal});
    if (!response.ok) throw new Error('资源暂不可用');
    const data = await response.json();
    document.querySelectorAll('.machine-budget-row').forEach(card=>{
      const id=card.dataset.originId; const remote=id.startsWith('node:'); const key=id.slice(5);
      const sample=remote?data.servers[key]:data.local; const fresh=sample && sample.fresh;
      card.querySelectorAll('[data-resource]').forEach(cell=>{
        const value=fresh?sample[cell.dataset.resource]:null;
        const valid=Number.isFinite(value) && value>=0 && value<=100;
        cell.querySelector('strong').textContent=valid?value.toFixed(1)+'%':'—';
        cell.querySelector('progress').value=valid?value:0;
        const detail=cell.querySelector('[data-resource-detail]');
        if(detail){const key=cell.dataset.resource;const used=fresh?sample[key+'Used']:null;const total=fresh?sample[key+'Total']:null;detail.textContent=Number.isFinite(used)&&Number.isFinite(total)?resourceBytes(used)+' / '+resourceBytes(total):key==='cpu'?'':'—';}

      });
      const uptime=card.querySelector('[data-resource-uptime]');
      if(uptime) uptime.textContent=fresh?(sample.uptimeLabel || resourceUptime(sample.uptime)):'—';
      const state=card.querySelector('[data-resource-state]');
      if(state) state.textContent=fresh?'每 5 秒刷新 · '+new Date(sample.observedAt*1000).toLocaleTimeString():sample?'资源数据已过期':'等待新版 Agent 上报';
      card.querySelectorAll('[data-server-operation] button').forEach(b=>b.disabled=!fresh);
      const op=data.operations[key];const status=card.querySelector('[data-operation-status]');
      if(status && !op) status.textContent='';
      if (status && op) {
        if (op.last_error === 'SESSIONS_NOT_DRAINED') {
          status.textContent = '连接尚未排空，已取消操作；服务保持运行，请在空闲时重试';
        } else if (op.last_error) {
          status.textContent = '操作失败：' + op.last_error;
        } else if (op.acked_at) {
          status.textContent = '节点已确认重启安排，请等待重新上线';
        } else {
          status.textContent = Date.now()/1000-op.created_at > 120
            ? '操作已超时，未确认执行' : '操作已排队，等待节点确认';
        }
      }
    });
  } catch (_) {
    document.querySelectorAll('[data-resource-state]').forEach(e=>e.textContent='资源暂不可用');
    document.querySelectorAll('[data-resource] strong').forEach(e=>e.textContent='—');
    document.querySelectorAll('[data-resource] progress').forEach(e=>e.value=0);
    document.querySelectorAll('[data-resource-detail],[data-resource-uptime]').forEach(e=>e.textContent='—');
    document.querySelectorAll('[data-server-operation] button').forEach(e=>e.disabled=true);
  } finally { clearTimeout(timer);serverMonitorBusy=false; }
}
document.addEventListener('submit',async event=>{
  const form=event.target.closest('[data-server-operation]');if(!form)return;
  event.preventDefault();
  const card=form.closest('.machine-budget-row');const name=card.querySelector('.machine-budget-head strong').textContent;
  const button=form.querySelector('button');if(button.disabled)return;
  if(!confirm('确认'+button.textContent+'：'+name+'？该节点连接将短暂中断。'))return;
  button.disabled=true;const state=card.querySelector('[data-operation-status]');state.textContent='正在提交…';
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);
  try {const response=await fetch(form.action,{method:'POST',credentials:'same-origin',body:new URLSearchParams(new FormData(form)),signal:controller.signal});const result=await response.json();state.textContent=result.message||'请求未完成';}
  catch(_){state.textContent='未收到确认，请查看状态，勿重复提交';}
  finally{clearTimeout(timer);setTimeout(refreshServerMonitor,1500);}
});
if(document.querySelector('.node-server-tools')){setInterval(refreshServerMonitor,5000);refreshServerMonitor();window.addEventListener('hashchange',refreshServerMonitor);window.addEventListener('consoleviewchange',refreshServerMonitor);document.addEventListener('visibilitychange',refreshServerMonitor);}
"""
