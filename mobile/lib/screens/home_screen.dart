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
  bool _refreshing = false;
  int _loadGeneration = 0;
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
    _timer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (mounted &&
          !_refreshing &&
          TickerMode.valuesOf(context).enabled &&
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
        _load(silent: true);
      }
    });
  }

  Future<void> _load({bool silent = false}) async {
    if (!mounted) return;
    final generation = ++_loadGeneration;
    _refreshing = true;
    if (!silent) setState(() => _loading = true);
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/overview');
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _data = data;
          _error = null;
          _loading = false;
        });
      }
    } on ApiException catch (error) {
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _error = error.message;
          _loading = false;
        });
      }
    } finally {
      if (generation == _loadGeneration) _refreshing = false;
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
            GlassControlSurface(
              child: TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('取消'),
              ),
            ),
            GlassControlSurface(
              child: FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: Text(label),
              ),
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
          GlassControlSurface(
            child: TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
          ),
          GlassControlSurface(
            child: FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('重启服务器'),
            ),
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
    var submitting = false;
    String? formError;
    final result = await showGlassFormDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => GlassDialog(
          title: const Text('对接新节点'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('生成前请先自行把需要的域名解析到目标服务器公网 IP。面板不会查询、修改或等待 DNS。'),
                const SizedBox(height: 16),
                GlassControlSurface(
                  child: TextField(
                    controller: name,
                    decoration: const InputDecoration(labelText: '节点名称'),
                  ),
                ),
                const SizedBox(height: 12),
                GlassControlSurface(
                  child: TextField(
                    controller: expectedIp,
                    decoration: const InputDecoration(labelText: '目标服务器公网 IP'),
                  ),
                ),
                if (formError != null)
                  Text(
                    formError!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
              ],
            ),
          ),
          actions: [
            GlassControlSurface(
              child: TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('取消'),
              ),
            ),
            GlassControlSurface(
              child: FilledButton(
                onPressed: submitting
                    ? null
                    : () async {
                        if (submitting) return;
                        if (name.text.trim().isEmpty ||
                            expectedIp.text.trim().isEmpty) {
                          setDialogState(
                            () => formError = '请填写节点名称和目标服务器公网 IP',
                          );
                          return;
                        }
                        setDialogState(() {
                          submitting = true;
                          formError = null;
                        });
                        try {
                          final data = await ref
                              .read(appControllerProvider.notifier)
                              .postJson('/api/v1/mobile/node-enrollments', {
                                'name': name.text.trim(),
                                'expectedIp': expectedIp.text.trim(),
                                'ttlMinutes': 10,
                                'mode': 'join',
                              });
                          if (dialogContext.mounted &&
                              ModalRoute.of(dialogContext)?.isCurrent == true) {
                            Navigator.pop(dialogContext, data);
                          }
                        } on ApiException catch (error) {
                          if (dialogContext.mounted &&
                              ModalRoute.of(dialogContext)?.isCurrent == true) {
                            setDialogState(() {
                              submitting = false;
                              formError = error.message;
                            });
                          }
                        }
                      },
                child: Text(submitting ? '生成中…' : '一键对接'),
              ),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    expectedIp.dispose();
    if (result == null || !mounted) return;
    final command = result['deploymentCommand']?.toString() ?? '';
    var copied = false;
    try {
      await Clipboard.setData(ClipboardData(text: command));
      copied = true;
    } on PlatformException {
      // The enrollment has already been created. Always expose its result.
    }
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setResultState) => GlassDialog(
          title: const Text('部署代码已生成'),
          content: SizedBox(
            width: 620,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    copied
                        ? '代码已复制。请在目标服务器以 root 粘贴运行；短时授权只能使用一次。'
                        : '自动复制失败。请手动选择下方代码，或重试复制；短时授权只能使用一次。',
                  ),
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
            GlassControlSurface(
              child: TextButton(
                onPressed: () async {
                  var succeeded = false;
                  try {
                    await Clipboard.setData(ClipboardData(text: command));
                    succeeded = true;
                  } on PlatformException {
                    // Keep the selectable command available for manual copying.
                  }
                  if (context.mounted) setResultState(() => copied = succeeded);
                },
                child: Text(copied ? '再次复制' : '重试复制'),
              ),
            ),
            GlassControlSurface(
              child: TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('关闭'),
              ),
            ),
          ],
        ),
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
              toolbarHeight: 64,
              pinned: false,
              title: const Text('首页'),
              actions: [
                GlassControlSurface(
                  child: IconButton(
                    onPressed: _loading ? null : _load,
                    tooltip: '刷新',
                    icon: const Icon(Icons.refresh_rounded),
                  ),
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
                      RefreshWarning(message: '数据刷新失败：$_error'),
                      const SizedBox(height: 12),
                    ],
                    _StatusHeader(data: data),
                    const SizedBox(height: 14),
                    _SummaryGrid(data: data),
                    const SizedBox(height: 14),
                    _BudgetsCard(data: data),
                    const SizedBox(height: 14),
                    _SectionCard(
                      title: '服务控制',
                      subtitle: '管理本机服务，或连接新的服务器',
                      child: _ServiceButtons(
                        disabled: _acting,
                        onStart: () => _serviceAction('start', '启动'),
                        onRestart: () => _serviceAction('restart', '重启'),
                        onStop: () => _serviceAction('stop', '停止'),
                        onEnroll: _showEnrollment,
                      ),
                    ),
                    const SizedBox(height: 14),
                    _ResourcesCard(
                      data: data,
                      disabled: _acting,
                      onReboot: _rebootServer,
                    ),
                    SizedBox(height: appDockExtent(context)),
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
    final nodes = Map<String, dynamic>.from(data['nodes'] as Map? ?? {});
    final online = (nodes['online'] as num?) ?? 0;
    final total = (nodes['total'] as num?) ?? 0;
    final accent = active ? const Color(0xFF8CEAD3) : const Color(0xFFFFBEAD);
    final scale = MediaQuery.textScalerOf(context).scale(14) / 14;
    final ring = SizedBox.square(
      dimension: 106,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox.square(
            dimension: 100,
            child: CircularProgressIndicator(
              value: total > 0 ? (online / total).clamp(0, 1) : 0,
              strokeWidth: 5,
              strokeCap: StrokeCap.round,
              color: accent,
              backgroundColor: Colors.white.withValues(alpha: .12),
              semanticsLabel: '在线节点 $online / $total',
            ),
          ),
          ExcludeSemantics(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '$online',
                  style: const TextStyle(
                    fontSize: 32,
                    fontWeight: FontWeight.w600,
                    color: Colors.white,
                  ),
                ),
                Text(
                  '/ $total 节点',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(0xFFCCD9E6),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
    final status = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'NETWORK OVERVIEW',
          style: TextStyle(
            color: accent,
            fontSize: 11,
            letterSpacing: 1.5,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 16),
        Text(
          serviceLabel(data['serviceStatus']),
          style: const TextStyle(
            color: Colors.white,
            fontSize: 24,
            fontWeight: FontWeight.w700,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          data['panelName']?.toString() ?? 'Hysteria 2',
          style: const TextStyle(color: Color(0xFFCCD9E6), fontSize: 13),
        ),
      ],
    );
    return GlassSurface(
      borderRadius: 28,
      tintColor: const Color(0xD0122F42),
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (scale > 1.3)
              status
            else
              Row(
                children: [
                  Expanded(child: status),
                  const SizedBox(width: 12),
                  ring,
                ],
              ),
            const SizedBox(height: 22),
            const Divider(
              color: Color(0xFF446072),
              indent: 0,
              endIndent: 0,
              height: 1,
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: [
                Text(
                  '面板 v${data['panelVersion'] ?? '-'}',
                  style: const TextStyle(
                    color: Color(0xFFCCD9E6),
                    fontSize: 12,
                  ),
                ),
                Text(
                  '最近刷新 ${formatTimestamp(data['refreshedAt'])}',
                  style: const TextStyle(
                    color: Color(0xFFCCD9E6),
                    fontSize: 12,
                  ),
                ),
              ],
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
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisExtent:
            114 + (MediaQuery.textScalerOf(context).scale(16) - 16) * 4,
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
                Row(
                  children: [
                    Icon(
                      item.$3,
                      size: 19,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        item.$1,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
                const Spacer(),
                Text(
                  item.$2,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                    fontSize: 28,
                    letterSpacing: -.6,
                  ),
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
                      ?.copyWith(fontWeight: FontWeight.w700),
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
        '一键对接',
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
                child: GlassControlSurface(
                  child: FilledButton.tonalIcon(
                    onPressed: disabled ? null : item.$3,
                    icon: Icon(item.$2, color: item.$4),
                    label: Text(item.$1),
                  ),
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
      title: '流量预算',
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
                        color: percent >= 95
                            ? Theme.of(context).colorScheme.error
                            : percent >= 80
                            ? const Color(0xFFB66A16)
                            : Theme.of(context).colorScheme.primary,
                        semanticsLabel:
                            '${item['name']} 流量用量${budget == null ? '，未设置预算' : ''}',
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
      action: GlassControlSurface(
        child: IconButton(
          color: Colors.orange,
          onPressed: disabled ? null : onReboot,
          tooltip: '重启服务器',
          icon: const Icon(Icons.restart_alt_rounded),
        ),
      ),
      child: GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisExtent:
              92 + (MediaQuery.textScalerOf(context).scale(16) - 16) * 4,
          crossAxisSpacing: 9,
          mainAxisSpacing: 9,
        ),
        itemCount: rows.length,
        itemBuilder: (context, index) => GlassSurface(
          borderRadius: 12,
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
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
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
          GlassControlSurface(
            child: FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('重试'),
            ),
          ),
        ],
      ),
    ),
  );
}
