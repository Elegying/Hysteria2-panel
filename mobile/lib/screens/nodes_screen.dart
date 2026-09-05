import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';
import '../core/glass.dart';

class NodesScreen extends ConsumerStatefulWidget {
  const NodesScreen({super.key});

  @override
  ConsumerState<NodesScreen> createState() => _NodesScreenState();
}

class _NodesScreenState extends ConsumerState<NodesScreen>
    with WidgetsBindingObserver, AutomaticKeepAliveClientMixin {
  List<Map<String, dynamic>> _nodes = [];
  Map<String, dynamic> _summary = {};
  final Map<String, int> _trafficTotals = {};
  final Map<String, double> _trafficRates = {};
  int? _trafficObservedAt;
  bool _loading = true;
  bool _refreshing = false;
  int _loadGeneration = 0;
  String? _error;
  Timer? _timer;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(_load);
    _timer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!_refreshing) _load(silent: true);
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
      final nextRates = <String, double>{};
      for (final node in items) {
        final id = node['nodeId'].toString();
        final total = (node['totalBytes'] as num? ?? 0).toInt();
        final previous = _trafficTotals[id];
        nextRates[id] = previous == null || elapsed <= 0 || total < previous
            ? 0
            : (total - previous) / elapsed;
        _trafficTotals[id] = total;
      }
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _summary = data;
          _nodes = items;
          _trafficRates
            ..clear()
            ..addAll(nextRates);
          _trafficObservedAt = observedAt;
          _loading = false;
          _error = null;
        });
      }
    } on ApiException catch (error) {
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _loading = false;
          _error = error.message;
        });
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
    final label = enabled ? '启用' : '紧急停用';
    final confirmed = await showDialog<bool>(
      context: detailContext,
      builder: (context) => GlassDialog(
        title: Text('确认$label面板本机节点'),
        content: Text(
          enabled ? '启用后节点将重新承载连接。确认继续吗？' : '紧急停用会立即中断该节点上的现有连接，仅应在故障或安全事件中使用。',
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
    try {
      await ref
          .read(appControllerProvider.notifier)
          .postJson(
            '/api/v1/mobile/nodes/local/${enabled ? 'enable' : 'disable'}',
          );
      if (detailContext.mounted) Navigator.pop(detailContext);
      await _load(silent: true);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$label任务已提交')));
      }
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(error.message),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }

  Future<void> _pairingAction(
    Map<String, dynamic> node,
    String action,
    BuildContext detailContext,
  ) async {
    final disconnect = action == 'disconnect';
    final confirmed = await showDialog<bool>(
      context: detailContext,
      builder: (context) => GlassDialog(
        title: Text(disconnect ? '确认一键断连' : '确认删除对接'),
        content: Text(
          disconnect
              ? '远端服务器会立即停止对接业务，并卸载本项目安装的服务、身份、配置、状态、防火墙规则和网络参数。'
              : '仅在服务器已失联时使用。此操作只吊销面板中的对接，不会清理失联服务器上的文件。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(disconnect ? '一键断连' : '删除对接'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref
          .read(appControllerProvider.notifier)
          .postJson('/api/v1/mobile/nodes/${node['nodeId']}/$action');
      if (detailContext.mounted) Navigator.pop(detailContext);
      await _load(silent: true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(disconnect ? '远端卸载任务已提交' : '对接已从面板删除')),
        );
      }
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(error.message),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }

  Future<void> _showNode(Map<String, dynamic> node) {
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
              node['observedIp'].toString().isNotEmpty
                  ? node['observedIp']
                  : node['expectedIp'],
            ),
            ('主机名', node['hostname']),
            ('Agent 版本', node['agentVersion']),
            ('平台', '${node['platform']} ${node['architecture']}'),
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
            ('实时流量', '${formatBytes(_trafficRates[node['nodeId']] ?? 0)}/s'),
          ];
    return showGlassModalBottomSheet<void>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: DraggableScrollableSheet(
          expand: false,
          initialChildSize: .82,
          minChildSize: .55,
          maxChildSize: .95,
          builder: (context, controller) => ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
            children: [
              Text(
                node['name'].toString(),
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              _StatusPill(status: node['status'].toString()),
              const SizedBox(height: 18),
              if (isLocal && node['canEmergencyControl'] == true) ...[
                FilledButton.icon(
                  style: node['enabled'] == true
                      ? FilledButton.styleFrom(
                          backgroundColor: Theme.of(context).colorScheme.error,
                        )
                      : null,
                  onPressed: () => _setNodeEnabled(
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
                const SizedBox(height: 12),
              ],
              if (!isLocal) ...[
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.error,
                  ),
                  onPressed: node['canDisconnect'] == true
                      ? () => _pairingAction(node, 'disconnect', sheetContext)
                      : null,
                  icon: const Icon(Icons.link_off_rounded),
                  label: const Text('一键断连'),
                ),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: node['canDeletePairing'] == true
                      ? () => _pairingAction(node, 'delete', sheetContext)
                      : null,
                  icon: const Icon(Icons.delete_outline_rounded),
                  label: const Text('删除对接'),
                ),
                const SizedBox(height: 12),
              ],
              ...rows.map(
                (item) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(item.$1),
                  subtitle: Text(
                    item.$2?.toString().isNotEmpty == true
                        ? item.$2.toString()
                        : '不可用',
                  ),
                  trailing: item.$1 == '节点 ID'
                      ? IconButton(
                          tooltip: '复制节点 ID',
                          onPressed: () async {
                            await Clipboard.setData(
                              ClipboardData(text: item.$2.toString()),
                            );
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('节点 ID 已复制')),
                              );
                            }
                          },
                          icon: const Icon(Icons.copy_rounded),
                        )
                      : null,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _dataPlaneHelp(node['dataPlaneState']?.toString()),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
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

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final counts = Map<String, dynamic>.from(
      _summary['statusCounts'] as Map? ?? {},
    );
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverAppBar(
              toolbarHeight: 64,
              pinned: false,
              title: const Text('节点'),
              actions: [
                IconButton(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh_rounded),
                  tooltip: '刷新',
                ),
              ],
            ),
            if (_error != null && _nodes.isNotEmpty)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: RefreshWarning(message: '数据刷新失败：$_error'),
                ),
              ),
            if (_loading && _nodes.isEmpty)
              const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null && _nodes.isEmpty)
              SliverFillRemaining(
                child: Center(
                  child: FilledButton.icon(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh_rounded),
                    label: Text(_error!),
                  ),
                ),
              )
            else ...[
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 14),
                  child: GlassCard(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceAround,
                        children: [
                          _Count(
                            label: '全部',
                            value: '${_summary['total'] ?? 0}',
                          ),
                          _Count(
                            label: '在线',
                            value: '${_summary['online'] ?? 0}',
                            color: Colors.green,
                          ),
                          _Count(
                            label: '离线',
                            value: '${counts['offline'] ?? 0}',
                            color: Colors.orange,
                          ),
                          _Count(
                            label: '待处理',
                            value:
                                '${(counts['pending_registration'] ?? 0) + (counts['pending_verification'] ?? 0)}',
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              if (_nodes.isEmpty)
                const SliverFillRemaining(
                  child: Center(child: Text('暂无节点，请从首页点击“对接”添加节点')),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                  sliver: SliverList.separated(
                    itemCount: _nodes.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 9),
                    itemBuilder: (context, index) {
                      final node = _nodes[index];
                      return GlassCard(
                        child: InkWell(
                          onTap: () => _showNode(node),
                          borderRadius: BorderRadius.circular(18),
                          child: Padding(
                            padding: const EdgeInsets.all(15),
                            child: Row(
                              children: [
                                CircleAvatar(
                                  child: Icon(
                                    node['status'] == 'online'
                                        ? Icons.dns_rounded
                                        : Icons.dns_outlined,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          Expanded(
                                            child: Text(
                                              node['name'].toString(),
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                              style: const TextStyle(
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                          ),
                                          _StatusPill(
                                            status: node['status'].toString(),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 5),
                                      Text(
                                        node['observedIp'].toString().isNotEmpty
                                            ? node['observedIp'].toString()
                                            : node['expectedIp'].toString(),
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall,
                                      ),
                                      Text(
                                        '${node['onlineDevices'] ?? '—'} 台在线 · 心跳 ${formatTimestamp(node['lastHeartbeatAt'])}',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall,
                                      ),
                                    ],
                                  ),
                                ),
                                const Icon(Icons.chevron_right_rounded),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              if (_nodes.isNotEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                    child: _RealtimeTrafficCard(
                      nodes: _nodes,
                      rates: _trafficRates,
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RealtimeTrafficCard extends StatelessWidget {
  const _RealtimeTrafficCard({required this.nodes, required this.rates});
  final List<Map<String, dynamic>> nodes;
  final Map<String, double> rates;

  @override
  Widget build(BuildContext context) => GlassCard(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '服务器节点实时流量',
            style: Theme.of(context).textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 3),
          Text('每 5 秒采样一次节点累计流量', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 12),
          ...nodes.map(
            (node) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    node['name'].toString(),
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    children: [
                      Text(
                        '${formatBytes(rates[node['nodeId']] ?? 0)}/s',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                      Text(
                        '累计 ${formatBytes(node['totalBytes'])}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
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

class _Count extends StatelessWidget {
  const _Count({required this.label, required this.value, this.color});
  final String label;
  final String value;
  final Color? color;
  @override
  Widget build(BuildContext context) => Column(
    children: [
      Text(
        value,
        style: Theme.of(context).textTheme.titleLarge
            ?.copyWith(fontWeight: FontWeight.w700, color: color),
      ),
      Text(label, style: Theme.of(context).textTheme.bodySmall),
    ],
  );
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
