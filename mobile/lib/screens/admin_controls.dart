import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';
import 'backup_controls.dart';

class AdminControls extends ConsumerStatefulWidget {
  const AdminControls({
    super.key,
    this.nodeId,
    this.resources,
    this.protocolOnly = false,
    this.onDisconnect,
    this.nodeProfile,
  });
  final String? nodeId;
  final Map<String, dynamic>? nodeProfile;
  final Map? resources;
  final bool protocolOnly;
  final VoidCallback? onDisconnect;
  @override
  ConsumerState<AdminControls> createState() => _ControlsState();
}

class _ControlsState extends ConsumerState<AdminControls> {
  bool _busy = false;
  bool _editing = false;
  bool _statusBusy = false;
  Timer? _timer;
  bool _executing = false;
  String? _message;
  String? _statusError;
  Map<String, dynamic>? _status;
  @override
  void initState() {
    super.initState();
    if (widget.nodeId != null) return;
    Future.microtask(_refreshStatus);
    _timer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (mounted &&
          TickerMode.valuesOf(context).enabled &&
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
        _refreshStatus();
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refreshStatus() async {
    if (_statusBusy) return;
    _statusBusy = true;
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/settings');
      if (!mounted) return;
      final overview = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/overview');
      data['serviceStatus'] = overview['serviceStatus'];
      data['resources'] = overview['resources'];
      data['panelVersion'] = overview['panelVersion'];
      if (mounted) {
        setState(() {
          _status = data;
          _statusError = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusError = e.toString();
          _status = null;
        });
      }
    } finally {
      _statusBusy = false;
    }
  }

  Future<void> _profile() async {
    if (_busy || _editing) return;
    _editing = true;
    final label = TextEditingController(
      text: widget.nodeProfile?['name']?.toString(),
    );
    final host = TextEditingController(
      text: widget.nodeProfile?['subscriptionHost']?.toString(),
    );
    final port = TextEditingController(
      text: '${widget.nodeProfile?['subscriptionPort'] ?? 443}',
    );
    final form = GlobalKey<FormState>();
    final result = await showGlassFormDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => GlassDialog(
        title: const Text('专线配置'),
        content: SingleChildScrollView(
          child: Form(
            key: form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              spacing: 14,
              children: [
                TextFormField(
                  controller: label,
                  decoration: const InputDecoration(labelText: '名称'),
                  validator: (v) => v!.trim().isEmpty ? '请输入名称' : null,
                ),
                TextFormField(
                  controller: host,
                  decoration: const InputDecoration(labelText: '订阅地址'),
                  validator: (v) => v!.trim().isEmpty ? '请输入地址' : null,
                ),
                TextFormField(
                  controller: port,
                  decoration: const InputDecoration(labelText: '订阅端口'),
                  keyboardType: TextInputType.number,
                  validator: (v) {
                    final n = int.tryParse(v ?? '');
                    return n == null || n < 1 || n > 65535 ? '请输入有效端口' : null;
                  },
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              if (form.currentState!.validate()) {
                Navigator.pop(context, <String, dynamic>{
                  'label': label.text.trim(),
                  'host': host.text.trim(),
                  'port': int.parse(port.text),
                });
              }
            },
            child: const Text('下一步'),
          ),
        ],
      ),
    );
    label.dispose();
    host.dispose();
    port.dispose();
    _editing = false;
    if (mounted && result != null) {
      await _run('保存专线配置', 'nodes/${widget.nodeId}/line-config', result);
    }
  }

  Future<void> _run(
    String title,
    String path,
    Map<String, dynamic> payload,
  ) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => GlassDialog(
          title: Text(title),
          content: const Text('确认对当前目标执行此操作？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('确认'),
            ),
          ],
        ),
      );
      if (!mounted || confirmed != true) return;
      setState(() => _executing = true);
      final result = await ref
          .read(appControllerProvider.notifier)
          .postJson('/api/v1/mobile/$path', payload);
      if (!mounted) return;
      setState(
        () => _message = result['accepted'] == true
            ? '操作已受理，请刷新确认执行结果'
            : result['message']?.toString() ?? '操作完成',
      );
      if (widget.nodeId == null) await _refreshStatus();
      if (path == 'updates/check') {
        setState(
          () => _message = result['update_available'] == true
              ? '发现面板版本 ${result['latest']}'
              : '检查完成，暂无可用更新',
        );
        if (result['update_available'] == true) {
          _busy = false;
          await _run('更新面板至 ${result['latest']}', 'updates/apply', {
            'confirm': 'UPDATE_PANEL',
            'target': result['latest'],
          });
        }
      }
    } catch (e) {
      if (mounted) setState(() => _message = e.toString());
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _executing = false;
        });
      }
    }
  }

  Widget _button(
    String title,
    String path, [
    Map<String, dynamic> payload = const {},
    bool purple = false,
  ]) => OutlinedButton(
    style: OutlinedButton.styleFrom(
      foregroundColor: purple
          ? Theme.of(context).colorScheme.secondary
          : Theme.of(context).colorScheme.primary,
      side: BorderSide(
        color: purple
            ? Theme.of(context).colorScheme.secondary
            : const Color(0xFF2D506A),
      ),
    ),
    onPressed: _busy ? null : () => _run(title, path, payload),
    child: Text(title),
  );
  Future<void> _networkOptions(bool hopping) async {
    final choices = hopping
        ? [
            ('启用端口跳跃', 'port-hopping/enable'),
            ('关闭端口跳跃', 'port-hopping/disable'),
          ]
        : [('网页出站', 'egress/web'), ('全局出站', 'egress/full')];
    final choice = await showGlassModalBottomSheet<int>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                hopping ? '本机端口跳跃' : '出站策略',
                style: Theme.of(ctx).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              for (var i = 0; i < choices.length; i++)
                OutlinedButton(
                  onPressed: () => Navigator.pop(ctx, i),
                  child: Text(choices[i].$1),
                ),
            ],
          ),
        ),
      ),
    );
    if (!mounted || choice == null) return;
    await _run(choices[choice].$1, choices[choice].$2, {
      'confirm': 'LOCAL_NODE',
    });
  }

  Widget _resource(String label, dynamic value) => Expanded(
    child: GlassCard(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.bodySmall),
            Text(
              value is num ? '${value.toStringAsFixed(0)}%' : '—',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 3),
            LinearProgressIndicator(
              value: value is num ? (value / 100).clamp(0, 1).toDouble() : 0,
              minHeight: 3,
            ),
          ],
        ),
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final id = widget.nodeId;
    final local = id == null || id == 'local';
    final premium = widget.nodeProfile?['tier'] == 'premium';
    final resources = widget.resources?['fresh'] == true
        ? widget.resources
        : null;
    final result = <Widget>[];
    if (id != null && widget.protocolOnly) {
      result.add(
        ActionGrid(
          children: [
            _button('启用协议', 'nodes/$id/protocol/enable', {'confirm': id}),
            _button('停用协议', 'nodes/$id/protocol/disable', {'confirm': id}),
          ],
        ),
      );
    } else if (id != null) {
      result.addAll([
        Row(
          children: [
            _resource('CPU', resources?['cpu']),
            const SizedBox(width: 12),
            _resource('内存', resources?['memory']),
            const SizedBox(width: 12),
            _resource('磁盘', resources?['disk']),
          ],
        ),
        const SizedBox(height: 6),
        LayoutBuilder(
          builder: (context, box) {
            final buttons = [
              _button(
                '重启服务',
                local ? 'service/restart' : 'nodes/$id/operations/restart',
                local ? {} : {'confirm': id},
              ),
              _button(
                '重启主机',
                local ? 'system/reboot' : 'nodes/$id/operations/reboot',
                local ? {} : {'confirm': id},
                true,
              ),
              if (!local)
                OutlinedButton(
                  onPressed: _busy ? null : widget.onDisconnect,
                  child: const Text('断开对接'),
                ),
              if (premium)
                OutlinedButton(
                  onPressed: _busy ? null : _profile,
                  child: const Text('专线配置'),
                ),
            ];
            final minWidth = MediaQuery.textScalerOf(context).scale(52) + 26;
            final columns = ((box.maxWidth + 6) / (minWidth + 6)).floor().clamp(
              1,
              buttons.length,
            );
            return OutlinedButtonTheme(
              data: OutlinedButtonThemeData(
                style:
                    (OutlinedButtonTheme.of(context).style ??
                            const ButtonStyle())
                        .copyWith(
                          padding: const WidgetStatePropertyAll(
                            EdgeInsets.symmetric(horizontal: 5, vertical: 4),
                          ),
                          minimumSize: const WidgetStatePropertyAll(
                            Size(0, 38),
                          ),
                        ),
              ),
              child: Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  for (final button in buttons)
                    SizedBox(
                      width: (box.maxWidth - (columns - 1) * 6) / columns,
                      child: button,
                    ),
                ],
              ),
            );
          },
        ),
      ]);
    } else {
      final active = _status?['serviceStatus'] == 'active';
      result.addAll([
        PanelSection(
          '服务与系统',
          child: GlassCard(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Wrap(
                    spacing: 6,
                    runSpacing: 8,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                        width: 95,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Hysteria2',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Text(
                              active ? '● 运行中' : '未运行',
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.primary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      _button(
                        active ? '停止服务' : '启动服务',
                        active ? 'service/stop' : 'service/start',
                        {},
                        true,
                      ),
                      _button('重启服务', 'service/restart'),
                    ],
                  ),
                  const Divider(height: 24, indent: 0, endIndent: 0),
                  const Text(
                    'BBR',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  Text(
                    '${(_status?['resources'] as Map?)?['tcpCongestionControl'] ?? '未知'}',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                  const Divider(height: 24, indent: 0, endIndent: 0),
                  const Text(
                    'TLS 证书',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  Text(
                    certificateLabel((_status?['certificate'] as Map?) ?? {}),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                  const Divider(height: 24, indent: 0, endIndent: 0),
                  _button('重启主机', 'system/reboot', {}, true),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        PanelSection(
          '网络设置',
          child: Column(
            children: [
              GlassCard(
                child: ListTile(
                  title: const Text('本机端口跳跃'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _networkOptions(true),
                ),
              ),
              const SizedBox(height: 8),
              GlassCard(
                child: ListTile(
                  title: const Text('出站策略'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _networkOptions(false),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        const BackupControls(),
        const SizedBox(height: 12),
        PanelSection(
          '面板更新',
          child: Row(
            children: [
              Expanded(
                child: Text(
                  'v${_status?['panelVersion'] ?? '—'}',
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.primary,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              _button('检查面板更新', 'updates/check', {}, true),
            ],
          ),
        ),
      ]);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ...result,
        if (_statusError != null) RefreshWarning(message: _statusError!),
        if (_executing) const LinearProgressIndicator(),
        if (_message != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_message!),
          ),
      ],
    );
  }
}

String certificateLabel(Map certificate) {
  return const {
        'ok': '有效',
        'notice': '有效（半年内到期）',
        'warning': '90 天内到期',
        'critical': '30 天内到期',
        'expired': '已过期',
        'not-yet-valid': '尚未生效',
        'unmonitored': '未配置监测',
        'unknown': '状态未知',
      }[certificate['level']] ??
      certificate['status']?.toString() ??
      '状态未知';
}
