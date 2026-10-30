import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';
import '../core/user_validity.dart';

class SubscriptionScreen extends ConsumerStatefulWidget {
  const SubscriptionScreen({
    required this.userId,
    required this.name,
    super.key,
  });
  final int userId;
  final String name;
  @override
  ConsumerState<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends ConsumerState<SubscriptionScreen> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _busy = false;
  String get _path => '/api/v1/mobile/users/${widget.userId}';
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final controller = ref.read(appControllerProvider.notifier);
      final caps = await controller.getJson('/api/v1/mobile/capabilities');
      if (!mounted) return;
      if (!(caps['features'] as List? ?? []).contains(
        'mobile-subscription-management',
      )) {
        throw const ApiException('当前面板尚不支持 App 订阅管理，请先升级面板');
      }
      final data = await controller.getJson('$_path/subscription');
      if (mounted) setState(() => _data = data);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _act(String action, String title, String message) async {
    if (_busy || _data == null || _error != null) return;
    // Reserve the operation before opening confirmation; rapid taps cannot stack it.
    setState(() => _busy = true);
    final snapshot = Map<String, dynamic>.from(_data!);
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => GlassDialog(
          title: Text(title),
          content: Text(message),
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
      final result = await ref.read(appControllerProvider.notifier).postJson(
        '$_path/subscription-$action',
        {
          'generation': snapshot['generation'],
          'revision': snapshot['revision'],
        },
      );
      if (mounted) {
        setState(() {
          _data = result;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = '${e.message}；请刷新核对后再操作');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _copy(String url) async {
    try {
      await Clipboard.setData(ClipboardData(text: url));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('订阅链接已复制')));
      }
    } on PlatformException {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('复制失败，请长按链接手动复制')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final disabled = _busy || _error != null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('订阅管理'),
        actions: [
          IconButton(
            onPressed: _busy ? null : _load,
            icon: const Icon(Icons.refresh),
            tooltip: '刷新',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Text(widget.name, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          if (_busy && _data == null) const LinearProgressIndicator(),
          if (_busy && _data != null) const Text('正在处理，请稍候…'),
          if (_error != null) ...[
            RefreshWarning(message: _error!),
            TextButton(
              onPressed: _busy ? null : _load,
              child: const Text('重新加载'),
            ),
          ],
          if (data != null && data['exists'] != true)
            FilledButton(
              onPressed: disabled
                  ? null
                  : () => _act('create', '创建订阅', '为此用户创建固定订阅链接，不修改节点密码。'),
              child: const Text('创建订阅'),
            ),
          if (data != null && data['exists'] == true) ...[
            GlassCard(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data['enabled'] == true ? '订阅已启用' : '订阅已停用',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      data['userType'] == 1
                          ? '专线节点 · 已就绪 ${data['premiumReadyCount']} / 4 地区'
                          : data['usesDefaults'] == true
                          ? '跟随普通节点设置'
                          : '独立节点配置',
                    ),
                    Text('账号到期：${validityLabel(data['expiresAt'])}'),
                    const SizedBox(height: 12),
                    const Text('固定订阅链接'),
                    SelectableText(data['url'] as String? ?? '旧版链接无法恢复，请核对后处理'),
                    TextButton.icon(
                      onPressed: !disabled && data['url'] is String
                          ? () => _copy(data['url'] as String)
                          : null,
                      icon: const Icon(Icons.copy),
                      label: const Text('复制订阅链接'),
                    ),
                    const Text('修改节点配置或密码后，用户刷新原订阅即可。无需重置链接。'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: disabled
                  ? null
                  : () => _act(
                      data['enabled'] == true ? 'disable' : 'enable',
                      data['enabled'] == true ? '停用订阅' : '启用订阅',
                      '只控制订阅下载，不改变链接，也不会禁用账号或断开已导入的节点。',
                    ),
              child: Text(data['enabled'] == true ? '停用订阅' : '启用订阅'),
            ),
            if (data['userType'] != 1 && data['usesDefaults'] != true)
              OutlinedButton(
                onPressed: disabled
                    ? null
                    : () => _act(
                        'inherit',
                        '跟随统一节点',
                        '清除独立节点配置，改为跟随普通节点设置。订阅链接保持不变。',
                      ),
                child: const Text('改为跟随统一节点'),
              ),
            const SizedBox(height: 12),
            GlassCard(
              child: ExpansionTile(
                key: PageStorageKey('subscription-danger-${widget.userId}'),
                title: const Text('链接泄露处理'),
                childrenPadding: const EdgeInsets.all(12),
                children: [
                  const Text(
                    '重置会更换订阅链接和该用户节点密码，并断开旧连接。旧链接立即失效，必须重新发给用户。仅在链接泄露时使用。',
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed: disabled
                        ? null
                        : () => _act(
                            'regenerate',
                            '重置订阅链接？',
                            '原订阅链接将失效，节点密码也会同步更换并断开旧连接。必须重新分享新链接。确定继续？',
                          ),
                    child: const Text('重置订阅链接'),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
