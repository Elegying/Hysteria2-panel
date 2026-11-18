import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';

class SubscriptionNodesScreen extends ConsumerStatefulWidget {
  const SubscriptionNodesScreen({
    super.key,
    this.external = false,
    this.userId,
    this.userName,
    this.subscriptionId,
  });
  final bool external;
  final int? userId;
  final String? userName;
  final int? subscriptionId;
  @override
  ConsumerState<SubscriptionNodesScreen> createState() => _EditorState();
}

class _EditorState extends ConsumerState<SubscriptionNodesScreen> {
  List<Map<String, dynamic>> _nodes = [];
  int _revision = 0;
  late final int _accountRevision;
  bool _busy = true;
  bool _loaded = false;
  bool _editing = false;
  bool _dirty = false;
  bool _leaving = false;
  String? _error;
  String get _path => widget.subscriptionId != null
      ? '/api/v1/mobile/subscriptions/${widget.subscriptionId}/nodes'
      : '/api/v1/mobile/subscriptions/${widget.external ? 'external' : 'defaults'}';
  @override
  void initState() {
    super.initState();
    _accountRevision = ref.read(appControllerProvider).contextRevision;
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _loaded = false;
    });
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson(
            widget.userId == null
                ? _path
                : '/api/v1/mobile/users/${widget.userId}/subscription',
          );
      if (!mounted) return;
      if (widget.userName != null &&
          ((data['name'] != null && data['name'] != widget.userName) ||
              data['subscriptionId'] != widget.subscriptionId)) {
        throw const ApiException('订阅归属已改变，请返回用户列表重新打开');
      }
      setState(() {
        _nodes = (data['nodes'] as List? ?? []).map((n) {
          final row = Map<String, dynamic>.from(n as Map);
          return <String, dynamic>{
            'label': row['label'] ?? '',
            'enabled':
                row['enabled'] == null ||
                row['enabled'] == true ||
                row['enabled'] == 1,
            if (widget.external) ...{
              'id': row['id'],
              'uri': '',
            } else ...{
              'host': row['host'] ?? '',
              'port': row['port'] ?? 443,
              'pin_sha256': row['pin_sha256'] ?? '',
              if (row['node_id'] != null) 'node_id': row['node_id'],
            },
          };
        }).toList();
        _revision = (data['revision'] as num?)?.toInt() ?? 0;
        _error = null;
        _loaded = true;
        _dirty = false;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _edit([int? index]) async {
    if (_busy || !_loaded || _editing) return;
    _editing = true;
    final row = index == null
        ? <String, dynamic>{'enabled': true}
        : _nodes[index];
    final label = TextEditingController(text: row['label']?.toString());
    final host = TextEditingController(text: row['host']?.toString());
    final port = TextEditingController(text: '${row['port'] ?? 443}');
    final pin = TextEditingController(text: row['pin_sha256']?.toString());
    final uri = TextEditingController(text: row['uri']?.toString());
    final form = GlobalKey<FormState>();
    final result = await showGlassFormDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => GlassDialog(
        title: Text(index == null ? '添加节点' : '编辑节点'),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
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
                  if (widget.external)
                    TextFormField(
                      controller: uri,
                      maxLines: 3,
                      decoration: InputDecoration(
                        labelText: row['id'] == null ? '节点链接' : '新链接（留空保留凭据）',
                      ),
                      validator: (v) => row['id'] == null && v!.trim().isEmpty
                          ? '请输入节点链接'
                          : null,
                    )
                  else ...[
                    TextFormField(
                      controller: host,
                      decoration: const InputDecoration(labelText: '地址'),
                      validator: (v) => v!.trim().isEmpty ? '请输入地址' : null,
                    ),
                    TextFormField(
                      controller: port,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: '端口'),
                      validator: (v) {
                        final n = int.tryParse(v ?? '');
                        return n == null || n < 1 || n > 65535
                            ? '端口应为 1–65535'
                            : null;
                      },
                    ),
                    TextFormField(
                      controller: pin,
                      decoration: const InputDecoration(
                        labelText: '证书 SHA-256',
                      ),
                      validator: (v) =>
                          RegExp(r'^[0-9a-fA-F]{64}$')
                              .hasMatch((v ?? '').trim().replaceAll(':', ''))
                          ? null
                          : '请输入 64 位证书指纹（可含冒号）',
                    ),
                  ],
                ],
              ),
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
              if (!form.currentState!.validate()) return;
              Navigator.pop(context, <String, dynamic>{
                ...row,
                'label': label.text.trim(),
                if (widget.external)
                  'uri': uri.text.trim()
                else ...{
                  'host': host.text.trim(),
                  'port': int.parse(port.text),
                  'pin_sha256': pin.text.trim(),
                },
              });
            },
            child: const Text('保存草稿'),
          ),
        ],
      ),
    );
    for (final c in [label, host, port, pin, uri]) {
      c.dispose();
    }
    _editing = false;
    if (result != null && mounted) {
      setState(() {
        _dirty = true;
        if (index == null) {
          _nodes.add(result);
        } else {
          _nodes[index] = result;
        }
      });
    }
  }

  Future<void> _save({bool preview = false}) async {
    if (_busy || !_loaded || _editing) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (ref.read(appControllerProvider).contextRevision != _accountRevision) {
        throw const ApiException('登录状态已改变，请重新打开订阅');
      }
      await ref.read(appControllerProvider.notifier).postJson(
        '$_path${preview ? '/preview' : ''}',
        {
          'nodes': _nodes,
          if (widget.external) 'revision': _revision,
          if (widget.userName != null) 'expectedName': widget.userName,
        },
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(preview ? '预览校验通过，可以发布' : '节点配置已保存，请客户端刷新订阅')),
      );
      if (!preview) await _load();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool> _discard() async =>
      await showDialog<bool>(
        context: context,
        builder: (ctx) => GlassDialog(
          title: const Text('放弃未发布的修改？'),
          content: const Text('当前草稿尚未保存，离开后修改将丢失。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('继续编辑'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('放弃修改'),
            ),
          ],
        ),
      ) ==
      true;
  Future<void> _leave() async {
    if (_leaving || _busy) return;
    _leaving = true;
    try {
      if (await _discard() && mounted) {
        setState(() => _dirty = false);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) Navigator.pop(context);
        });
      }
    } finally {
      _leaving = false;
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_dirty && !_busy,
    onPopInvokedWithResult: (didPop, result) {
      if (!didPop && _dirty) _leave();
    },
    child: Scaffold(
      appBar: AppBar(
        title: Text(
          widget.external
              ? '外部节点'
              : widget.userId != null
              ? '用户订阅节点'
              : '默认节点',
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_busy) const LinearProgressIndicator(),
          if (_error != null) RefreshWarning(message: _error!),
          Wrap(
            spacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: _busy || !_loaded ? null : () => _edit(),
                icon: const Icon(Icons.add),
                label: const Text('添加节点'),
              ),
              if (widget.external)
                OutlinedButton(
                  onPressed: _busy || !_loaded
                      ? null
                      : () => _save(preview: true),
                  child: const Text('预览'),
                ),
              FilledButton(
                onPressed: _busy || !_loaded ? null : _save,
                child: Text(
                  widget.external
                      ? '发布'
                      : widget.userId != null
                      ? '保存用户节点'
                      : '保存默认节点',
                ),
              ),
              TextButton(
                onPressed: _busy
                    ? null
                    : () async {
                        if (!_dirty || await _discard()) {
                          if (mounted) _load();
                        }
                      },
                child: const Text('重新加载'),
              ),
            ],
          ),
          for (var i = 0; i < _nodes.length; i++)
            GlassCard(
              child: Column(
                children: [
                  SwitchListTile(
                    title: Text(_nodes[i]['label'].toString()),
                    value: _nodes[i]['enabled'] == true,
                    onChanged: _busy || !_loaded
                        ? null
                        : (v) => setState(() {
                            _nodes[i]['enabled'] = v;
                            _dirty = true;
                          }),
                  ),
                  OverflowBar(
                    children: [
                      TextButton(
                        onPressed: _busy ? null : () => _edit(i),
                        child: const Text('编辑'),
                      ),
                      TextButton(
                        onPressed: _busy
                            ? null
                            : () => setState(() {
                                _nodes.removeAt(i);
                                _dirty = true;
                              }),
                        child: const Text('移除草稿节点'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}
