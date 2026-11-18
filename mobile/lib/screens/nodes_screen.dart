import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';
import '../core/glass.dart';
import 'admin_controls.dart';
import 'node_enrollment.dart';
import 'node_telemetry_card.dart';

class NodesScreen extends ConsumerStatefulWidget {
  const NodesScreen({super.key});

  @override
  ConsumerState<NodesScreen> createState() => _NodesScreenState();
}

class _NodesScreenState extends ConsumerState<NodesScreen>
    with WidgetsBindingObserver, AutomaticKeepAliveClientMixin {
  List<Map<String, dynamic>> _nodes = [];
  final Set<String> _expanded = {};
  final Map<String, double> _trafficRates = {};
  final Map<String, int> _trafficTotals = {};
  int? _trafficObservedAt;
  List<Map<String, dynamic>> _budgets = [];
  bool _enrolling = false;
  bool _loading = true;
  bool _refreshing = false;
  int _loadGeneration = 0;
  String? _error;
  Timer? _timer;
  final _detailsRevision = ValueNotifier<int>(0);
  final _nodeActions = <String>{};

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(_load);
    _timer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted &&
          !_refreshing &&
          TickerMode.valuesOf(context).enabled &&
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
        _load(silent: true);
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _load(silent: true);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _detailsRevision.dispose();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!mounted) return;
    final generation = ++_loadGeneration;
    _refreshing = true;
    if (!silent) setState(() => _loading = true);
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/nodes');
      if (!mounted || generation != _loadGeneration) return;
      final items = (data['items'] as List? ?? const [])
          .map((value) => Map<String, dynamic>.from(value as Map))
          .toList();
      final observedAt = (data['observedAt'] as num? ?? 0).toInt();
      final elapsed = _trafficObservedAt == null
          ? 0
          : observedAt - _trafficObservedAt!;
      for (final node in items) {
        final id = node['nodeId'].toString();
        final total = (node['totalBytes'] as num? ?? 0).toInt();
        final previous = _trafficTotals[id];
        _trafficRates[id] = previous == null || elapsed <= 0 || total < previous
            ? 0
            : (total - previous) / elapsed;
        _trafficTotals[id] = total;
      }
      _trafficObservedAt = observedAt;
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _nodes = items;
          _loading = false;
          _error = null;
        });
        _detailsRevision.value++;
      }
    } on ApiException catch (error) {
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _loading = false;
          _error = error.message;
        });
        _detailsRevision.value++;
      }
    } finally {
      if (generation == _loadGeneration) _refreshing = false;
    }
  }

  Future<void> _setNodeEnabled(
    Map<String, dynamic> node,
    bool enabled,
    BuildContext detailContext,
  ) async {
    final id = node['nodeId'].toString();
    if (!_nodeActions.add(id)) return;
    _detailsRevision.value++;
    try {
      final label = enabled ? '启用' : '紧急停用';
      final confirmed = await showDialog<bool>(
        context: detailContext,
        builder: (context) => GlassDialog(
          title: Text('确认$label面板本机节点'),
          content: Text(
            enabled
                ? '启用后节点将重新承载连接。确认继续吗？'
                : '紧急停用会立即中断该节点上的现有连接，仅应在故障或安全事件中使用。',
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
      if (confirmed != true || !mounted) return;
      try {
        await ref
            .read(appControllerProvider.notifier)
            .postJson(
              '/api/v1/mobile/nodes/local/${enabled ? 'enable' : 'disable'}',
            );
        if (detailContext.mounted &&
            ModalRoute.of(detailContext) is PopupRoute) {
          Navigator.pop(detailContext);
        }
        await _load(silent: true);
        if (mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text('$label任务已提交')));
        }
      } on ApiException catch (error) {
        if (detailContext.mounted) {
          await showGlassError(detailContext, error.message);
        } else if (mounted) {
          await showGlassError(context, error.message);
        }
      }
    } finally {
      _nodeActions.remove(id);
      if (mounted) _detailsRevision.value++;
    }
  }

  Future<void> _pairingAction(
    Map<String, dynamic> node,
    String action,
    BuildContext detailContext,
  ) async {
    final id = node['nodeId'].toString();
    if (!_nodeActions.add(id)) return;
    _detailsRevision.value++;
    try {
      final disconnect = action == 'disconnect';
      final confirmed = await showDialog<bool>(
        context: detailContext,
        builder: (context) => GlassDialog(
          title: Text(disconnect ? '确认一键断连' : '确认删除对接'),
          content: Text(
            disconnect
                ? '远端服务器会立即停止对接业务，并卸载本项目安装的服务、身份、配置、状态、防火墙规则和网络参数。'
                : '立即撤销此节点的面板授权并移出当前列表，无需远端确认。不会卸载服务器文件，也不保证已有连接立即断开；历史流量保留。',
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
                child: Text(disconnect ? '一键断连' : '删除对接'),
              ),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
      try {
        await ref
            .read(appControllerProvider.notifier)
            .postJson('/api/v1/mobile/nodes/${node['nodeId']}/$action');
        if (detailContext.mounted &&
            ModalRoute.of(detailContext) is PopupRoute) {
          Navigator.pop(detailContext);
        }
        await _load(silent: true);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(disconnect ? '远端卸载任务已提交' : '对接已从面板删除')),
          );
        }
      } on ApiException catch (error) {
        if (detailContext.mounted) {
          await showGlassError(detailContext, error.message);
        } else if (mounted) {
          await showGlassError(context, error.message);
        }
      }
    } finally {
      _nodeActions.remove(id);
      if (mounted) _detailsRevision.value++;
    }
  }

  Future<void> _showNode(Map<String, dynamic> selectedNode) {
    var copiedId = false;
    return showGlassModalBottomSheet<void>(
      context: context,
      builder: (sheetContext) => ValueListenableBuilder<int>(
        valueListenable: _detailsRevision,
        builder: (context, revision, child) {
          final matches = _nodes.where(
            (item) => item['nodeId'] == selectedNode['nodeId'],
          );
          if (matches.isEmpty) {
            return const SafeArea(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text('此节点已从面板移除，请关闭详情并刷新列表。'),
              ),
            );
          }
          final node = matches.first;
          final busy = _nodeActions.contains(node['nodeId'].toString());
          final isLocal = node['kind'] == 'local';
          final rows = isLocal
              ? [
                  ('节点类型', '面板本机节点'),
                  ('面板入口', node['observedIp']),
                  ('在线设备', node['onlineDevices'] ?? '—'),
                  ('累计上传', formatBytes(node['txBytes'])),
                  ('累计下载', formatBytes(node['rxBytes'])),
                  ('累计流量', formatBytes(node['totalBytes'])),
                  ('实时流量', '${formatBytes(_trafficRates['local'] ?? 0)}/s'),
                  ('最后采样', formatTimestamp(node['trafficObservedAt'])),
                ]
              : [
                  ('节点 ID', node['nodeId']),
                  (
                    '公网 IP',
                    node['observedIp']?.toString().isNotEmpty == true
                        ? node['observedIp']
                        : node['expectedIp'],
                  ),
                  ('主机名', node['hostname']),
                  ('Agent 版本', node['agentVersion']),
                  (
                    '平台',
                    [node['platform'], node['architecture']]
                        .where(
                          (value) =>
                              value != null && value.toString().isNotEmpty,
                        )
                        .join(' '),
                  ),
                  ('控制协议', node['policyState']),
                  ('数据面', node['dataPlaneState']),
                  ('在线设备', node['onlineDevices'] ?? '—'),
                  ('最后心跳', formatTimestamp(node['lastHeartbeatAt'])),
                  ('在线快照', formatTimestamp(node['lastSnapshotAt'])),
                  ('流量 ACK', formatTimestamp(node['lastTrafficAckAt'])),
                  ('待执行命令', node['pendingCommands']),
                  ('失败命令', node['failedCommands']),
                  ('累计上传', formatBytes(node['txBytes'])),
                  ('累计下载', formatBytes(node['rxBytes'])),
                  ('累计流量', formatBytes(node['totalBytes'])),
                  (
                    '实时流量',
                    '${formatBytes(_trafficRates[node['nodeId']] ?? 0)}/s',
                  ),
                ];
          return SafeArea(
            child: DraggableScrollableSheet(
              expand: false,
              initialChildSize: .82,
              minChildSize: .55,
              maxChildSize: .95,
              builder: (context, controller) => ListView(
                controller: controller,
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                children: [
                  if (_error != null) RefreshWarning(message: '数据刷新失败：$_error'),
                  if (busy)
                    const Padding(
                      padding: EdgeInsets.only(bottom: 12),
                      child: Text('操作处理中，请稍候…'),
                    ),
                  Text(
                    node['name'].toString(),
                    style: Theme.of(context).textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  _StatusPill(status: node['status'].toString()),
                  const SizedBox(height: 12),
                  if (isLocal && node['canEmergencyControl'] == true) ...[
                    GlassControlSurface(
                      child: FilledButton.icon(
                        style: node['enabled'] == true
                            ? FilledButton.styleFrom(
                                backgroundColor: Theme.of(context)
                                    .colorScheme
                                    .error
                                    .withValues(alpha: .22),
                                foregroundColor: Theme.of(context)
                                    .colorScheme
                                    .error,
                              )
                            : null,
                        onPressed: busy
                            ? null
                            : () => _setNodeEnabled(
                                node,
                                node['enabled'] != true,
                                sheetContext,
                              ),
                        icon: Icon(
                          node['enabled'] == true
                              ? Icons.emergency_rounded
                              : Icons.play_arrow_rounded,
                        ),
                        label: Text(node['enabled'] == true ? '紧急停用' : '启用节点'),
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  if (!isLocal) ...[
                    GlassControlSurface(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: Theme.of(context).colorScheme.error
                              .withValues(alpha: .22),
                          foregroundColor: Theme.of(context).colorScheme.error,
                        ),
                        onPressed: !busy && node['canDisconnect'] == true
                            ? () => _pairingAction(
                                node,
                                'disconnect',
                                sheetContext,
                              )
                            : null,
                        icon: const Icon(Icons.link_off_rounded),
                        label: const Text('一键断连'),
                      ),
                    ),
                    const SizedBox(height: 10),
                    GlassControlSurface(
                      child: OutlinedButton.icon(
                        onPressed: !busy && node['canDeletePairing'] == true
                            ? () => _pairingAction(node, 'delete', sheetContext)
                            : null,
                        icon: const Icon(Icons.delete_outline_rounded),
                        label: const Text('删除对接'),
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  ...rows.map(
                    (item) => ListTile(
                      dense: true,
                      visualDensity: const VisualDensity(vertical: -2),
                      contentPadding: EdgeInsets.zero,
                      title: Text(item.$1),
                      subtitle: item.$1 == '节点 ID'
                          ? Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                SelectableText(
                                  item.$2?.toString().isNotEmpty == true
                                      ? item.$2.toString()
                                      : '不可用',
                                ),
                                if (copiedId)
                                  Semantics(
                                    liveRegion: true,
                                    child: const Text('节点 ID 已复制'),
                                  ),
                              ],
                            )
                          : Text(
                              item.$2?.toString().isNotEmpty == true
                                  ? item.$2.toString()
                                  : '不可用',
                            ),
                      trailing: item.$1 == '节点 ID'
                          ? GlassControlSurface(
                              child: IconButton(
                                tooltip: '复制节点 ID',
                                onPressed: () async {
                                  copiedId = false;
                                  _detailsRevision.value++;
                                  try {
                                    await Clipboard.setData(
                                      ClipboardData(text: item.$2.toString()),
                                    );
                                  } on PlatformException {
                                    if (context.mounted) {
                                      await showGlassError(
                                        context,
                                        '复制失败，请重试或长按节点 ID 手动复制',
                                      );
                                    }
                                    return;
                                  }
                                  if (mounted && context.mounted) {
                                    copiedId = true;
                                    _detailsRevision.value++;
                                  }
                                },
                                icon: const Icon(Icons.copy_rounded),
                              ),
                            )
                          : null,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _dataPlaneHelp(node['dataPlaneState']?.toString()),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (!isLocal)
                    AdminControls(
                      nodeId: node['nodeId'].toString(),
                      nodeProfile: node,
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  static String _dataPlaneHelp(String? state) {
    switch (state) {
      case 'local':
        return '这是面板所在服务器的本机节点，可在上方执行紧急停用或重新启用。';
      case 'not_issued':
        return '节点尚未领取数据面部署凭据。';
      case 'bootstrap_issued':
        return '正在自动配置 Hysteria、FULL 出口、双入口与网络优化。';
      case 'data_plane_installed':
        return '数据面已经安装，正在等待真实直连验证。';
      case 'direct_canary_passed':
        return '节点对接已经完成；DNS 由你自行维护，面板不会检查或修改。';
      case 'dns_admitted':
        return '节点对接已经完成；旧版本 DNS 状态不再参与控制。';
      default:
        return '数据面状态暂不可用。';
    }
  }

  Future<void> _loadBudgets() async {
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/overview');
      if (mounted) {
        setState(
          () => _budgets = (data['trafficBudgets'] as List? ?? [])
              .whereType<Map>()
              .map((e) => Map<String, dynamic>.from(e))
              .toList(),
        );
      }
    } catch (_) {
      /* Node controls stay available when overview is unavailable. */
    }
  }

  Future<void> _enroll() async {
    if (_enrolling) return;
    _enrolling = true;
    try {
      await showNodeEnrollment(context, ref);
    } finally {
      _enrolling = false;
    }
    if (mounted) _load(silent: true);
  }

  Future<void> _codes() async {
    await showGlassModalBottomSheet<void>(
      context: context,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(16),
          children: [
            Text('对接码管理', style: Theme.of(ctx).textTheme.titleLarge),
            const SizedBox(height: 8),
            const Text('新建对接码后，在目标服务器执行部署命令。已有节点可查看详情、重新对接或撤销授权。'),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: () {
                Navigator.pop(ctx);
                _enroll();
              },
              child: const Text('生成对接码'),
            ),
            for (final node in _nodes)
              ListTile(
                title: Text(node['name'].toString()),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.pop(ctx);
                  _showNode(node);
                },
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(10, 0, 10, 20),
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            const PanelHeading('节点管理'),
            Row(
              children: [
                Expanded(
                  child: _entry('节点对接', '添加或连接远端节点', Icons.link, _enroll),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _entry('对接码管理', '查看、生成与管理', Icons.qr_code, _codes),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text('节点列表', style: Theme.of(context).textTheme.titleLarge),
                Text(
                  '共 ${_nodes.length} 个节点',
                  style: const TextStyle(fontSize: 11),
                ),
                OutlinedButton(
                  onPressed: _enroll,
                  style: OutlinedButton.styleFrom(
                    backgroundColor: const Color(0xFF6240B8),
                  ),
                  child: const Text('＋ 添加节点'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (_loading && _nodes.isEmpty) const LinearProgressIndicator(),
            if (_error != null) RefreshWarning(message: '数据刷新失败：$_error'),
            for (final node in _nodes)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _nodeCard(node),
              ),
            if (!_loading && _nodes.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text('暂无节点，请点击添加节点'),
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
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(subtitle, style: const TextStyle(fontSize: 10)),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
  Widget _nodeCard(Map<String, dynamic> node) {
    final id = node['nodeId'].toString();
    final expanded = _expanded.contains(id);
    final matches = _budgets.where(
      (b) =>
          b['originId'] == node['originId'] ||
          (id != 'local' && b['originId'] == 'node:$id') ||
          (id == 'local' && b['kind'] == 'local'),
    );
    final item = matches.isNotEmpty
        ? matches.first
        : <String, dynamic>{
            ...node,
            'originId': node['originId'] ?? (id == 'local' ? '' : 'node:$id'),
          };
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => setState(() {
              if (expanded) {
                _expanded.remove(id);
              } else {
                _expanded.add(id);
                _loadBudgets();
              }
            }),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          node['name'].toString(),
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${id == 'local' ? '面板节点' : '远端数据节点'} · ${nodeStatusLabel(node['status'])}',
                          style: TextStyle(
                            fontSize: 12,
                            color: node['status'] == 'online'
                                ? const Color(0xFF00E1DF)
                                : const Color(0xFFBC9BEF),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '${node['onlineDevices'] ?? '—'} 台设备',
                    style: const TextStyle(fontSize: 12),
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
          AnimatedSize(
            duration: MediaQuery.disableAnimationsOf(context)
                ? Duration.zero
                : const Duration(milliseconds: 200),
            child: !expanded
                ? const SizedBox(width: double.infinity)
                : Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        NodeTelemetryCard(
                          item: item,
                          embedded: true,
                          showBudget: false,
                        ),
                        const SizedBox(height: 10),
                        AdminControls(
                          nodeId: id,
                          nodeProfile: node,
                          compact: true,
                          originId: item['originId']?.toString(),
                          budgetData: item['budget'] is Map
                              ? Map<String, dynamic>.from(item['budget'])
                              : null,
                          onDisconnect: node['canDisconnect'] == true
                              ? () =>
                                    _pairingAction(node, 'disconnect', context)
                              : null,
                          budget: NodeTelemetryCard(
                            item: item,
                            embedded: true,
                            showTelemetry: false,
                            showActions: false,
                          ),
                        ),
                        const SizedBox(height: 8),
                        OutlinedButton(
                          onPressed: () => _showNode(node),
                          child: const Text('节点详情与对接管理'),
                        ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status});
  final String status;
  @override
  Widget build(BuildContext context) {
    final color = status == 'online'
        ? Colors.green
        : status == 'revoked' || status == 'registration_expired'
        ? Theme.of(context).colorScheme.error
        : Colors.orange;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .13),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        nodeStatusLabel(status),
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
