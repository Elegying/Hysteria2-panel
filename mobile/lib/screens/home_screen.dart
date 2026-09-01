import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';
import '../core/glass.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen>
    with WidgetsBindingObserver, AutomaticKeepAliveClientMixin {
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = true;
  bool _acting = false;
  Timer? _timer;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(_load);
    _startTimer();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _load();
      _startTimer();
    } else {
      _timer?.cancel();
    }
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _load(silent: true),
    );
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent && mounted) setState(() => _loading = true);
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/overview');
      if (mounted) {
        setState(() {
          _data = data;
          _error = null;
          _loading = false;
        });
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _error = error.message;
          _loading = false;
        });
      }
    }
  }

  Future<void> _serviceAction(String action, String label) async {
    if (action != 'start') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => GlassDialog(
          title: Text('确认$label服务'),
          content: Text(
            action == 'stop'
                ? '停止后，当前所有 Hysteria 连接都会中断。确认停止服务吗？'
                : '重启期间现有连接会短暂中断，流量会先完成结算。确认继续吗？',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: Text(label),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
    }
    setState(() => _acting = true);
    try {
      await ref
          .read(appControllerProvider.notifier)
          .postJson('/api/v1/mobile/service/$action');
      await _load(silent: true);
      if (mounted) _message('$label操作已完成');
    } on ApiException catch (error) {
      if (mounted) _message(error.message, error: true);
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _rebootServer() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => GlassDialog(
        title: const Text('确认重启服务器'),
        content: const Text('重启后面板和所有连接会暂时中断，通常需要 30 至 90 秒恢复。确认继续吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('重启服务器'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _acting = true);
    try {
      await ref
          .read(appControllerProvider.notifier)
          .postJson('/api/v1/mobile/system/reboot');
      if (mounted) _message('服务器重启任务已受理');
    } on ApiException catch (error) {
      if (mounted) _message(error.message, error: true);
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  void _message(String value, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(value),
        backgroundColor: error ? Theme.of(context).colorScheme.error : null,
      ),
    );
  }

  Future<void> _showEnrollment() async {
    final name = TextEditingController();
    final expectedIp = TextEditingController();
    var ttl = 10;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => GlassDialog(
          title: const Text('对接新节点'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('生成短时授权后，在新服务器使用 root 执行完整部署代码。面板不会自动修改 DNS。'),
                const SizedBox(height: 16),
                TextField(
                  controller: name,
                  decoration: const InputDecoration(labelText: '节点名称'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: expectedIp,
                  decoration: const InputDecoration(labelText: '预期公网 IP（可选）'),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int>(
                  initialValue: ttl,
                  dropdownColor: glassMenuColor(context),
                  borderRadius: BorderRadius.circular(16),
                  decoration: const InputDecoration(labelText: '对接码有效期'),
                  items: const [5, 10, 30]
                      .map(
                        (value) => DropdownMenuItem(
                          value: value,
                          child: Text('$value 分钟'),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setDialogState(() => ttl = value ?? 10),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () async {
                if (name.text.trim().isEmpty) return;
                try {
                  final data = await ref
                      .read(appControllerProvider.notifier)
                      .postJson('/api/v1/mobile/node-enrollments', {
                        'name': name.text.trim(),
                        'expectedIp': expectedIp.text.trim(),
                        'ttlMinutes': ttl,
                        'mode': 'join',
                      });
                  if (dialogContext.mounted) Navigator.pop(dialogContext, data);
                } on ApiException catch (error) {
                  if (dialogContext.mounted) {
                    ScaffoldMessenger.of(dialogContext)
                        .showSnackBar(SnackBar(content: Text(error.message)));
                  }
                }
              },
              child: const Text('生成部署代码'),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    expectedIp.dispose();
    if (result == null || !mounted) return;
    final command = result['deploymentCommand']?.toString() ?? '';
    await showDialog<void>(
      context: context,
      builder: (context) => GlassDialog(
        title: const Text('部署代码已生成'),
        content: SizedBox(
          width: 620,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('代码包含短时授权，请只在目标服务器执行；过期后会自动失效。'),
                const SizedBox(height: 12),
                SelectableText(
                  command,
                  style: Theme.of(context).textTheme.bodySmall
                      ?.copyWith(fontFamily: 'monospace'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
          FilledButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: command));
              if (context.mounted) Navigator.pop(context);
              if (mounted) _message('部署代码已复制');
            },
            icon: const Icon(Icons.copy_rounded),
            label: const Text('复制代码'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final data = _data;
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverAppBar(
              pinned: false,
              title: const Text('首页'),
              actions: [
                IconButton(
                  onPressed: _loading ? null : _load,
                  tooltip: '刷新',
                  icon: const Icon(Icons.refresh_rounded),
                ),
              ],
            ),
            if (_loading && data == null)
              const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null && data == null)
              SliverFillRemaining(
                child: _LoadError(message: _error!, onRetry: _load),
              )
            else if (data != null)
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                sliver: SliverList.list(
                  children: [
                    if (_error != null) ...[
                      _InlineWarning(message: '数据刷新失败：$_error'),
                      const SizedBox(height: 12),
                    ],
                    _StatusHeader(data: data),
                    const SizedBox(height: 14),
                    _SummaryGrid(data: data),
                    const SizedBox(height: 14),
                    _SectionCard(
                      title: '服务控制',
                      subtitle: '启动、重启、停止和节点对接集中在这里',
                      child: _ServiceButtons(
                        disabled: _acting,
                        onStart: () => _serviceAction('start', '启动'),
                        onRestart: () => _serviceAction('restart', '重启'),
                        onStop: () => _serviceAction('stop', '停止'),
                        onEnroll: _showEnrollment,
                      ),
                    ),
                    const SizedBox(height: 14),
                    _BudgetsCard(data: data),
                    const SizedBox(height: 14),
                    _ResourcesCard(
                      data: data,
                      disabled: _acting,
                      onReboot: _rebootServer,
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusHeader extends StatelessWidget {
  const _StatusHeader({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final active = data['serviceStatus'] == 'active';
    return GlassCard(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(
              radius: 24,
              backgroundColor: active
                  ? Colors.green.withValues(alpha: .16)
                  : Theme.of(context).colorScheme.errorContainer,
              child: Icon(
                active
                    ? Icons.check_circle_rounded
                    : Icons.error_outline_rounded,
                color: active
                    ? Colors.green
                    : Theme.of(context).colorScheme.error,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    serviceLabel(data['serviceStatus']),
                    style: Theme.of(context).textTheme.titleLarge
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${data['panelName'] ?? 'Hysteria 2'} · 面板 v${data['panelVersion'] ?? '-'}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  Text(
                    '最近刷新 ${formatTimestamp(data['refreshedAt'])}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final users = Map<String, dynamic>.from(data['users'] as Map? ?? {});
    final nodes = Map<String, dynamic>.from(data['nodes'] as Map? ?? {});
    final traffic = Map<String, dynamic>.from(data['traffic'] as Map? ?? {});
    final cards = [
      ('当前用户', '${users['total'] ?? 0}', Icons.people_rounded),
      ('在线设备', '${users['onlineDevices'] ?? 0}', Icons.devices_rounded),
      (
        '在线节点',
        '${nodes['online'] ?? 0} / ${nodes['total'] ?? 0}',
        Icons.dns_rounded,
      ),
      (
        '总流量',
        formatBytes(traffic['totalBytes']),
        Icons.swap_vert_circle_rounded,
      ),
    ];
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 1.65,
        crossAxisSpacing: 10,
        mainAxisSpacing: 10,
      ),
      itemCount: cards.length,
      itemBuilder: (context, index) {
        final item = cards[index];
        return GlassCard(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(item.$3, color: Theme.of(context).colorScheme.primary),
                const Spacer(),
                Text(item.$1, style: Theme.of(context).textTheme.bodySmall),
                Text(
                  item.$2,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.w800),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.subtitle,
    required this.child,
    this.action,
  });
  final String title;
  final String subtitle;
  final Widget child;
  final Widget? action;

  @override
  Widget build(BuildContext context) => GlassCard(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  title,
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.w800),
                ),
              ),
              if (action != null) ...[const SizedBox(width: 10), action!],
            ],
          ),
          const SizedBox(height: 3),
          Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 16),
          child,
        ],
      ),
    ),
  );
}

class _ServiceButtons extends StatelessWidget {
  const _ServiceButtons({
    required this.disabled,
    required this.onStart,
    required this.onRestart,
    required this.onStop,
    required this.onEnroll,
  });
  final bool disabled;
  final VoidCallback onStart;
  final VoidCallback onRestart;
  final VoidCallback onStop;
  final VoidCallback onEnroll;

  @override
  Widget build(BuildContext context) {
    final actions = [
      ('启动', Icons.play_arrow_rounded, onStart, Colors.green),
      ('重启', Icons.restart_alt_rounded, onRestart, Colors.orange),
      ('停止', Icons.stop_rounded, onStop, Colors.red),
      (
        '对接',
        Icons.add_link_rounded,
        onEnroll,
        Theme.of(context).colorScheme.secondary,
      ),
    ];
    return LayoutBuilder(
      builder: (context, constraints) => Wrap(
        spacing: 9,
        runSpacing: 9,
        children: actions
            .map(
              (item) => SizedBox(
                width: (constraints.maxWidth - 9) / 2,
                child: FilledButton.tonalIcon(
                  onPressed: disabled ? null : item.$3,
                  icon: Icon(item.$2, color: item.$4),
                  label: Text(item.$1),
                ),
              ),
            )
            .toList(),
      ),
    );
  }
}

class _BudgetsCard extends StatelessWidget {
  const _BudgetsCard({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final raw = data['trafficBudgets'] as List? ?? const [];
    return _SectionCard(
      title: '节点统计与流量预算',
      subtitle: '按面板节点与远程节点统计当前周期用量',
      child: raw.isEmpty
          ? const Text('暂无节点流量数据')
          : Column(
              children: raw.map((value) {
                final item = Map<String, dynamic>.from(value as Map);
                final budget = item['budget'] is Map
                    ? Map<String, dynamic>.from(item['budget'] as Map)
                    : null;
                final percent = (budget?['percent'] as num?)?.toDouble() ?? 0;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              item['name']?.toString() ?? '未知节点',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          Text('${item['onlineDevices'] ?? '—'} 台在线'),
                        ],
                      ),
                      const SizedBox(height: 7),
                      LinearProgressIndicator(
                        value: (percent / 100).clamp(0, 1),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        budget == null
                            ? '未设置预算 · 已用 ${formatBytes((item['txBytes'] as num? ?? 0) + (item['rxBytes'] as num? ?? 0))}'
                            : '${formatBytes(budget['usedBytes'])} / ${formatBytes(budget['limitBytes'])} · ${percent.toStringAsFixed(1)}%',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
    );
  }
}

class _ResourcesCard extends StatelessWidget {
  const _ResourcesCard({
    required this.data,
    required this.disabled,
    required this.onReboot,
  });
  final Map<String, dynamic> data;
  final bool disabled;
  final VoidCallback onReboot;

  @override
  Widget build(BuildContext context) {
    final resources = Map<String, dynamic>.from(
      data['resources'] as Map? ?? {},
    );
    final rows = [
      (
        'CPU 使用率',
        resources['cpuPercent'] == null ? '不可用' : '${resources['cpuPercent']}%',
      ),
      (
        '内存占用',
        resources['memoryPercent'] == null
            ? '不可用'
            : '${resources['memoryPercent']}%',
      ),
      (
        '磁盘占用',
        resources['diskPercent'] == null
            ? '不可用'
            : '${resources['diskPercent']}%',
      ),
      ('运行时间', resources['uptime']?.toString() ?? '不可用'),
      ('拥塞控制', resources['tcpCongestionControl']?.toString() ?? '不可用'),
      ('默认队列', resources['defaultQdisc']?.toString() ?? '不可用'),
    ];
    return _SectionCard(
      title: '系统资源',
      subtitle: '服务器实时负载与网络优化状态',
      action: IconButton.filledTonal(
        onPressed: disabled ? null : onReboot,
        tooltip: '重启服务器',
        icon: const Icon(Icons.restart_alt_rounded),
      ),
      child: GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          childAspectRatio: 2.15,
          crossAxisSpacing: 9,
          mainAxisSpacing: 9,
        ),
        itemCount: rows.length,
        itemBuilder: (context, index) => DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Colors.white.withValues(
                  alpha: Theme.of(context).brightness == Brightness.dark
                      ? .09
                      : .62,
                ),
                Theme.of(context).colorScheme.surfaceContainerHighest
                    .withValues(alpha: .34),
              ],
            ),
            border: Border.all(
              color: Colors.white.withValues(
                alpha: Theme.of(context).brightness == Brightness.dark
                    ? .18
                    : .82,
              ),
            ),
            borderRadius: BorderRadius.circular(12),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(
                  alpha: Theme.of(context).brightness == Brightness.dark
                      ? .18
                      : .07,
                ),
                blurRadius: 12,
                offset: const Offset(0, 5),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  rows[index].$1,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 3),
                Text(
                  rows[index].$2,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _InlineWarning extends StatelessWidget {
  const _InlineWarning({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Material(
    color: Theme.of(context).colorScheme.errorContainer,
    borderRadius: BorderRadius.circular(12),
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_rounded),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
    ),
  );
}

class _LoadError extends StatelessWidget {
  const _LoadError({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.cloud_off_rounded,
            size: 48,
            color: Theme.of(context).colorScheme.error,
          ),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('重试'),
          ),
        ],
      ),
    ),
  );
}
