"""Typed administrative operations shared with the mobile HTTP transport.

This module never creates browser sessions, follows redirects or accepts arbitrary
commands. The transport supplies existing validators and maintenance callbacks.
"""
import ipaddress
import json
import re
import socket
import time

from .budgets import gib_input_to_bytes
from .mobile_api import json_boolean, json_integer


class AdminApiError(ValueError):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


EXACT_ROUTES = {
    ('GET', '/api/v1/mobile/settings'): 'settings',
    ('GET', '/api/v1/mobile/budgets'): 'budgets',
    ('GET', '/api/v1/mobile/subscriptions'): 'subscriptions',
    ('GET', '/api/v1/mobile/subscriptions/defaults'): 'subscription-defaults',
    ('GET', '/api/v1/mobile/subscriptions/external'): 'external-nodes',
    ('POST', '/api/v1/mobile/subscriptions/defaults'): 'set-subscription-defaults',
    ('POST', '/api/v1/mobile/subscriptions/external'): 'set-external-nodes',
    ('POST', '/api/v1/mobile/subscriptions/external/preview'): 'preview-external-nodes',
    ('POST', '/api/v1/mobile/users/reset-traffic'): 'reset-all-traffic',
    ('POST', '/api/v1/mobile/usage-origins/legacy-unattributed/delete'): 'delete-unattributed',
    ('POST', '/api/v1/mobile/updates/check'): 'check-update',
    ('POST', '/api/v1/mobile/updates/apply'): 'apply-update',
    ('POST', '/api/v1/mobile/backup'): 'backup',
    ('POST', '/api/v1/mobile/restore'): 'restore',
}
PATTERN_ROUTES = (
    ('POST', 'origin-budget', r'/usage-origins/((?:local|node):[0-9a-f]{32})/budget'),
    ('POST', 'diagnose', r'/usage-origins/((?:local|node):[0-9a-f]{32})/diagnostics'),
    ('POST', 'remote-operation', r'/nodes/([0-9a-f]{32})/operations/(restart|reboot)'),
    ('POST', 'line-config', r'/nodes/([0-9a-f]{32})/line-config'),
    ('POST', 'verify-node', r'/nodes/([0-9a-f]{32})/verify'),
    ('POST', 'revoke-node', r'/nodes/([0-9a-f]{32})/revoke'),
    ('POST', 'node-protocol', r'/nodes/([0-9a-f]{32})/protocol/(enable|disable)'),
    ('POST', 'node-lifecycle', r'/nodes/([0-9a-f]{32})/lifecycle/(drain|stop|emergency-stop|resume|archive|budget-dns-removed)'),
    ('POST', 'node-bootstrap', r'/nodes/([0-9a-f]{32})/data-plane/bootstrap'),
    ('POST', 'node-canary', r'/nodes/([0-9a-f]{32})/data-plane/canary/pass'),
    ('POST', 'node-dns', r'/nodes/([0-9a-f]{32})/data-plane/dns/(admit|remove)'),
    ('POST', 'port-hopping', r'/port-hopping/(enable|disable)'),
    ('POST', 'egress', r'/egress/(web|full)'),
    ('POST', 'subscription-nodes', r'/subscriptions/([1-9][0-9]{0,18})/nodes'),
    ('POST', 'subscription-action', r'/subscriptions/([1-9][0-9]{0,18})/(enable|disable|delete|regenerate)'),
)
COMPILED_ROUTES = tuple((method, name, re.compile('/api/v1/mobile' + pattern))
                        for method, name, pattern in PATTERN_ROUTES)


def match_admin_route(method, path):
    route = EXACT_ROUTES.get((method, path))
    if route:
        return route, ()
    for expected, name, pattern in COMPILED_ROUTES:
        match = pattern.fullmatch(path) if method == expected else None
        if match:
            if name.startswith('subscription-') and int(match[1]) > 2**63 - 1:
                return None, ()
            return name, match.groups()
    return None, ()


def fields(payload, allowed=(), required=()):
    if not isinstance(payload, dict) or set(payload) - set(allowed) or set(required) - set(payload):
        raise AdminApiError(400, 'REQUEST_INVALID', '请求字段缺失或不受支持')


def confirmation(payload, expected):
    if payload.get('confirm') != expected:
        raise AdminApiError(400, 'CONFIRMATION_REQUIRED', '请确认本次操作及目标')


class AdminApi:
    def __init__(self, application, actor, audit, validators, prepare_maintenance, kick, defaults):
        self.app = application
        self.db = application.database
        self.actor, self.audit_actor = actor[:64], actor
        self.audit, self.validators = audit, validators
        self.prepare_maintenance, self.kick, self.defaults = prepare_maintenance, kick, defaults

    def record(self, action, target):
        self.audit(self.audit_actor, action, str(target))

    def active_origins(self):
        return [self.app.usage_manager.local_origin_id] + [
            'node:' + node['node_id'] for node in self.db.list_nodes()
            if node['status'] != 'revoked'
        ]

    def read(self, route):
        if route == 'settings':
            offsite = 'not_configured'
            path = self.app.offsite_backup_status_path
            try:
                if path.is_file() and not path.is_symlink():
                    with path.open('rb') as source:
                        raw = source.read(4097)
                    if len(raw) > 4096:
                        raise ValueError('oversized status')
                    offsite = json.loads(raw).get('state')
                    if offsite not in {'not_configured', 'success', 'failed'}:
                        raise ValueError('unknown status')
            except (OSError, ValueError, TypeError, AttributeError):
                offsite = 'unavailable'
            return {
                'certificate': self.app.health_monitor.certificate_status(),
                'egress': self.app.egress_policy_controller.inspect(),
                'hopping': self.app.port_hopping_controller.status(),
                'update': self.app.update_result,
                'offsiteBackup': {'state': offsite},
                'backupAvailable': self.app.backup_manager is not None,
                'restoreAvailable': self.app.backup_manager is not None,
            }
        if route == 'budgets':
            return {'items': self.db.list_origin_budgets(self.active_origins(), int(time.time()))}
        if route == 'subscription-defaults':
            return {'nodes': self.defaults(), 'hopping': self.app.port_hopping_controller.status()}
        if route == 'external-nodes':
            state = self.db.get_external_nodes()
            return {'revision': state['revision'], 'nodes': self.public_external(state['nodes'])}
        if route == 'subscriptions':
            # Credentials are returned only by the existing per-user subscription endpoint.
            allowed = {'id', 'user_id', 'user_name', 'enabled', 'user_type', 'created_at'}
            return {'items': [{key: value for key, value in row.items() if key in allowed}
                              for row in self.db.list_subscriptions()]}
        raise AdminApiError(404, 'NOT_FOUND', '接口不存在')

    def public_external(self, nodes):
        result = []
        for index, node in enumerate(nodes):
            parsed = self.validators['parse_external'](node['uri'])
            result.append({'id': index, 'label': node['label'], 'enabled': node['enabled'],
                           **{key: parsed[key] for key in ('host', 'port', 'insecure')}})
        return result

    def write(self, route, parameters, payload):
        # Keep the same user/maintenance serialization as browser mutations.
        with self.app.user_action_lock:
            result = self._write(route, parameters, payload)
        return result

    def _write(self, route, parameters, payload):
        if route in {'set-subscription-defaults', 'subscription-nodes'}:
            fields(payload, ('nodes',), ('nodes',))
            if not isinstance(payload['nodes'], list):
                raise AdminApiError(400, 'NODES_INVALID', '节点必须是列表')
            for node in payload['nodes']:
                fields(node, ('label', 'host', 'port', 'pin_sha256', 'enabled', 'node_id'),
                       ('label', 'host', 'port', 'pin_sha256', 'enabled'))
                json_integer(node['port'])
                json_boolean(node['enabled'])
                if any(not isinstance(node[key], str) for key in ('label', 'host', 'pin_sha256')):
                    raise AdminApiError(400, 'NODES_INVALID', '节点文本字段无效')
                if node.get('node_id') is not None and (not isinstance(node['node_id'], str) or not re.fullmatch('[0-9a-f]{32}', node['node_id'])):
                    raise AdminApiError(400, 'NODES_INVALID', '节点标识无效')
            nodes = self.validators['subscription_nodes'](payload['nodes'], allow_empty=route == 'subscription-nodes')
            if route == 'set-subscription-defaults':
                self.db.set_subscription_defaults(nodes)
            else:
                subscription_id = int(parameters[0])
                if self.db.get_subscription(subscription_id=subscription_id) is None:
                    raise AdminApiError(404, 'SUBSCRIPTION_NOT_FOUND', '订阅不存在')
                self.db.set_subscription_nodes(subscription_id, nodes)
            self.record('subscription_nodes_updated', parameters[0] if parameters else 'defaults')
            return 200, {'saved': True}
        if route in {'set-external-nodes', 'preview-external-nodes'}:
            return self.external_nodes(route, payload)
        if route == 'subscription-action':
            fields(payload, ('confirm',), ('confirm',))
            confirmation(payload, parameters[0])
            subscription_id, action = int(parameters[0]), parameters[1]
            if self.db.get_subscription(subscription_id=subscription_id) is None:
                raise AdminApiError(404, 'SUBSCRIPTION_NOT_FOUND', '订阅不存在')
            if action == 'delete':
                self.db.delete_subscription(subscription_id)
            elif action == 'regenerate':
                rotated = self.db.regenerate_subscription_token(subscription_id)
                self.kick(rotated['user_name'])
            else:
                self.db.set_subscription_enabled(subscription_id, action == 'enable')
            self.record('subscription_' + action, subscription_id)
            return 200, {'saved': True}
        if route == 'origin-budget':
            return self.budget(parameters[0], payload)
        if route == 'diagnose':
            fields(payload)
            if parameters[0] not in self.active_origins():
                raise AdminApiError(404, 'NODE_NOT_FOUND', '节点不存在')
            accepted, message = self.app.line_monitor.request(parameters[0])
            self.record('line_diagnostic_requested', parameters[0])
            return (202 if accepted else 409), {'accepted': accepted, 'message': message}
        if route == 'remote-operation':
            fields(payload, ('confirm',), ('confirm',))
            node_id, action = parameters
            confirmation(payload, node_id)
            sample = self.db.server_monitor.snapshot([node_id]).get(node_id, {})
            if not sample.get('fresh'):
                raise AdminApiError(409, 'NODE_UNAVAILABLE', '节点离线或未上报运维能力')
            try:
                command = self.db.queue_node_command(
                    node_id, 'RESTART_SERVICE' if action == 'restart' else 'REBOOT_SERVER',
                    {'expiresAt': int(time.time()) + 120}, int(time.time()))
            except ValueError:
                raise AdminApiError(409, 'STATE_CONFLICT', '节点状态不允许此操作，请刷新后重试') from None
            self.record('server_operation_queued', node_id + ':' + action)
            return 202, {'commandId': command['commandId'], 'accepted': True}
        if route == 'line-config':
            fields(payload, ('label', 'host', 'port'), ('label', 'host', 'port'))
            if not all(isinstance(payload[key], str) for key in ('label', 'host')):
                raise AdminApiError(400, 'REQUEST_INVALID', '节点名称和地址必须为文本')
            self.db.update_premium_node_profile(parameters[0], payload['label'], payload['host'], json_integer(payload['port']))
            self.record('premium_node_profile_updated', parameters[0])
            return 200, {'saved': True}
        if route == 'port-hopping':
            fields(payload, ('confirm',), ('confirm',))
            confirmation(payload, 'LOCAL_NODE')
            result = self.app.port_hopping_controller.set_enabled(parameters[0] == 'enable')
            self.record('port_hopping_changed', result['enabled'])
            return 200, result
        if route == 'egress':
            fields(payload, ('confirm',), ('confirm',))
            confirmation(payload, 'LOCAL_NODE')
            self.prepare_maintenance()
            state = self.app.usage_manager.run_after_collect(lambda: self.app.egress_policy_controller.switch(parameters[0]))
            self.record('egress_policy_changed', parameters[0])
            return 200, {'state': state}
        if route == 'reset-all-traffic':
            fields(payload, ('confirm', 'group'), ('confirm', 'group'))
            confirmation(payload, 'RESET_TRAFFIC')
            group = payload['group']
            if group not in {'standard', 'premium', 'all'}:
                raise AdminApiError(400, 'GROUP_INVALID', '用户分组无效')
            self.app.usage_manager.reset_all(group=None if group == 'all' else group)
            self.record('all_proxy_traffic_reset', group)
            return 200, {'reset': True}
        if route == 'delete-unattributed':
            fields(payload, ('confirm',), ('confirm',))
            confirmation(payload, 'DELETE_UNATTRIBUTED')
            result = self.db.delete_unattributed_history()
            self.record('unattributed_history_deleted', 'legacy')
            return 200, {'deleted': result}
        if route in {'check-update', 'apply-update'}:
            return self.update(route, payload)
        return self.node_action(route, parameters, payload)

    def external_nodes(self, route, payload):
        fields(payload, ('revision', 'nodes'), ('revision', 'nodes'))
        revision = json_integer(payload['revision'])
        state = self.db.get_external_nodes()
        if revision != state['revision']:
            raise AdminApiError(409, 'CONFIG_CHANGED', '配置已变更，请重新加载')
        if not isinstance(payload['nodes'], list) or len(payload['nodes']) > 32:
            raise AdminApiError(400, 'NODES_INVALID', '最多支持 32 个节点')
        resolved = []
        for node in payload['nodes']:
            fields(node, ('id', 'label', 'enabled', 'uri'), ('label', 'enabled'))
            node = dict(node)
            json_boolean(node['enabled'])
            if not node.get('uri'):
                index = json_integer(node.get('id'))
                if not 0 <= index < len(state['nodes']):
                    raise AdminApiError(400, 'NODES_INVALID', '缺少节点链接')
                node['uri'] = state['nodes'][index]['uri']
            resolved.append(node)
        normalized = self.validators['external_nodes'](resolved)
        if route == 'preview-external-nodes':
            return 200, {'nodes': self.public_external(normalized)}
        revision = self.db.publish_external_nodes(normalized, revision)
        self.record('external_nodes_published', len(normalized))
        return 200, {'revision': revision, 'saved': True}

    def budget(self, origin_id, payload):
        fields(payload, ('limitGiB', 'warningPercent', 'usedGiB', 'resetDay'), ('limitGiB', 'warningPercent'))
        if origin_id not in self.active_origins():
            raise AdminApiError(404, 'NODE_NOT_FOUND', '节点不存在')
        limit = json_integer(payload['limitGiB'])
        warning = json_integer(payload['warningPercent'])
        if not 0 <= limit <= (2**63 - 1) // 1024**3:
            raise AdminApiError(400, 'BUDGET_INVALID', '预算超出允许范围')
        if ('usedGiB' in payload) != ('resetDay' in payload):
            raise AdminApiError(400, 'BUDGET_INVALID', '已用流量和重置日必须同时填写')
        options = {}
        if 'usedGiB' in payload:
            if not isinstance(payload['usedGiB'], str):
                raise AdminApiError(400, 'BUDGET_INVALID', 'usedGiB 必须是十进制字符串')
            options = {'manual_used_bytes': gib_input_to_bytes(payload['usedGiB']),
                       'reset_day': json_integer(payload['resetDay'])}
        self.db.set_origin_budget(origin_id, limit * 1024**3, warning, self.actor, int(time.time()), **options)
        self.record('node_traffic_budget_updated', origin_id)
        return 200, {'saved': True}

    def update(self, route, payload):
        fields(payload, () if route == 'check-update' else ('confirm', 'target'))
        with self.app.update_lock:
            if route == 'check-update':
                self.app.update_result = self.app.update_checker.check()
                self.record('panel_update_checked', 'panel')
                return 200, self.app.update_result
            confirmation(payload, 'UPDATE_PANEL')
            result = self.app.update_result
            if not result or not result.get('update_available') or payload.get('target') != result.get('latest'):
                raise AdminApiError(409, 'UPDATE_NOT_READY', '请检查更新并确认目标版本')
            if self.db.has_external_subscription_state():
                raise AdminApiError(409, 'EXTERNAL_NODES_PRESENT', '当前外部节点配置不支持在线升级')
            self.app.update_controller.queue(result['latest'])
            self.record('panel_update_queued', result['latest'])
            return 202, self.app.update_controller.status()

    def node_action(self, route, parameters, payload):
        node_id = parameters[0] if parameters else ''
        now = int(time.time())
        fields(payload, ('fingerprint',) if route == 'verify-node' else ('confirm',))
        if route != 'verify-node':
            confirmation(payload, node_id)
        if route == 'verify-node':
            fingerprint = payload.get('fingerprint')
            if not isinstance(fingerprint, str) or not re.fullmatch('[0-9a-f]{64}', fingerprint):
                raise AdminApiError(400, 'FINGERPRINT_INVALID', '节点指纹无效')
            if not self.db.verify_node(node_id, fingerprint, actor=self.actor, verified_at=now):
                raise AdminApiError(409, 'NODE_CHANGED', '节点状态或指纹不匹配')
        elif route == 'revoke-node':
            if not self.db.revoke_node(node_id, revoked_at=now):
                raise AdminApiError(404, 'NODE_NOT_FOUND', '节点不存在')
        elif route == 'node-protocol':
            state = 'protocol_ready' if parameters[1] == 'enable' else 'standby'
            if not self.db.set_node_policy_state(node_id, state, actor=self.actor, changed_at=now):
                raise AdminApiError(409, 'NODE_UNAVAILABLE', '节点必须已验证且在线')
        elif route == 'node-bootstrap':
            if not self.app.secure_cookies or self.app.data_plane_bootstrap_service is None:
                raise AdminApiError(409, 'HTTPS_REQUIRED', '请先启用面板 HTTPS')
            result = self.app.data_plane_bootstrap_service.issue(node_id, actor=self.actor)
            self.record('node_data_plane_bootstrap_issued', node_id)
            return 201, result
        elif route == 'node-canary':
            self.db.mark_node_direct_canary_passed(node_id, self.actor, now)
        elif route == 'node-dns':
            method = self.db.mark_node_dns_admitted if parameters[1] == 'admit' else self.db.remove_node_dns_admission
            method(node_id, self.actor, now)
        elif route == 'node-lifecycle':
            self.lifecycle(node_id, parameters[1], now)
        else:
            raise AdminApiError(404, 'NOT_FOUND', '接口不存在')
        self.record(route.replace('-', '_'), node_id)
        return 200, {'accepted': True}

    def lifecycle(self, node_id, action, now):
        if action == 'budget-dns-removed':
            self.db.confirm_node_budget_dns_removed(node_id, self.actor, now)
        elif action == 'drain':
            self.db.begin_node_drain(node_id, self.actor, now)
        elif action == 'resume':
            self.db.request_node_resume(node_id, self.actor, now)
        elif action == 'archive':
            self.db.archive_stopped_node(node_id, self.actor, now)
        else:
            emergency = action == 'emergency-stop'
            removed = False
            if not emergency:
                node = next((n for n in self.db.list_nodes() if n['node_id'] == node_id), None)
                if node is None:
                    raise AdminApiError(404, 'NODE_NOT_FOUND', '节点不存在')
                expected = str(ipaddress.ip_address(node.get('expected_ip') or node.get('observed_ip')))
                addresses = {str(ipaddress.ip_address(info[4][0])) for info in socket.getaddrinfo(
                    node.get('subscription_host') or self.app.public_host, None, type=socket.SOCK_STREAM)}
                removed = expected not in addresses
            self.db.request_node_stop(node_id, self.actor, now, dns_removed_verified=removed, emergency=emergency)
