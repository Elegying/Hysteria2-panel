import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';
import '../core/glass.dart';

class DomainUsageScreen extends ConsumerStatefulWidget {
  const DomainUsageScreen.global({super.key}) : userId = null, userName = null;

  const DomainUsageScreen.user({
    required int this.userId,
    required String this.userName,
    super.key,
  });

  final int? userId;
  final String? userName;

  @override
  ConsumerState<DomainUsageScreen> createState() => _DomainUsageScreenState();
}

class _DomainUsageScreenState extends ConsumerState<DomainUsageScreen> {
  Map<String, dynamic>? _data;
  String? _error;
  int _loadGeneration = 0;

  Future<void> _load() async {
    if (!mounted) return;
    final generation = ++_loadGeneration;
    setState(() => _error = null);
    try {
      final path = widget.userId == null
          ? '/api/v1/mobile/domain-usage'
          : '/api/v1/mobile/users/${widget.userId}/domain-usage';
      final data = await ref.read(appControllerProvider.notifier).getJson(path);
      if (mounted && generation == _loadGeneration) {
        setState(() => _data = data);
      }
    } on ApiException catch (error) {
      if (mounted && generation == _loadGeneration) {
        setState(() => _error = error.message);
      }
    }
  }

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  @override
  Widget build(BuildContext context) {
    final items = (_data?['items'] as List? ?? const [])
        .map((value) => Map<String, dynamic>.from(value as Map))
        .toList();
    final title = widget.userName == null
        ? '全局流量详情'
        : '${widget.userName} · 流量详情';
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverAppBar(
                pinned: false,
                title: Text(title),
                actions: [
                  IconButton(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh_rounded),
                    tooltip: '刷新',
                  ),
                ],
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                sliver: SliverList.list(
                  children: [
                    GlassCard(
                      child: Padding(
                        padding: const EdgeInsets.all(18),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '本月访问域名 TOP10',
                              style: Theme.of(context).textTheme.titleLarge
                                  ?.copyWith(fontWeight: FontWeight.w800),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '${_data?['month'] ?? '本月'} · 按上传与下载流量合计排序',
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                            const SizedBox(height: 5),
                            Text(
                              '仅统计 Hysteria 能识别的 TCP 目标域名，不保存完整访问日志、URL 或 Cookie。',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (_data == null && _error == null)
                      const Padding(
                        padding: EdgeInsets.all(32),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    else if (_error != null)
                      GlassCard(
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            children: [
                              Text(_error!, textAlign: TextAlign.center),
                              const SizedBox(height: 12),
                              FilledButton.icon(
                                onPressed: _load,
                                icon: const Icon(Icons.refresh_rounded),
                                label: const Text('重试'),
                              ),
                            ],
                          ),
                        ),
                      )
                    else if (items.isEmpty)
                      const GlassCard(
                        child: Padding(
                          padding: EdgeInsets.all(24),
                          child: Center(child: Text('本月暂时没有可识别的域名流量')),
                        ),
                      )
                    else
                      ...items.indexed.map((entry) {
                        final index = entry.$1;
                        final item = entry.$2;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: GlassCard(
                            child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 18,
                                vertical: 8,
                              ),
                              leading: CircleAvatar(
                                child: Text('${index + 1}'),
                              ),
                              title: Text(
                                item['domain']?.toString() ?? '-',
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              subtitle: Text(
                                '上传 ${formatBytes(item['txBytes'])} · 下载 ${formatBytes(item['rxBytes'])}',
                              ),
                              trailing: Text(
                                formatBytes(item['usedBytes']),
                                style: const TextStyle(
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                            ),
                          ),
                        );
                      }),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
