import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';
import 'subscription_screen.dart';
import 'subscription_nodes_screen.dart';

class SubscriptionsScreen extends ConsumerStatefulWidget {
  const SubscriptionsScreen({super.key});
  @override
  ConsumerState<SubscriptionsScreen> createState() => _SubscriptionsState();
}

class _SubscriptionsState extends ConsumerState<SubscriptionsScreen> {
  List<Map<String, dynamic>> _items = [];
  String? _error;
  String _query = '';
  final Set<int> _expanded = {};
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/subscriptions');
      if (mounted) {
        setState(
          () => _items = (data['items'] as List? ?? [])
              .map((item) => Map<String, dynamic>.from(item as Map))
              .toList(),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _delete(Map<String, dynamic> item) async {
    if (_loading) return;
    setState(() => _loading = true);
    try {
      final approved = await showDialog<bool>(
        context: context,
        builder: (context) => GlassDialog(
          title: const Text('删除订阅'),
          content: Text('删除 ${item['user_name']} 的订阅后，原订阅链接失效。确认继续？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('删除'),
            ),
          ],
        ),
      );
      if (!mounted || approved != true) return;
      await ref.read(appControllerProvider.notifier).postJson(
        '/api/v1/mobile/subscriptions/${item['id']}/delete',
        {'confirm': item['id'].toString()},
      );
      if (mounted) setState(() => _items.remove(item));
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _editor(bool external) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => SubscriptionNodesScreen(external: external),
    ),
  );
  @override
  Widget build(BuildContext context) {
    final items = _items
        .where(
          (item) => '${item['user_name']} ${item['user_id']}'.contains(_query),
        )
        .toList();
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(10, 0, 10, 20),
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            const PanelHeading('订阅管理'),
            SegmentedButton<int>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: 0, label: Text('用户订阅')),
                ButtonSegment(value: 1, label: Text('默认节点')),
                ButtonSegment(value: 2, label: Text('外部节点')),
              ],
              selected: const {0},
              onSelectionChanged: (v) {
                if (v.single != 0) _editor(v.single == 2);
              },
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _entry(
                    '管理默认节点',
                    '配置并维护默认节点',
                    Icons.layers_outlined,
                    () => _editor(false),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _entry(
                    '导入外部节点',
                    '从订阅导入节点',
                    Icons.cloud_upload_outlined,
                    () => _editor(true),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            GlassCard(
              child: Row(
                children: [
                  Expanded(
                    child: TextButton.icon(
                      onPressed: () => _editor(true),
                      icon: const Icon(Icons.visibility_outlined),
                      label: const Text('预览'),
                    ),
                  ),
                  const SizedBox(height: 30, child: VerticalDivider(width: 1)),
                  Expanded(
                    child: TextButton.icon(
                      onPressed: () => _editor(true),
                      icon: const Icon(
                        Icons.send_outlined,
                        color: Color(0xFFBC9BEF),
                      ),
                      label: const Text(
                        '发布',
                        style: TextStyle(color: Color(0xFFBC9BEF)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            GlassCard(
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '用户订阅',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                        ),
                        Text(
                          '共 ${_items.length} 个用户',
                          style: const TextStyle(fontSize: 12),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    GlassCard(
                      child: TextField(
                        decoration: const InputDecoration(
                          prefixIcon: Icon(Icons.search),
                          hintText: '搜索用户',
                        ),
                        onChanged: (v) => setState(() => _query = v.trim()),
                      ),
                    ),
                    const SizedBox(height: 14),
                    if (_loading) const LinearProgressIndicator(),
                    if (_error != null) RefreshWarning(message: _error!),
                    if (!_loading && items.isEmpty)
                      const Padding(
                        padding: EdgeInsets.all(20),
                        child: Text('暂无匹配的订阅'),
                      ),
                    for (final item in items)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: _card(item),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _entry(
    String title,
    String subtitle,
    IconData icon,
    VoidCallback action,
  ) => GlassCard(
    child: InkWell(
      onTap: action,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary, size: 24),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(subtitle, style: const TextStyle(fontSize: 10)),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
  Widget _card(Map<String, dynamic> item) {
    final id = int.tryParse(item['user_id'].toString());
    final expanded = _expanded.contains(id);
    final enabled = item['enabled'] == true || item['enabled'] == 1;
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: id == null
                ? null
                : () => setState(() {
                    if (expanded) {
                      _expanded.remove(id);
                    } else {
                      _expanded.add(id);
                    }
                  }),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              child: Row(
                children: [
                  const Icon(Icons.person_outline, size: 22),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      item['user_name']?.toString() ?? '用户 $id',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  Text(
                    enabled ? '已启用' : '已停用',
                    style: TextStyle(
                      fontSize: 12,
                      color: enabled
                          ? const Color(0xFF00E1DF)
                          : const Color(0xFFBC9BEF),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Icon(
                    expanded ? Icons.expand_less : Icons.expand_more,
                    size: 20,
                  ),
                ],
              ),
            ),
          ),
          if (expanded && id != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 0, 10, 8),
              child: SubscriptionScreen(
                userId: id,
                name: item['user_name']?.toString() ?? '用户 $id',
                embedded: true,
                onDelete: () => _delete(item),
              ),
            ),
        ],
      ),
    );
  }
}
