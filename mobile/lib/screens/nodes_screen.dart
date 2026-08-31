import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';

class NodesScreen extends ConsumerStatefulWidget {
  const NodesScreen({super.key});

  @override
  ConsumerState<NodesScreen> createState() => _NodesScreenState();
}

class _NodesScreenState extends ConsumerState<NodesScreen>
    with WidgetsBindingObserver, AutomaticKeepAliveClientMixin {
  List<Map<String, dynamic>> _nodes = [];
  Map<String, dynamic> _summary = {};
  bool _loading = true;
  String? _error;
  Timer? _timer;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(_load);
    _timer = Timer.periodic(
      const Duration(seconds: 15),
      (_) => _load(silent: true),
    );
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
    if (!silent && mounted) setState(() => _loading = true);
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/nodes');
      final items = (data['items'] as List? ?? const [])
          .map((value) => Map<String, dynamic>.from(value as Map))
          .toList();
      if (mounted) {
        setState(() {
          _summary = data;
          _nodes = items;
          _loading = false;
          _error = null;
        });
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = error.message;
        });
      }
    }
  }

  Future<void> _verify(
    Map<String, dynamic> node,
    BuildContext detailContext,
  ) async {
    final short = node['fingerprintShort']?.toString() ?? '';
    final confirmed = await showDialog<bool>(
      context: detailContext,
      builder: (context) => AlertDialog(
        title: const Text('核对节点短码'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('请确认服务器终端显示的 16 位短码与下面完全一致：'),
            const SizedBox(height: 16),
            SelectableText(
              short,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                fontFamily: 'monospace',
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('不一致'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('短码一致，开始部署'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(appControllerProvider.notifier).postJson(
        '/api/v1/mobile/nodes/${node['nodeId']}/verify',
        {'fingerprint': node['fingerprint']},
      );
      if (detailContext.mounted) Navigator.pop(detailContext);
      await _load(silent: true);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('节点已确认，自动部署即将开始')));
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
    final rows = [
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
      ('DNS 准入', node['dnsAdmitted'] == true ? '已准入' : '未准入'),
      ('在线设备', node['onlineDevices'] ?? '—'),
      ('最后心跳', formatTimestamp(node['lastHeartbeatAt'])),
      ('在线快照', formatTimestamp(node['lastSnapshotAt'])),
      ('流量 ACK', formatTimestamp(node['lastTrafficAckAt'])),
      ('待执行命令', node['pendingCommands']),
      ('失败命令', node['failedCommands']),
    ];
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
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
                    ?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 4),
              _StatusPill(status: node['status'].toString()),
              const SizedBox(height: 18),
              if (node['status'] == 'pending_verification' &&
                  node['fingerprintShort'].toString().isNotEmpty) ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          '等待安全确认',
                          style: TextStyle(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          '与服务器终端核对短码 ${node['fingerprintShort']}，一致后才能开始自动部署。',
                        ),
                        const SizedBox(height: 12),
                        FilledButton.icon(
                          onPressed: () => _verify(node, sheetContext),
                          icon: const Icon(Icons.verified_user_rounded),
                          label: const Text('核对短码并确认'),
                        ),
                      ],
                    ),
                  ),
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
      case 'not_issued':
        return '节点尚未领取数据面部署凭据。';
      case 'bootstrap_issued':
        return '正在自动配置 Hysteria、FULL 出口、双入口与网络优化。';
      case 'data_plane_installed':
        return '数据面已经安装，正在等待真实直连验证。';
      case 'direct_canary_passed':
        return '直连验证已经通过，请手动把节点 IP 添加到 DNS。';
      case 'dns_admitted':
        return 'DNS 已检测并准入，节点可以正常承载用户连接。';
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
              pinned: true,
              title: const Text('节点'),
              actions: [
                IconButton(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh_rounded),
                  tooltip: '刷新',
                ),
              ],
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
                  child: Card(
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
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                  sliver: SliverList.separated(
                    itemCount: _nodes.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 9),
                    itemBuilder: (context, index) {
                      final node = _nodes[index];
                      return Card(
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
                                                fontWeight: FontWeight.w800,
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
            ],
          ],
        ),
      ),
    );
  }
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
            ?.copyWith(fontWeight: FontWeight.w800, color: color),
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
