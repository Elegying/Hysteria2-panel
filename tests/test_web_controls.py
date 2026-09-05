"""Exercise dashboard submit behavior using the installed JavaScript runtime."""

import shutil
import subprocess
import unittest

from hy2panel.web_assets import PAGE_SCRIPT


class WebControlsTests(unittest.TestCase):
    def run_script(self, script):
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            input=PAGE_SCRIPT, text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to execute dashboard JavaScript")
    def test_inline_requests_bound_waiting_without_claiming_mutation_failure(self):
        self.run_script(r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const timers = new Map();
let timerId = 0;
let mode = 'connect';
let login = '';
const context = {
  document: {
    addEventListener() {}, querySelectorAll() { return []; },
    getElementById() { return null; }, querySelector() { return null; }
  },
  window: {
    setTimeout(callback, delay) { timers.set(++timerId, {callback, delay}); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    location: {assign(url) { login = url; }}
  },
  AbortController, URLSearchParams,
  FormData: class { *[Symbol.iterator]() { yield ['csrf', 'fixture']; } },
  async fetch(url, options) {
    assert.equal(url, '/users');
    assert.equal(options.method, 'POST');
    if (mode === 'network') throw new TypeError('Failed to fetch');
    const waitForAbort = () => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('aborted')));
    });
    if (mode === 'connect') return waitForAbort();
    return {
      ok: !['rejected', 'expired'].includes(mode),
      status: mode === 'expired' ? 401 : mode === 'rejected' ? 400 : 201,
      headers: {get() { return 'application/json'; }},
      async json() {
        if (mode === 'body') return waitForAbort();
        if (mode === 'malformed') throw new SyntaxError('truncated response');
        return mode === 'rejected' ? {error: '设备数无效'} : {name: 'created-user'};
      }
    };
  }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(0, 'utf8'), context);
(async () => {
  for (mode of ['connect', 'body']) {
    const pending = context.submitInlineForm({action: '/users'});
    pending.catch(() => {});
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    const abort = [...timers.values()].find(timer => timer.delay === 45000);
    assert.ok(abort, 'inline buttons need a bounded response wait');
    abort.callback();
    await assert.rejects(pending, /结果尚未确认/);
    assert.equal(timers.size, 0);
  }
  for (mode of ['network', 'malformed']) {
    await assert.rejects(context.submitInlineForm({action: '/users'}), /结果尚未确认/);
    assert.equal(timers.size, 0);
  }
  mode = 'rejected';
  await assert.rejects(context.submitInlineForm({action: '/users'}), /设备数无效/);
  mode = 'expired';
  await assert.rejects(context.submitInlineForm({action: '/users'}), /登录/);
  assert.equal(login, '/login');
  mode = 'success';
  assert.equal((await context.submitInlineForm({action: '/users'})).name, 'created-user');
  assert.equal(timers.size, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
""")

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to execute dashboard JavaScript")
    def test_update_poll_timeout_is_bounded_and_retry_cannot_reapply(self):
        self.run_script(r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const timers = new Map();
const status = {dataset: {state: 'idle'}, textContent: ''};
const button = {disabled: true, textContent: '正在更新…', type: 'submit'};
let timerId = 0;
let reloads = 0;
let login = '';
let requests = 0;
let mode = 'hang';
const context = {
  document: {
    addEventListener() {}, querySelectorAll() { return []; }, getElementById() { return null; },
    querySelector(selector) { return selector === '[data-update-status]' ? status : null; }
  },
  window: {
    setTimeout(callback, delay) { timers.set(++timerId, {callback, delay}); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    location: {reload() { reloads++; }, assign(url) { login = url; }}
  },
  AbortController,
  fetch(url, options) {
    requests++;
    assert.equal(url, '/updates/status');
    assert.equal(options.method, undefined, 'status retry must remain read-only');
    if (mode === 'expired') return Promise.resolve({status: 401, ok: false});
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('timeout'))));
  }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(0, 'utf8'), context);
(async () => {
  const pending = context.pollUpdateStatus(button, 0);
  assert.equal(requests, 1);
  const abort = [...timers.values()].find(timer => timer.delay === 8000);
  assert.ok(abort, 'a hung status request needs its own deadline');
  abort.callback();
  await pending;
  assert.equal(timers.size, 0);
  assert.equal(status.dataset.state, 'unknown', 'a missing response is not proof of failure');
  assert.equal(button.disabled, false);
  assert.equal(button.type, 'button');
  button.onclick();
  assert.equal(reloads, 1);
  assert.equal(requests, 1, 'refresh must not requeue an update');
  mode = 'expired';
  await context.pollUpdateStatus(button, Date.now() + 180000);
  assert.equal(login, '/login');
  assert.equal(timers.size, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
""")

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to execute dashboard JavaScript")
    def test_restore_blocks_duplicate_submissions_but_allows_failed_upload_retry(self):
        script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const handlers = [];
const button = {disabled: false, textContent: '上传并恢复'};
const file = {files: []};
const status = {textContent: ''};
const form = {
  dataset: {csrf: 'fixture-csrf'},
  closest(selector) { return selector === '[data-restore-form]' ? this : null; },
  querySelector(selector) {
    return {'button[type="submit"]': button, 'input[type="file"]': file,
            '[data-restore-status]': status}[selector];
  }
};
let accept = false;
let requests = 0;
let respond;
vm.runInNewContext(fs.readFileSync(0, 'utf8'), {
  document: {
    addEventListener(type, handler) { if (type === 'submit') handlers.push(handler); },
    querySelector() { return null; }, querySelectorAll() { return []; },
    getElementById() { return null; }
  },
  window: {confirm() { return accept; }, setTimeout() {}, clearTimeout() {}},
  AbortController,
  fetch() { requests++; return new Promise(resolve => { respond = resolve; }); }
});
function submit() {
  const event = {target: form, defaultPrevented: false,
                 preventDefault() { this.defaultPrevented = true; }};
  return Promise.all(handlers.map(handler => handler(event)));
}
function response(ok, payload) {
  return {ok, status: ok ? 202 : 400,
          headers: {get() { return 'application/json'; }},
          async json() { return payload; }};
}
(async () => {
  await submit();
  assert.match(status.textContent, /请选择/);
  file.files = [{}];
  await submit();
  assert.equal(requests, 0, 'cancel must not upload');
  assert.equal(button.disabled, false);
  accept = true;
  let pending = submit();
  assert.equal(button.disabled, true, 'upload must disable the submit button');
  await submit();
  assert.equal(requests, 1, 'an in-flight upload must not be duplicated');
  respond(response(false, {error: '备份校验失败'}));
  await pending;
  assert.equal(button.disabled, false, 'a failed upload must allow retry');
  assert.equal(button.textContent, '上传并恢复');
  assert.equal(status.textContent, '备份校验失败');
  pending = submit();
  respond(response(true, {status: 'queued'}));
  await pending;
  assert.equal(requests, 2);
  assert.equal(button.disabled, true);
  assert.equal(button.textContent, '恢复已启动');
  const queuedMessage = status.textContent;
  assert.match(queuedMessage, /恢复任务已启动/);
  await submit();
  assert.equal(requests, 2, 'a queued restore must not be submitted again');
  assert.equal(status.textContent, queuedMessage);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        self.run_script(script)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to execute dashboard JavaScript")
    def test_update_and_restore_do_not_resubmit_after_losing_the_response(self):
        self.run_script(r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const script = fs.readFileSync(0, 'utf8');
(async () => {
  for (const kind of ['update', 'restore']) {
    const handlers = [];
    const timers = new Map();
    const button = {disabled: false, type: 'submit', textContent: 'submit'};
    const status = {dataset: {state: 'idle'}, textContent: ''};
    let timerId = 0;
    let posts = 0;
    let gets = 0;
    let reloads = 0;
    const form = {
      action: '/updates/apply', dataset: {csrf: 'fixture'},
      closest(selector) { return selector === '[data-' + kind + '-form]' ? this : null; },
      querySelector(selector) {
        if (selector === 'button[type="submit"]') return button.type === 'submit' ? button : null;
        if (selector === 'input[type="file"]') return {files: [{}]};
        if (selector === '[data-restore-status]') return status;
      }
    };
    const context = {
      document: {
        addEventListener(type, handler) { if (type === 'submit') handlers.push(handler); },
        querySelectorAll() { return []; }, getElementById() { return null; },
        querySelector(selector) { return selector === '[data-update-status]' ? status : null; }
      },
      window: {
        confirm() { return true; },
        setTimeout(callback, delay) { timers.set(++timerId, {callback, delay}); return timerId; },
        clearTimeout(id) { timers.delete(id); },
        location: {reload() { reloads++; }}
      },
      AbortController, URLSearchParams,
      FormData: class { *[Symbol.iterator]() { yield ['csrf', 'fixture']; } },
      async fetch(url, options) {
        if (options.method === 'POST') {
          posts++;
          return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('lost response'))));
        }
        gets++;
        assert.equal(url, '/updates/status');
        return {ok: true, status: 200, async json() { return {state: 'queued'}; }};
      }
    };
    vm.createContext(context);
    vm.runInContext(script, context);
    function submit() {
      const event = {target: form, defaultPrevented: false,
        preventDefault() { this.defaultPrevented = true; }};
      return Promise.all(handlers.map(handler => handler(event)));
    }
    const pending = submit();
    assert.equal(posts, 1);
    const delay = kind === 'restore' ? 16 * 60 * 1000 : 45000;
    const abort = [...timers.values()].find(timer => timer.delay === delay);
    assert.ok(abort, 'restore must allow its full maintenance window and still have a deadline');
    abort.callback();
    await pending;
    await new Promise(setImmediate);
    if (kind === 'update') {
      assert.equal(gets, 1, 'an uncertain update must recover via status reads');
      assert.equal(status.dataset.state, 'queued', JSON.stringify(status));
      assert.equal(button.disabled, true);
    } else {
      assert.equal(button.type, 'button');
      assert.equal(button.disabled, false);
      assert.equal(button.textContent, '刷新状态');
      assert.match(status.textContent, /结果尚未确认/);
      button.onclick();
      assert.equal(reloads, 1);
    }
    await submit();
    assert.equal(posts, 1, 'lost responses must not enable a duplicate maintenance action');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


if __name__ == "__main__":
    unittest.main()
