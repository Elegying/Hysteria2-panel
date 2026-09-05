#!/usr/bin/env python3
"""Exercise real dashboard controls against an isolated local HTTP fixture."""

import base64
import contextlib
import json
import os
import pathlib
import signal
import subprocess  # nosec B404 -- fixed local Chrome executable and argv.
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

from websockets.sync.client import connect

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_panel import PanelHttpTests  # noqa: E402
sys.path.insert(0, str(ROOT / ".github/scripts"))
from browser_smoke import chrome_executable  # noqa: E402

OUT = pathlib.Path(tempfile.mkdtemp(prefix='hy2-browser-controls-'))
OUT.mkdir(mode=0o700, exist_ok=True)


class Browser:
    def __init__(self, url):
        self.context = connect(url, proxy=None, max_size=32 * 1024 * 1024)
        self.ws = self.context.__enter__()
        self.sequence = 0
        self.accept = True
        self.dialogs = []
        self.errors = []

    def call(self, method, params=None):
        self.sequence += 1
        wanted = self.sequence
        self.ws.send(json.dumps({'id': wanted, 'method': method, 'params': params or {}}))
        until = time.monotonic() + 20
        while True:
            message = json.loads(self.ws.recv(timeout=max(.01, until-time.monotonic())))
            if message.get('method') == 'Page.javascriptDialogOpening':
                self.dialogs.append(message['params']['message'])
                self.sequence += 1
                self.ws.send(json.dumps({'id': self.sequence, 'method': 'Page.handleJavaScriptDialog', 'params': {'accept': self.accept}}))
            if message.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(message['params'])
            if message.get('id') == wanted:
                if 'error' in message:
                    raise RuntimeError(str(message['error']))
                return message.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True})
        if 'exceptionDetails' in result:
            raise RuntimeError(str(result['exceptionDetails']))
        return result.get('result', {}).get('value')

    def wait(self, expression, timeout=15):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            try:
                if self.evaluate('Boolean(' + expression + ')'):
                    return
            except RuntimeError:
                pass
            time.sleep(.1)
        raise AssertionError('browser condition failed: '+expression)

    def navigate(self, url):
        tag = str(time.time_ns())
        self.evaluate('window.__auditDocument = '+json.dumps(tag))
        self.call('Page.navigate', {'url': url})
        self.wait('window.__auditDocument !== '+json.dumps(tag)+' && location.href === '+json.dumps(url)+' && document.readyState === "complete"')

    def click(self, selector, navigation=False):
        tag = str(time.time_ns())
        point = self.evaluate('''(() => {
            window.__auditDocument = %s;
            const e = document.querySelector(%s);
            if (!e) throw new Error('control is missing');
            if (e.disabled) throw new Error('control is disabled');
            e.scrollIntoView({behavior:'instant',block:'center', inline:'center'});
            const r = e.getBoundingClientRect();
            if (!r.width || !r.height) throw new Error('control is hidden');
            return {x:r.x+r.width/2, y:r.y+r.height/2};
        })()''' % (json.dumps(tag), json.dumps(selector)))
        self.call('Input.dispatchMouseEvent', {'type':'mousePressed','button':'left','clickCount':1, **point})
        self.call('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','clickCount':1, **point})
        if navigation:
            self.wait('window.__auditDocument !== '+json.dumps(tag)+' && document.readyState === "complete"')

    def value(self, selector, value, event='input'):
        self.evaluate('''(() => {const e=document.querySelector(%s); e.value=%s; e.dispatchEvent(new Event(%s,{bubbles:true}));})()''' % (json.dumps(selector), json.dumps(value), json.dumps(event)))

    def screenshot(self, name):
        data = self.call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
        (OUT/name).write_bytes(base64.b64decode(data['data']))


fixture = PanelHttpTests('runTest')
fixture.setUp()
process = None
browser = None
report = {'passed':[], 'failed':None}


def passed(name):
    report['passed'].append(name)
    print('PASS', name, flush=True)


try:
    fixture.db.create_proxy_user('web-alpha')
    fixture.db.create_proxy_user('web-beta')
    profile = tempfile.TemporaryDirectory(prefix='hy2-web-buttons-chrome-')
    log = (OUT/'chrome.log').open('wb')
    process = subprocess.Popen([  # nosec B603 -- fixed local browser arguments.
        chrome_executable(),
        *(['--no-sandbox'] if os.geteuid() == 0 else []),
        '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
        '--disable-background-networking','--remote-debugging-port=0',
        '--disable-background-timer-throttling','--disable-renderer-backgrounding',
        '--user-data-dir='+profile.name,'--window-size=1380,1000','about:blank',
    ], stdout=log, stderr=log, start_new_session=True)
    port_file = pathlib.Path(profile.name)/'DevToolsActivePort'
    for attempt in range(200):
        if port_file.exists():
            break
        time.sleep(.1)
    port = int(port_file.read_text().splitlines()[0])
    with urllib.request.urlopen('http://127.0.0.1:{}/json/list'.format(port),timeout=5) as response:  # nosec B310 -- local Chrome only.
        tabs = json.load(response)
    browser = Browser(next(tab['webSocketDebuggerUrl'] for tab in tabs if tab['type']=='page'))
    browser.call('Page.enable')
    browser.call('Runtime.enable')
    browser.call('Browser.grantPermissions', {'origin':fixture.base_url,'permissions':['clipboardReadWrite','clipboardSanitizedWrite']})
    browser.call('Browser.setDownloadBehavior', {'behavior':'allow','downloadPath':str(OUT)})
    browser.navigate(fixture.base_url+'/login')
    browser.value('#username','Elegy')
    browser.value('#password','admin-password')
    browser.click('.login-form button',navigation=True)
    browser.wait('document.querySelector("[data-egress-form]")')
    browser.screenshot('dashboard-before.png')
    passed('网页登录与控制台加载')

    browser.accept = False
    browser.click('[data-egress-form] button')
    assert fixture.egress_policy_controller.actions == []
    assert browser.evaluate('document.querySelector("[data-egress-state]").textContent') == 'FULL 已关闭'
    assert browser.evaluate('document.querySelector("[data-egress-form] button").disabled') is False
    passed('FULL 取消确认不提交且按钮可继续使用')
    browser.accept = True
    for target,label in (('full','FULL 已开启'),('web','FULL 已关闭')):
        browser.click('[data-egress-form] button',navigation=True)
        assert fixture.egress_policy_controller.state == target
        assert browser.evaluate('document.querySelector("[data-egress-state]").textContent') == label
    passed('FULL 开启与关闭真实表单往返')
    switch = fixture.egress_policy_controller.switch
    fixture.server.request_deadline = .2
    def slow_switch(policy):
        time.sleep(.6)
        return switch(policy)
    fixture.egress_policy_controller.switch = slow_switch
    browser.click('[data-egress-form] button',navigation=True)
    assert fixture.egress_policy_controller.state == 'full'
    assert browser.evaluate('document.querySelector("[data-egress-state]").textContent') == 'FULL 已开启'
    fixture.server.request_deadline = 30
    fixture.egress_policy_controller.switch = switch
    passed('FULL 慢切换仍返回成功页面')
    def fail_switch(policy):
        raise RuntimeError('simulated service failure')
    fixture.egress_policy_controller.switch = fail_switch
    browser.click('[data-egress-form] button',navigation=True)
    assert browser.evaluate('document.body.innerText.includes("出站策略切换失败")')
    assert fixture.egress_policy_controller.state == 'full'
    fixture.egress_policy_controller.switch = switch
    browser.navigate(fixture.base_url+'/')
    passed('FULL 后端失败显示错误且原状态保留')

    browser.click('[data-dialog-open="create-user-dialog"]')
    browser.wait('document.getElementById("create-user-dialog").open')
    browser.value('#name','web-created')
    browser.click('[data-create-user-form] button')
    browser.wait('document.getElementById("credentials-dialog").open')
    created = fixture.db.get_proxy_user_by_name('web-created')
    assert created is not None
    user_id = created['id']
    browser.click('[data-copy-target="credentials-uri"]')
    browser.wait('document.querySelector("[data-copy-target=credentials-uri]").textContent === "已复制"')
    assert browser.evaluate('navigator.clipboard.readText()').startswith('hysteria2://')
    browser.click('#credentials-dialog [data-dialog-close]',navigation=True)
    passed('添加用户、连接信息、复制与关闭后刷新')

    browser.click('[data-dialog-open="edit-user-dialog"]')
    browser.value('#edit-user-select',str(user_id),'change')
    browser.value('#edit-device-limit','7')
    browser.value('#edit-traffic-limit-gb','20')
    browser.click('[data-edit-user-form] button',navigation=True)
    assert fixture.db.get_proxy_user(user_id)['device_limit'] == 7
    passed('编辑用户选择、保存与列表刷新')

    row = '[data-user-name="web-created"] '
    browser.click(row+'[data-share-form] button')
    browser.wait('document.querySelector('+json.dumps(row+'[data-share-form] button')+').textContent === "已复制"')
    browser.click(row+'[data-qr-form] button')
    browser.wait('document.getElementById("credentials-dialog").open && document.getElementById("credentials-qr").width > 0')
    browser.click('[data-save-qr]')
    for attempt in range(50):
        if (OUT/'hysteria2-node-qr.png').exists():
            break
        time.sleep(.1)
    assert (OUT/'hysteria2-node-qr.png').read_bytes().startswith(b'\x89PNG')
    browser.click('#credentials-dialog [data-dialog-close]')
    passed('行内分享、二维码生成与 PNG 下载')
    for enabled in (False,True):
        browser.click(row+'form[action$="/toggle"] button',navigation=True)
        assert bool(fixture.db.get_proxy_user(user_id)['enabled']) is enabled
    passed('用户禁用与启用')
    token = fixture.db.recover_proxy_token(user_id)
    browser.accept = False
    browser.click(row+'form[action$="/rotate"] button')
    assert fixture.db.recover_proxy_token(user_id) == token
    browser.accept = True
    browser.click(row+'form[action$="/rotate"] button',navigation=True)
    assert fixture.db.recover_proxy_token(user_id) != token
    browser.navigate(fixture.base_url+'/')
    passed('改密取消与确认分支')
    fixture.db.add_traffic({'web-created':{'tx':1000,'rx':2000}})
    browser.click(row+'form[action$="/reset"] button',navigation=True)
    user = fixture.db.get_proxy_user(user_id)
    assert user['tx_bytes']==user['rx_bytes']==0
    passed('单用户重置流量')
    browser.accept = False
    browser.click(row+'form[action$="/delete"] button')
    assert fixture.db.get_proxy_user_by_name('web-created') is not None
    browser.accept = True
    browser.click(row+'form[action$="/delete"] button',navigation=True)
    assert fixture.db.get_proxy_user_by_name('web-created') is None
    passed('删除用户取消与确认分支')

    browser.value('[data-user-search]','web-alpha')
    browser.wait('location.search.includes("q=web-alpha") && document.querySelectorAll("[data-user-name]").length===1')
    browser.click('[data-clear-user-filters]',navigation=True)
    assert browser.evaluate('document.querySelectorAll("[data-user-name]").length')==2
    passed('搜索与清除筛选')
    for action,state in (('stop','inactive'),('start','active'),('restart','active')):
        browser.click('form[action="/service/'+action+'"] button',navigation=True)
        assert fixture.service_controller.state == state
    passed('服务停止、启动与重启按钮')
    browser.click('[data-dialog-open="node-onboarding-dialog"]')
    browser.value('#node-name','web-audit-node')
    browser.value('#node-expected-ip','9.9.9.9')
    browser.click('[data-node-enrollment-form] button')
    browser.wait('document.querySelector("[data-node-enrollment-result]").hidden === false')
    assert browser.evaluate('document.getElementById("node-deployment-code").value').startswith('(\nset -euo pipefail')
    browser.click('#node-onboarding-dialog [data-dialog-close]')
    browser.wait('!document.getElementById("node-onboarding-dialog").open && document.getElementById("node-deployment-code").value === ""')
    passed('对接管理打开、生成代码、关闭清除')
    create = fixture.application.node_enrollment_service.create
    release_enrollment = threading.Event()
    def delayed_enrollment(*args, **kwargs):
        result = create(*args, **kwargs)
        if not release_enrollment.wait(5):
            raise RuntimeError('test did not release enrollment response')
        return result
    fixture.application.node_enrollment_service.create = delayed_enrollment
    browser.click('[data-dialog-open="node-onboarding-dialog"]')
    browser.value('#node-name','web-late-node')
    browser.value('#node-expected-ip','9.9.9.7')
    browser.click('[data-node-enrollment-form] button')
    browser.wait('document.querySelector("[data-node-enrollment-form] button").disabled')
    browser.click('#node-onboarding-dialog [data-dialog-close]')
    browser.wait('!document.getElementById("node-onboarding-dialog").open')
    browser.click('[data-dialog-open="node-onboarding-dialog"]')
    release_enrollment.set()
    browser.wait('!document.querySelector("[data-node-enrollment-form] button").disabled')
    assert browser.evaluate('document.getElementById("node-deployment-code").value') == ''
    assert browser.evaluate('document.querySelector("[data-node-enrollment-result]").hidden')
    fixture.application.node_enrollment_service.create = create
    browser.click('#node-onboarding-dialog [data-dialog-close]')
    browser.wait('!document.getElementById("node-onboarding-dialog").open')
    passed('对接弹窗关闭后重开，不接收上一轮迟到代码')
    service = fixture.application.node_enrollment_service
    issued = service.create('web-ready-node','127.0.0.1',10,'Elegy')
    service.register({
        'enrollmentToken':fixture.enrollment_token(issued['deploymentCommand']),
        'publicKey':base64.b64encode(bytes.fromhex('302a300506032b6570032100')+b'd'*32).decode(),
        'hostname':'web-ready.example.test','platform':'linux','architecture':'amd64','agentVersion':'0.39.5',
    },remote_ip='127.0.0.1')
    now = int(time.time())
    fixture.application.node_heartbeat_service.accept({
        'nodeId':issued['nodeId'],'sentAt':now,
        'nonce':base64.urlsafe_b64encode(b'd'*32).rstrip(b'=').decode(),
        'hostname':'web-ready.example.test','agentVersion':'0.39.5',
        'signature':base64.b64encode(b's'*64).decode(),
    },'127.0.0.1')
    fixture.db.set_node_policy_state(issued['nodeId'],'protocol_ready','Elegy',now)
    with fixture.db._connect() as connection:
        connection.execute("UPDATE nodes SET data_plane_state = 'direct_canary_passed' WHERE node_id = ?",(issued['nodeId'],))
    stale = service.create('web-lost-node','9.9.9.8',10,'Elegy')
    browser.navigate(fixture.base_url+'/')
    browser.click('[data-dialog-open="node-onboarding-dialog"]')
    disconnect_selector = 'form[action="/nodes/'+issued['nodeId']+'/disconnect"] button'
    browser.accept = False
    browser.click(disconnect_selector)
    assert fixture.db.get_node_for_heartbeat(issued['nodeId'])['lifecycle_state'] != 'disconnecting'
    browser.accept = True
    browser.click(disconnect_selector,navigation=True)
    assert fixture.db.get_node_for_heartbeat(issued['nodeId'])['lifecycle_state'] == 'disconnecting'
    browser.click('[data-dialog-open="node-onboarding-dialog"]')
    delete_selector = 'form[action="/nodes/'+stale['nodeId']+'/delete"] button'
    browser.accept = False
    browser.click(delete_selector)
    assert next(n for n in fixture.db.list_nodes() if n['node_id']==stale['nodeId'])['status'] != 'revoked'
    browser.accept = True
    browser.click(delete_selector,navigation=True)
    assert next(n for n in fixture.db.list_nodes() if n['node_id']==stale['nodeId'])['status'] == 'revoked'
    assert browser.evaluate('document.body.innerText.includes("web-lost-node")') is False
    passed('在线节点一键断连、离线删除对接的取消与确认（隔离节点）')
    browser.click('[data-dialog-open="budget-dialog-'+fixture.application.usage_manager.local_origin_id.split(':',1)[1]+'"]')
    for name, value in (('limit_gib','200'),('used_gib','2.5'),('warning_percent','88'),('reset_day','28')):
        browser.value('.budget-dialog[open] [name="'+name+'"]',value)
    browser.click('.budget-dialog[open] button[type="submit"]',navigation=True)
    budget = fixture.db.get_origin_budget(fixture.application.usage_manager.local_origin_id)
    assert budget['limit_bytes'] == 200*1024**3
    assert budget['manual_used_bytes'] == 2.5*1024**3
    assert budget['warning_percent'] == 88 and budget['reset_day'] == 28
    passed('流量预算、基线、告警与重置日保存')
    fixture.db.add_traffic({'web-alpha':{'tx':111,'rx':222},'web-beta':{'tx':333,'rx':444}})
    browser.click('.service-actions a[href="/"]',navigation=True)
    browser.click('a.sort-link[href*="sort=traffic"]',navigation=True)
    assert browser.evaluate('Array.from(document.querySelectorAll("[data-user-name]")).map(e=>e.dataset.userName)') == ['web-beta','web-alpha']
    browser.click('a.sort-link[href*="sort=traffic"]',navigation=True)
    assert browser.evaluate('Array.from(document.querySelectorAll("[data-user-name]")).map(e=>e.dataset.userName)') == ['web-alpha','web-beta']
    browser.value('[data-status-filter]','enabled','change')
    browser.wait('location.search.includes("status=enabled")')
    browser.value('[data-online-filter]','inactive','change')
    browser.wait('location.search.includes("online=inactive")')
    browser.value('[data-udp443-filter]','blocked','change')
    browser.wait('location.search.includes("udp443=blocked")')
    assert browser.evaluate('document.querySelectorAll("[data-user-name]").length') == 2
    browser.click('[data-clear-user-filters]',navigation=True)
    passed('页面刷新、流量升降排序与组合筛选')
    browser.accept = False
    browser.click('form[action="/users/reset-traffic"] button')
    assert fixture.db.get_proxy_user_by_name('web-alpha')['tx_bytes'] == 111
    browser.accept = True
    browser.click('form[action="/users/reset-traffic"] button',navigation=True)
    assert all(fixture.db.get_proxy_user_by_name(name)[key] == 0 for name in ('web-alpha','web-beta') for key in ('tx_bytes','rx_bytes'))
    passed('全部流量重置取消与确认')
    browser.click('form[action="/updates/check"] button',navigation=True)
    browser.wait('document.querySelector("[data-update-form]")')
    browser.accept = False
    browser.click('[data-update-form] button')
    assert fixture.update_controller.queued == 0
    browser.accept = True
    browser.click('[data-update-form] button')
    browser.wait('document.querySelector("[data-update-form] button").textContent === "正在更新…"')
    assert fixture.update_controller.queued == 1
    passed('检查更新、取消与确认排队')
    fixture.application.update_result = None
    browser.navigate(fixture.base_url+'/')
    browser.wait('document.querySelector("[data-update-form] button").disabled')
    assert browser.evaluate('document.querySelector("[data-update-form] button").textContent') == '正在更新…'
    assert fixture.update_controller.queued == 1
    status = fixture.update_controller.status
    status_calls = [0]
    def finish_update_with_error():
        status_calls[0] += 1
        return {**status(), 'state':'failed','message':'测试更新失败'} if status_calls[0] >= 3 else status()
    fixture.update_controller.status = finish_update_with_error
    browser.navigate(fixture.base_url+'/')
    browser.wait('document.querySelector("[data-update-form] button").textContent === "刷新状态"')
    assert status_calls[0] >= 3
    assert not browser.evaluate('document.querySelector("[data-update-form] button").disabled')
    assert fixture.update_controller.queued == 1
    browser.click('[data-update-form] button',navigation=True)
    assert fixture.update_controller.queued == 1
    fixture.update_controller.status = status
    fixture.update_controller.queued = 0
    passed('更新中刷新继续跟踪，失败恢复按钮且不会重复排队')
    browser.navigate(fixture.base_url+'/')
    browser.click('form[action="/updates/check"] button', navigation=True)
    browser.evaluate('''(() => {
      const original = window.fetch;
      window.fetch = async function(url, options) {
        const response = await original(url, options);
        if (url.endsWith('/updates/apply') && options.method === 'POST') {
          window.fetch = original;
          throw new TypeError('simulated response loss after queueing');
        }
        return response;
      };
    })()''')
    browser.click('[data-update-form] button')
    browser.wait('document.querySelector("[data-update-status]").dataset.state === "queued"')
    assert browser.evaluate('document.querySelector("[data-update-form] button").disabled')
    assert fixture.update_controller.queued == 1
    passed('更新已排队但响应丢失时通过只读轮询恢复状态')
    fixture.update_controller.queued = 0
    browser.navigate(fixture.base_url+'/')
    browser.accept = False
    browser.click('form[action="/system/reboot"] button')
    assert fixture.reboot_controller.queued == 0
    browser.accept = True
    browser.click('form[action="/system/reboot"] button',navigation=True)
    assert fixture.reboot_controller.queued == 1
    assert browser.evaluate('document.body.innerText.includes("服务器正在重启")')
    passed('服务器重启取消、排队与反馈页面（隔离控制器）')
    browser.navigate(fixture.base_url+'/')
    browser.call('Emulation.setDeviceMetricsOverride',{'width':375,'height':812,'deviceScaleFactor':1,'mobile':True})
    browser.screenshot('dashboard-mobile.png')
    browser.click('[data-egress-form] button',navigation=True)
    assert fixture.egress_policy_controller.state=='web'
    passed('手机视口 FULL 点击切换')
    browser.call('Emulation.clearDeviceMetricsOverride')
    browser.click('[data-dialog-open="migration-dialog"]')
    before_zip = set(OUT.glob('*.zip'))
    browser.click('form[action="/backup"] button')
    until = time.monotonic()+10
    while time.monotonic()<until and not set(OUT.glob('*.zip'))-before_zip:
        time.sleep(.1)
    backup_path = next(iter(set(OUT.glob('*.zip'))-before_zip))
    with zipfile.ZipFile(backup_path) as package:
        assert package.testzip() is None
        assert 'manifest.json' in package.namelist()
    passed('数据迁移弹窗与完整 ZIP 备份下载')
    document = browser.call('DOM.getDocument')
    file_node = browser.call('DOM.querySelector',{'nodeId':document['root']['nodeId'],'selector':'#restore-file'})
    browser.call('DOM.setFileInputFiles',{'nodeId':file_node['nodeId'],'files':[str(backup_path)]})
    browser.accept = False
    browser.click('[data-restore-form] button')
    assert fixture.restore_controller.queued == 0
    browser.accept = True
    invalid_path = OUT/'invalid-backup.zip'
    invalid_path.write_bytes(b'invalid archive fixture')
    browser.call('DOM.setFileInputFiles',{'nodeId':file_node['nodeId'],'files':[str(invalid_path)]})
    browser.click('[data-restore-form] button')
    browser.wait('!document.querySelector("[data-restore-form] button").disabled && !document.querySelector("[data-restore-status]").textContent.includes("正在校验")')
    assert fixture.restore_controller.queued == 0
    assert not browser.evaluate('document.querySelector("[data-restore-status]").textContent.includes("恢复任务已启动")')
    passed('无效恢复文件显示错误且按钮恢复可用')
    browser.call('DOM.setFileInputFiles',{'nodeId':file_node['nodeId'],'files':[str(backup_path)]})
    browser.click('[data-restore-form] button')
    browser.wait('document.querySelector("[data-restore-status]").textContent.includes("恢复任务已启动")')
    assert fixture.restore_controller.queued == 1
    passed('恢复上传取消、确认与任务排队（隔离控制器）')
    if not browser.evaluate('document.querySelector("[data-restore-form] button").disabled'):
        browser.click('[data-restore-form] button')
        browser.wait('!document.querySelector("[data-restore-status]").textContent.includes("正在校验")')
        status = browser.evaluate('document.querySelector("[data-restore-status]").textContent')
        assert '恢复任务已启动' in status, 'duplicate restore overwrote queued result: '+status
    passed('已排队的恢复任务不能被重复提交覆盖')
    # The isolated restore controller does not consume its staged archive.
    fixture.application.backup_manager.pending_archive.unlink()
    browser.navigate(fixture.base_url+'/')
    browser.click('[data-dialog-open="migration-dialog"]')
    document = browser.call('DOM.getDocument')
    file_node = browser.call('DOM.querySelector', {'nodeId': document['root']['nodeId'], 'selector': '#restore-file'})
    browser.call('DOM.setFileInputFiles', {'nodeId': file_node['nodeId'], 'files': [str(backup_path)]})
    browser.evaluate('''(() => {
      const original = window.fetch;
      window.fetch = async function(url, options) {
        const response = await original(url, options);
        if (url === '/restore' && options.method === 'POST') {
          window.fetch = original;
          throw new TypeError('simulated response loss after queueing');
        }
        return response;
      };
    })()''')
    browser.click('[data-restore-form] button')
    browser.wait('document.querySelector("[data-restore-status]").textContent.includes("结果尚未确认")')
    assert fixture.restore_controller.queued == 2
    assert browser.evaluate('document.querySelector("[data-restore-form] button").type') == 'button'
    browser.click('[data-restore-form] button', navigation=True)
    assert fixture.restore_controller.queued == 2
    passed('恢复已排队但响应丢失时仅刷新状态且不重复上传')
    browser.click('[data-dialog-open="migration-dialog"]')
    browser.click('#migration-dialog [data-dialog-close]')
    browser.click('form[action="/logout"] button',navigation=True)
    assert browser.evaluate('location.pathname') == '/login'
    passed('退出登录')
    assert not browser.errors, browser.errors
    report['result'] = 'passed'
    print('浏览器交互检查通过：{} 组'.format(len(report['passed'])), flush=True)
except Exception as error:
    report['failed'] = str(error)
    report['result'] = 'failed'
    if browser is not None:
        try:
            browser.screenshot('failure.png')
            (OUT/'failure-dom.txt').write_text(str(browser.evaluate('document.body.innerText')))
        except Exception:
            pass
    raise
finally:
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if browser is not None:
        browser.context.__exit__(None,None,None)
    if process is not None:
        # Stop Chrome's helpers before removing the profile they still write.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        log.close()
        profile.cleanup()
    fixture.tearDown()
