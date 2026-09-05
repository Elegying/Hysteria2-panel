"""Static browser assets kept outside the application entrypoint."""

FAVICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<title>Hysteria 2 Panel</title><rect x="2" y="2" width="60" height="60" rx="14" fill="#0b1a2c" stroke="#284867" stroke-width="2"/>
<path fill="#4bc493" d="M9 16h7v12h11V16h7v32h-7V35H16v13H9z"/>
<path fill="#f3f7ff" d="M37 24c0-7 4-11 11-11s11 4 11 10c0 5-3 8-8 12l-6 6h14v7H37v-8l10-9c4-3 5-5 5-7 0-3-1-4-4-4-3 0-4 2-4 5h-7z"/>
</svg>"""

PAGE_STYLE = """
:root{color-scheme:dark;--bg:#06111f;--surface:#0b1a2c;--surface-2:#132438;--text:#f3f7ff;--muted:#9aaac0;--line:#22364b;--accent:#5f91f7;--teal:#25b99a;--success:#4bc493;--warning:#f5b54b;--danger:#ff6675}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;text-rendering:optimizeLegibility}
main{width:min(1420px,calc(100% - 40px));margin:20px auto 42px}.topbar{display:flex;align-items:center;gap:12px;background:#102846;border:1px solid #284867;border-radius:20px;padding:18px 22px;margin-bottom:16px}.brand{min-width:max-content}.eyebrow{display:inline-block;border:1px solid #405b7c;border-radius:999px;padding:7px 13px;color:#c8d7ef;font-size:12px;letter-spacing:.12em}.topbar h1{font-size:28px;margin:0 4px}.topbar-spacer{flex:1}.pill{display:flex;align-items:center;gap:6px;min-height:44px;border:1px solid #34495f;border-radius:10px;padding:9px 14px;background:#1b2c40;color:var(--muted);white-space:nowrap}.pill strong{color:var(--text);margin:0}
h1,h2,h3,p{margin-top:0}h2{font-size:20px;margin-bottom:4px}h3{font-size:16px}.muted{color:var(--muted)}.ok{color:var(--success)}.bad{color:var(--danger)}.warning{color:var(--warning)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}.metric,.card{background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 28px rgba(0,0,0,.12)}.metric{padding:16px 18px;border-top:3px solid var(--teal);min-width:0}.metric>strong{display:block;font-size:26px;margin:7px 0 2px;font-variant-numeric:tabular-nums}.metric span{color:var(--muted)}.metric-warning{display:block;color:var(--warning);font-size:12px}.machine-stats{padding:16px 18px}.machine-stats .section-head{margin-bottom:10px}.machine-section-head{align-items:center;padding-bottom:10px}.machine-section-head p{margin:0;font-size:12px}.machine-count{flex:0 0 auto;padding:5px 9px;border:1px solid #375170;border-radius:999px;color:var(--muted);font-size:11px;white-space:nowrap}.machine-warning{margin-bottom:10px}.machine-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.machine-card{min-width:0;padding:12px;border:1px solid #283b50;border-radius:12px;background:var(--surface-2)}.machine-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.machine-card-head>div{min-width:0}.machine-card-head strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.machine-card-head>span{font-weight:750;white-space:nowrap}.machine-kind{display:block;font-size:11px;margin-top:1px}.machine-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:9px 0}.machine-fact{min-width:0;padding:7px 8px;border:1px solid #2b4056;border-radius:9px;background:#101f31}.machine-fact span,.machine-fact strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.machine-fact span{color:var(--muted);font-size:10px}.machine-fact strong{margin-top:2px;font-size:13px}.machine-budget{padding-top:8px;border-top:1px solid var(--line)}.machine-observed{display:block;margin-top:7px;font-size:10px;text-align:right}
.operations{display:grid;gap:16px;margin-bottom:16px;align-items:start}.dashboard-trio{align-items:stretch;grid-template-columns:minmax(0,1.45fr) minmax(270px,.85fr) minmax(240px,.72fr)}.dashboard-trio>.card{height:100%;margin-bottom:0}.card{padding:20px;margin-bottom:16px}.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:1px solid var(--line);padding-bottom:15px;margin-bottom:16px}.dashboard-trio .section-head{padding-bottom:12px;margin-bottom:12px}.service-badge{border-radius:999px;padding:8px 13px;background:#123833;color:var(--success);font-weight:700;white-space:nowrap}.service-badge.off{background:#3a2028;color:#ff9aa4}
.button-row,.actions{display:flex;flex-wrap:wrap;gap:9px}.service-actions>.button{display:inline-flex;align-items:center;justify-content:center;text-align:center}button,.button{display:inline-block;border:1px solid transparent;border-radius:10px;background:var(--accent);color:#fff;padding:10px 15px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer;transition:filter .15s ease,transform .15s ease}button:hover,.button:hover{filter:brightness(1.08);transform:translateY(-1px)}button:active,.button:active{transform:none}button.secondary,.button.secondary{background:#1b2c40;border-color:#34495f}button.success{background:var(--success);color:#082016}button.warning{background:var(--warning);color:#251a05}button.danger{background:var(--danger)}button.ghost{background:transparent;border-color:#3a526b;color:#dce8f8}form.inline{display:inline}.system-actions{flex:0 0 auto}.system-actions button{padding:8px 11px}
.resource-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.resource,.detail{background:var(--surface-2);border:1px solid #283b50;border-radius:14px;padding:18px}.resource{padding:12px}.resource strong{font-size:18px;margin-top:4px}.resource small{font-size:11px}.resource strong,.detail strong{display:block}.certificate-resource{grid-column:1/-1;display:flex;align-items:baseline;gap:8px;min-width:0}.certificate-resource span{white-space:nowrap}.certificate-resource strong{margin:0;font-size:16px;white-space:nowrap}.service-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.compact-detail{padding:12px}.compact-detail strong{font-size:18px;margin-top:4px}.port-detail{display:flex;align-items:center;justify-content:space-between;gap:12px}.port-detail>div strong{white-space:nowrap}.egress-control{display:grid;justify-items:end;gap:3px;margin:0}.egress-state{color:var(--muted);font-size:11px;font-weight:750;white-space:nowrap}.egress-state.on{color:var(--success)}.egress-state.unknown{color:var(--warning)}.egress-switch{display:inline-flex;align-items:center;gap:6px;padding:5px 7px;background:#1b2c40;border-color:#40566f;border-radius:999px;font-size:11px}.egress-switch.on{background:#123833;border-color:#26745d;color:#caffec}.egress-switch.unknown{border-color:#8b6b30}.egress-switch-track{position:relative;width:30px;height:18px;border-radius:999px;background:#52647a;box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}.egress-switch-track>span{position:absolute;top:3px;left:3px;width:12px;height:12px;border-radius:50%;background:#fff;transition:transform .15s ease}.egress-switch.on .egress-switch-track{background:var(--success)}.egress-switch.on .egress-switch-track>span{transform:translateX(12px)}.egress-switch-action{min-width:22px;text-align:center}.bbr-detail strong,.version-row strong{font-size:18px;margin-top:4px}.bbr-detail small{display:block;font-size:11px;margin-top:3px}.version-panel>p{font-size:12px;margin:4px 0 0}.version-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.version-actions{flex-wrap:nowrap}.version-actions form{margin:0}.compact-button{padding:8px 11px}.notice{padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#10233a;color:#c7d6ea}
.rank-list{display:grid;gap:6px}.rank-row{display:grid;grid-template-columns:28px minmax(0,1fr);align-items:center;gap:7px;padding:7px 9px;background:var(--surface-2);border:1px solid #283b50;border-radius:10px}.rank-main{display:flex;align-items:baseline;gap:8px;min-width:0}.rank-number{color:var(--accent);font-weight:800}.rank-name{font-weight:700;overflow:hidden;text-overflow:ellipsis}.rank-traffic{color:var(--muted);font-size:12px;white-space:nowrap}
.create-grid{display:grid;grid-template-columns:2fr 1fr 1fr auto;align-items:end;gap:12px;margin-bottom:22px}.section-actions,.user-tools{display:flex;align-items:center;gap:9px}.user-section-head{display:flex;align-items:center;flex-wrap:wrap}.user-heading{flex:1 1 240px}.user-section-head .section-actions{flex:0 0 auto}.user-tools{justify-content:space-between;margin-bottom:14px}.user-filters{display:grid;grid-template-columns:minmax(220px,2fr) repeat(3,minmax(120px,1fr)) auto;align-items:end;gap:9px;flex:1}.user-filters label{margin-bottom:4px;font-size:12px;color:var(--muted)}.user-filters button{padding:10px 12px}.search-status{margin:0;white-space:nowrap}.filter-empty{margin:0 0 14px;padding:11px 14px;border:1px dashed #3a526b;border-radius:10px;text-align:center}label{display:block;font-weight:650;margin-bottom:6px}input,textarea,select{width:100%;padding:11px 13px;border:1px solid #3a4d63;border-radius:9px;background:#101f31;color:var(--text);font:inherit}input:focus,textarea:focus,select:focus,button:focus-visible,.button:focus-visible{outline:3px solid rgba(95,145,247,.38);outline-offset:2px}button:disabled{cursor:wait;opacity:.65}.table-wrap{overflow-x:auto;scrollbar-gutter:stable}table{width:100%;border-collapse:separate;border-spacing:0;min-width:1050px;font-variant-numeric:tabular-nums}th,td{padding:13px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}th{color:var(--muted);font-size:13px;white-space:nowrap}.user-table th{position:sticky;top:0;z-index:2;background:var(--surface);box-shadow:0 1px 0 var(--line)}.user-table tbody tr{transition:background-color .15s ease}.user-table tbody tr:hover{background:#0f2135}.user-table tr[data-over-device-limit="1"]{background:rgba(255,102,117,.07)}.over-limit-name{color:var(--danger)}.limit-alert{display:block;margin-top:2px;color:var(--danger);font-size:11px;font-weight:700}.limit-alert[hidden]{display:none}.sort-link{color:inherit;text-decoration:none}.sort-link:hover{text-decoration:underline}.status{font-weight:750}.enabled{color:var(--success)}.disabled{color:var(--danger)}progress{width:150px;height:10px;accent-color:var(--accent)}.traffic-cell{min-width:190px}.traffic-label{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--muted);margin-top:4px}.actions{min-width:420px}.user-table tr[hidden]{display:none}.update-state{margin-top:6px}.update-state[data-state="failed"]{color:var(--danger)}.update-state[data-state="running"],.update-state[data-state="queued"]{color:var(--warning)}.update-state[data-state="success"]{color:var(--success)}
.checkbox-field{display:flex;align-items:flex-start;gap:10px;margin:0;padding:12px;border:1px solid #3a4d63;border-radius:10px;background:#101f31}.checkbox-field input{width:auto;margin:4px 0 0;flex:0 0 auto}.checkbox-field span{font-weight:650}.checkbox-field small{display:block;margin-top:3px;font-weight:400}
.login{width:min(430px,100%);margin:12vh auto}.login-form{display:grid;gap:12px}.login-actions{margin:4px 0 0}.login-actions button{min-width:110px}.copy-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px;margin-bottom:16px}.error{color:var(--danger)}code{word-break:break-all}
.migration-dialog{width:min(820px,calc(100% - 32px));max-height:min(86vh,760px);padding:0;border:1px solid #35506d;border-radius:18px;background:var(--surface);color:var(--text);box-shadow:0 24px 80px rgba(0,0,0,.55);overflow:auto}.migration-dialog::backdrop{background:rgba(1,8,18,.78);backdrop-filter:blur(4px)}.credentials-dialog{width:min(680px,calc(100% - 32px))}.create-dialog{width:min(560px,calc(100% - 32px))}.create-dialog .create-grid{grid-template-columns:1fr 1fr;margin-bottom:0}.create-dialog .wide,.create-dialog .create-grid>button{grid-column:1/-1}.credentials-dialog textarea{min-height:118px}.qr-panel{display:grid;justify-items:center;gap:8px;margin:16px 0}.qr-panel[hidden]{display:none}.qr-canvas{display:block;width:min(100%,320px);height:auto;border:10px solid #fff;border-radius:8px;background:#fff;image-rendering:pixelated}.credential-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:14px 0}.credential-actions button{width:100%}.dialog-shell{padding:22px}.dialog-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:16px}.dialog-head h2{margin-bottom:4px}.dialog-close{flex:0 0 auto;width:40px;height:40px;padding:0;border-radius:50%;background:#1b2c40;border-color:#34495f;font-size:24px;line-height:1}.migration-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.migration-grid .detail{height:100%}.migration-grid p:last-child{margin-bottom:0}.toast{position:fixed;right:18px;bottom:18px;z-index:20;max-width:min(420px,calc(100% - 36px));margin:0;padding:11px 14px;border:1px solid #375170;border-radius:10px;background:#102846;box-shadow:0 12px 36px rgba(0,0,0,.4)}.toast.error{border-color:#8a3844;color:#ffd5da}.toast[hidden]{display:none}
.node-onboarding-dialog{width:min(900px,calc(100% - 32px))}.node-enrollment-grid{display:grid;grid-template-columns:minmax(190px,1fr) minmax(190px,1fr) minmax(120px,.55fr) auto;align-items:end;gap:10px;margin:16px 0}.enrollment-result{margin:16px 0;padding:14px;border:1px solid #375170;border-radius:12px;background:#0d2035}.enrollment-result[hidden]{display:none}.enrollment-result textarea{min-height:220px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}.node-list-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-top:20px}.node-list{display:grid;gap:8px}.node-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px;padding:11px 12px;border:1px solid #283b50;border-radius:11px;background:var(--surface-2)}.node-row>div:first-child{min-width:0}.node-row strong,.node-row small{display:block}.node-row small{margin-top:2px;overflow-wrap:anywhere}.node-row>span{font-weight:750;white-space:nowrap}.node-actions{display:flex;flex-wrap:wrap;gap:8px}.node-actions form{margin:0}
.operation-guides{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 18px}.operation-guide{padding:15px;border:1px solid #375170;border-radius:13px;background:#0d2035}.operation-guide h3{margin:0 0 12px}.danger-guide{border-color:#80505a}.numbered-steps{list-style:none;counter-reset:guide-step;display:grid;gap:11px;margin:0;padding:0}.numbered-steps li{counter-increment:guide-step;display:grid;grid-template-columns:34px minmax(0,1fr);column-gap:9px;align-items:start}.numbered-steps li::before{content:counter(guide-step);display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:var(--accent);color:#03101e;font-weight:850;grid-row:1/3}.danger-guide .numbered-steps li::before{background:var(--warning)}.numbered-steps strong,.numbered-steps span{grid-column:2}.numbered-steps span{margin-top:2px;color:var(--muted);font-size:13px;line-height:1.45}.budget-summary{display:grid;gap:2px;min-width:0}.budget-main{display:flex;align-items:baseline;justify-content:space-between;gap:8px}.budget-main span,.budget-main strong{white-space:nowrap}.budget-main strong{font-size:12px}.budget-summary small{font-size:10px;white-space:normal}.budget-editor{margin-top:6px}.budget-editor summary{width:max-content;color:#c8d7ef;font-size:11px;font-weight:750;cursor:pointer}.budget-editor summary:hover{color:var(--text)}.budget-editor[open] summary{margin-bottom:7px}.budget-form{display:grid;grid-template-columns:repeat(4,minmax(80px,1fr)) auto;gap:6px;align-items:end;min-width:0}.budget-form label{font-size:10px;color:var(--muted)}.budget-form input{min-width:0;padding:7px 8px;margin-top:3px}.budget-form button{padding:8px 10px;white-space:nowrap}.legacy-cleanup-form{margin-top:7px}.legacy-cleanup-form button{width:100%}.wide-detail{grid-column:1/-1}
@media(max-width:640px){.operation-guides{grid-template-columns:1fr}}
@media(min-width:641px) and (max-width:1300px){.brand{display:none}.topbar h1{white-space:nowrap}}
@media(max-width:1050px){.topbar{flex-wrap:wrap}.topbar-spacer{display:none}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.operations{grid-template-columns:1fr}.create-grid{grid-template-columns:1fr 1fr}.create-grid .wide{grid-column:1/-1}.node-enrollment-grid{grid-template-columns:1fr 1fr}.node-enrollment-grid>button{width:100%}.user-filters{grid-template-columns:minmax(200px,2fr) repeat(3,minmax(105px,1fr)) auto}.budget-form{grid-template-columns:repeat(2,minmax(0,1fr))}.budget-form button{grid-column:1/-1}}
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
.machine-stats{padding:20px 22px}.machine-grid{gap:12px}.machine-card,.resource,.detail,.rank-row{border-color:#2b4058;background:linear-gradient(180deg,#142338,#111f31)}.machine-card{padding:15px;border-radius:14px}.machine-facts{gap:8px;margin:12px 0}.machine-fact{padding:9px 10px;border-color:#2a415a;background:#0d1b2c}.machine-fact span{font-size:11px}.machine-fact strong{font-size:14px}.machine-observed{margin-top:9px}.budget-editor summary{display:inline-flex;align-items:center;min-height:36px;padding:6px 10px;border:1px solid #39536e;border-radius:8px;background:#13243a;font-size:12px}
.machine-budget-list{display:grid}.machine-budget-row{min-width:0;padding:18px 2px;border-bottom:1px solid var(--line)}.machine-budget-row:first-child{padding-top:2px}.machine-budget-row:last-child{padding-bottom:2px;border-bottom:0}.machine-budget-head,.machine-budget-usage,.machine-budget-meta{display:flex;align-items:center;justify-content:space-between;gap:14px}.machine-budget-head>div{min-width:0}.machine-budget-head>div>strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:18px}.machine-budget-head small{display:block;margin-top:3px}.machine-online{flex:0 0 auto;color:#dce5f3;font-size:15px;white-space:nowrap}.machine-online strong{font-size:20px}.machine-budget-row>progress{display:block;width:100%;height:10px;margin:14px 0 10px;background:#344056}.machine-budget-row>progress::-webkit-progress-bar{background:#344056}.machine-budget-row>progress::-webkit-progress-value{background:linear-gradient(90deg,#a9c4ff,#7fa6f8)}.machine-budget-usage>strong{font-size:17px;font-variant-numeric:tabular-nums}.machine-budget-usage>span{font-size:12px;white-space:nowrap}.machine-budget-meta{align-items:flex-end;margin-top:8px}.machine-budget-meta>small{min-width:0;line-height:1.45}.machine-budget-edit,.legacy-cleanup-form{flex:0 0 auto;margin:0}.budget-dialog{width:min(680px,calc(100% - 32px))}.budget-dialog-form{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.budget-dialog-form button{grid-column:1/-1}.budget-dialog-form label{color:var(--muted)}
.dashboard-trio{grid-template-columns:minmax(0,1.35fr) minmax(280px,.82fr) minmax(250px,.74fr);gap:14px}.dashboard-trio>.card{min-width:0}.service-badge{border:1px solid rgba(86,210,159,.3);background:rgba(52,145,109,.15);font-size:12px}.service-badge.off{border-color:rgba(255,120,134,.28);background:rgba(173,58,72,.16)}
button,.button{min-height:42px;padding:9px 14px;border-radius:10px;background:linear-gradient(180deg,var(--accent),var(--accent-strong));box-shadow:0 5px 14px rgba(34,80,157,.18);transition:background-color .15s ease,border-color .15s ease,box-shadow .15s ease,transform .15s ease}button:hover,.button:hover{filter:none;box-shadow:0 8px 18px rgba(34,80,157,.24);transform:translateY(-1px)}button.secondary,.button.secondary{border-color:#3a506b;background:#17273b;box-shadow:none}button.secondary:hover,.button.secondary:hover,button.ghost:hover{border-color:#58718f;background:#1b3048}button.success{background:linear-gradient(180deg,#5fd9a7,#3dbb8b);box-shadow:0 5px 14px rgba(39,139,101,.18)}button.warning{border-color:rgba(243,189,98,.42);background:rgba(243,189,98,.12);color:#ffd991;box-shadow:none}button.warning:hover{background:rgba(243,189,98,.2)}button.danger{border-color:rgba(255,120,134,.43);background:rgba(255,120,134,.1);color:#ffb4bc;box-shadow:none}button.danger:hover{background:rgba(255,120,134,.18)}button.ghost{border-color:#374e68;background:transparent;box-shadow:none;color:#dce8f8}button:disabled{transform:none;box-shadow:none}.compact-button{min-height:38px}
.service-details{gap:10px;margin-top:14px}.compact-detail{padding:14px}.resource-grid{gap:10px}.resource{min-height:87px;padding:14px}.resource strong{font-size:20px}.certificate-resource{min-height:auto}.rank-list{gap:8px}.rank-row{min-height:44px;padding:9px 11px}.rank-number{font-size:12px}.rank-main{justify-content:space-between}.rank-traffic{font-variant-numeric:tabular-nums}.notice{padding:13px 15px;border-color:#385473;border-radius:12px;background:#10243a;color:#d2def0}.notice strong{color:#fff}code{padding:2px 5px;border:1px solid #314962;border-radius:5px;background:#0a1727;color:#dbe8fb}
.login{position:relative;width:min(480px,100%);margin:clamp(64px,12vh,120px) auto;padding:34px;border-color:#304967;background:linear-gradient(155deg,#13243a,#0c1929);box-shadow:0 30px 90px rgba(0,0,0,.38)}.login::before{content:"H2";display:grid;place-items:center;width:54px;height:54px;margin-bottom:24px;border:1px solid #47688d;border-radius:15px;background:linear-gradient(145deg,#173756,#10233a);color:#82dfc0;font-size:20px;font-weight:900;letter-spacing:-.04em}.login h1{margin-bottom:8px;font-size:29px}.login>.muted{margin-bottom:26px}.login-form{gap:16px}.login-actions{margin-top:4px}.login-actions button{width:100%;min-height:46px}.login-support{display:flex;align-items:flex-start;gap:9px;margin:22px 0 0;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.login-support::before{content:"";flex:0 0 auto;width:8px;height:8px;margin-top:5px;border-radius:50%;background:var(--success);box-shadow:0 0 0 4px rgba(86,210,159,.1)}
.login::before{display:none}.login-brand{display:flex;align-items:center;gap:16px;margin-bottom:18px}.login-brand img{flex:0 0 auto;width:54px;height:54px;border-radius:15px;box-shadow:0 12px 28px rgba(0,0,0,.28)}.login-brand .state-kicker{margin-bottom:7px}.login-brand h1{margin:0}.dialog-close{width:auto;min-width:64px;height:40px;padding:0 14px;border-radius:999px;font-size:13px;line-height:1;white-space:nowrap}
.state-page{width:min(620px,100%);margin:clamp(72px,15vh,150px) auto;padding:34px}.state-kicker{display:inline-flex;margin-bottom:18px;padding:6px 10px;border:1px solid #3d5672;border-radius:999px;background:#12253d;color:#bfd0e8;font-size:11px;font-weight:800;letter-spacing:.08em}.state-page h1{margin-bottom:12px}.state-page .error{padding:14px 16px;border:1px solid rgba(255,120,134,.3);border-radius:12px;background:rgba(255,120,134,.08);color:#ffc2c8}.state-actions{display:flex;gap:10px;margin:24px 0 0}.copy-grid{padding:14px;border:1px solid #2b4058;border-radius:13px;background:#101f31}.copy-grid textarea{background:#0b1828}

label{font-size:13px}input,textarea,select{min-height:44px;padding:10px 12px;border-color:#3a506a;border-radius:10px;background:#0e1c2d}textarea{line-height:1.55}input:hover,textarea:hover,select:hover{border-color:#506987}input:focus,textarea:focus,select:focus,button:focus-visible,.button:focus-visible,summary:focus-visible{outline:3px solid rgba(120,166,255,.34);outline-offset:2px;border-color:#79a7ff}
.user-tools{align-items:flex-end;padding:14px;border:1px solid #273c54;border-radius:14px;background:#0d1b2c}.user-filters{gap:10px}.search-status{padding-bottom:10px;font-size:12px}.table-wrap{border:1px solid #273b52;border-radius:14px}.user-table table{min-width:1080px}.user-table th{top:0;padding:12px 11px;background:#101f31;color:#b3c0d1;font-size:11px;letter-spacing:.03em}.user-table td{padding:12px 11px}.user-table tbody tr:last-child td{border-bottom:0}.user-table tbody tr:hover{background:#122338}.status{display:inline-flex;align-items:center;min-height:28px;padding:4px 9px;border-radius:999px;font-size:12px}.status.enabled{background:rgba(86,210,159,.1)}.status.disabled{background:rgba(255,120,134,.1)}progress{overflow:hidden;height:7px;border:0;border-radius:999px;background:#22364d}progress::-webkit-progress-bar{background:#22364d;border-radius:999px}progress::-webkit-progress-value{border-radius:999px;background:linear-gradient(90deg,var(--teal),var(--accent))}.traffic-label{margin-top:6px;font-size:11px}
.actions{align-items:center;min-width:360px;gap:6px}.actions button{min-height:36px;padding:7px 10px;font-size:12px}
.migration-dialog{border-color:#3b5674;border-radius:20px;background:#0d1a2b;box-shadow:0 28px 100px rgba(0,0,0,.62)}.migration-dialog::backdrop{background:rgba(2,8,17,.82)}.dialog-shell{padding:0 24px 24px}.dialog-head{position:sticky;z-index:4;top:0;margin:0 -24px 20px;padding:22px 24px 17px;border-color:#263b52;background:rgba(13,26,43,.96);backdrop-filter:blur(14px)}.dialog-head h2{font-size:23px}.dialog-close{width:44px;height:44px;border-color:#405a77;background:#17293f;box-shadow:none}.operation-guide{padding:17px;border-color:#38526f;border-radius:14px;background:#102138}.danger-guide{border-color:#73505a;background:#201c2b}.numbered-steps{gap:13px}.numbered-steps li{grid-template-columns:36px minmax(0,1fr)}.numbered-steps li::before{width:32px;height:32px;background:#79a7ff;color:#06101e}.numbered-steps span{font-size:12px}.node-enrollment-grid{padding:16px;border:1px solid #2c435c;border-radius:14px;background:#0b1929}.node-row{padding:14px;border-radius:13px}.migration-grid{gap:14px}.migration-grid .detail{padding:20px}.credential-actions{gap:10px}.toast{padding:13px 16px;border-color:#3e5a7a;border-radius:12px;background:#142b49;box-shadow:var(--shadow)}.toast:not(.error){color:#dff8ed}.toast.error{background:#321c28}
@media(max-width:1050px){main{width:min(920px,calc(100% - 32px))}.dashboard-trio{grid-template-columns:1fr;gap:14px}.topbar h1{max-width:none}.user-tools{align-items:stretch}.actions{min-width:330px}}
@media(max-width:640px){body::before{display:none}main{width:calc(100% - 24px);margin:12px auto 32px}.topbar{min-height:0;padding:18px;border-radius:18px}.topbar h1{font-size:24px;line-height:1.2}.pill{justify-content:center;min-height:44px;text-align:center}.metrics{gap:10px}.metric{min-height:112px;padding:16px}.metric>strong{font-size:24px}.card{padding:18px;border-radius:16px}.machine-stats{padding:18px}.machine-card{padding:14px}.section-head{gap:10px}.button-row{gap:8px}.button-row button,.button-row .button{min-height:44px}.user-tools{padding:12px}.user-table{border:0}.user-table tr{grid-template-columns:minmax(0,1fr) auto auto;padding:10px;gap:6px 8px;border-radius:12px}.user-table td:nth-child(1){grid-column:1}.user-table td:nth-child(2){grid-column:2}.user-table td:nth-child(3){grid-column:3;white-space:nowrap}.user-table td:nth-child(4){grid-column:1;font-size:10px;color:var(--muted);white-space:nowrap}.user-table td:nth-child(5){grid-column:2/4}.user-table td:nth-child(6){grid-column:1/-1;margin-top:0;padding-top:8px;border-top:1px solid #2b4058}.user-table td:nth-child(3)::before,.user-table td:nth-child(4)::before{display:inline;margin-right:4px;color:var(--muted);font-size:9px;font-weight:700;letter-spacing:.02em}.user-table td:nth-child(3)::before{content:"在线"}.user-table td:nth-child(4)::before{content:"上下行"}.user-table progress{height:6px}.user-table .traffic-label{margin-top:3px;font-size:10px}.user-table .actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));min-width:0;gap:4px}.user-table .actions form,.user-table .actions button{width:100%}.user-table .actions button{min-height:32px;padding:5px 4px;font-size:11px}.login{margin:36px auto;padding:26px}.state-page{margin:44px auto;padding:24px}.state-actions{display:grid}.dialog-shell{padding:0 18px 18px}.dialog-head{top:0;margin:0 -18px 18px;padding:18px}.dialog-head h2{font-size:21px}.operation-guides{gap:10px}.operation-guide{padding:14px}.node-enrollment-grid{padding:13px}.migration-grid .detail{padding:16px}.toast{left:12px;right:12px;bottom:12px;max-width:none}}
@media(max-width:640px){.machine-budget-row{padding:16px 0}.machine-budget-head>div>strong{font-size:16px}.machine-online{font-size:12px}.machine-online strong{font-size:17px}.machine-budget-usage{align-items:flex-start;flex-direction:column;gap:3px}.machine-budget-usage>strong{font-size:15px}.machine-budget-meta{align-items:stretch;flex-direction:column;gap:10px}.machine-budget-edit,.legacy-cleanup-form,.legacy-cleanup-form button{width:100%}.budget-dialog-form{grid-template-columns:1fr}}
@media(max-width:360px){main{width:calc(100% - 16px)}.metrics{grid-template-columns:1fr}.section-actions{grid-template-columns:1fr}.section-actions form{grid-column:auto}.user-filters{grid-template-columns:1fr}.user-filters .user-search{grid-column:auto}.login{padding:22px}}
@media(prefers-contrast:more){:root{--line:#536b87;--line-strong:#7890aa;--muted:#c3cddd}.card,.metric,.machine-card,.machine-budget-row,.resource,.detail,input,textarea,select{border-width:2px}}
@media(forced-colors:active){button,.button,.status,.service-badge,.eyebrow,.pill{forced-color-adjust:auto}.metric::before{display:none}}
@media(max-width:640px){.user-table table,.user-table tbody{display:block;width:100%;min-width:0}}
@media(max-width:640px){.user-table td{padding:0}.user-table td:nth-child(6){padding-top:8px}}
@media(max-width:640px){.version-row{display:grid;grid-template-columns:1fr;align-items:start;gap:8px}.version-actions{grid-template-columns:1fr;width:100%}.version-actions form,.version-actions button{width:100%}}
.service-badge.pending{border-color:rgba(243,189,98,.34);background:rgba(243,189,98,.12);color:var(--warning)}.service-badge.failed{border-color:rgba(255,120,134,.34);background:rgba(255,120,134,.13);color:#ffabb4}.user-table td:first-child strong,.node-row strong{overflow-wrap:anywhere;word-break:break-word}.topbar .pill,.topbar .topbar-action,.topbar .logout-form button{border:1px solid #3a506b;border-radius:10px;background:#17273b;box-shadow:none}
@media(max-width:640px){.user-table td:first-child strong{display:block;max-width:100%}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important}.migration-dialog::backdrop,.dialog-head{backdrop-filter:none}}
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
class UnconfirmedRequestError extends Error {
  constructor() {
    super('连接中断或响应异常，操作结果尚未确认；请刷新页面核对状态后再操作');
  }
}
async function postJson(url, options, timeoutMs = 45000) {
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
document.addEventListener('click', function(event) {
  const opener = event.target.closest('[data-dialog-open]');
  if (opener) {
    if (opener.dataset.dialogOpen === 'edit-user-dialog') syncEditUserForm();
    const dialog = document.getElementById(opener.dataset.dialogOpen);
    if (dialog && typeof dialog.showModal === 'function') {
      dialogOpeners.set(dialog, opener);
      dialog.showModal();
    }
    return;
  }
  const closer = event.target.closest('[data-dialog-close]');
  if (closer) {
    const dialog = closer.closest('dialog');
    if (dialog) dialog.close();
  }
});
document.addEventListener('keydown', function(event) {
  if (event.key !== 'Escape') return;
  const dialogs = Array.from(document.querySelectorAll('dialog[open]'));
  const dialog = dialogs[dialogs.length - 1];
  if (!dialog) return;
  event.preventDefault();
  dialog.close();
});
document.addEventListener('close', function(event) {
  const dialog = event.target;
  if (!(dialog instanceof HTMLDialogElement)) return;
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
    if (!payload || typeof payload.deploymentCommand !== 'string' || !payload.deploymentCommand.startsWith('(\\nset -euo pipefail')) {
      throw new Error('部署代码响应无效');
    }
    code.value = payload.deploymentCommand;
    expiry.textContent = '对接码将在 ' + new Date(Number(payload.expiresAt) * 1000).toLocaleTimeString() + ' 过期，且只能使用一次。';
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
    button.textContent = '一键对接';
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
  if (refresh) window.location.href = '/';
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
const editUserSelect = document.querySelector('[data-edit-user-select]');
if (editUserSelect) {
  editUserSelect.addEventListener('change', syncEditUserForm);
  syncEditUserForm();
}
const filterForm = document.querySelector('[data-user-filters]');
if (filterForm) {
  const userSearch = filterForm.querySelector('[data-user-search]');
  const clearFilters = filterForm.querySelector('[data-clear-user-filters]');
  let searchTimer = 0;
  function applyServerFilters() {
    const params = new URLSearchParams(new FormData(filterForm));
    const url = new URL(window.location.href);
    ['q', 'status', 'online', 'udp443'].forEach(function(name) {
      const value = params.get(name);
      if (value) url.searchParams.set(name, value);
      else url.searchParams.delete(name);
    });
    url.searchParams.delete('page');
    window.location.assign(url.pathname + url.search);
  }
  filterForm.addEventListener('submit', function(event) {
    event.preventDefault();
    applyServerFilters();
  });
  filterForm.addEventListener('change', applyServerFilters);
  userSearch.addEventListener('input', function() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(applyServerFilters, 350);
  });
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
if (document.querySelector('[data-live-online-total]')) {
  window.setTimeout(refreshOnlineStatus, 2000);
}
"""
