import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';
import '../core/glass.dart';
import 'budget_actions.dart';
import 'network_monitor.dart';

class NodeTelemetryCard extends ConsumerStatefulWidget {
  const NodeTelemetryCard({
    required this.item,
    super.key,
    this.embedded = false,
    this.showTelemetry = true,
    this.showBudget = true,
    this.showActions = true,
  });
  final Map<String, dynamic> item;
  final bool embedded;
  final bool showTelemetry;
  final bool showBudget;
  final bool showActions;
  @override
  ConsumerState<NodeTelemetryCard> createState() => _NodeTelemetryState();
}

class _NodeTelemetryState extends ConsumerState<NodeTelemetryCard> {
  Map<String, dynamic> _network = {};
  Timer? _timer;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted &&
          TickerMode.valuesOf(context).enabled &&
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
        _load();
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    if (_busy) return;
    _busy = true;
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/line-monitor?range=5m');
      final network = data['network'] as Map? ?? {};
      final row = network[widget.item['originId']] as Map?;
      if (mounted) {
        setState(() => _network = Map<String, dynamic>.from(row ?? {}));
      }
    } catch (_) {
      if (mounted) setState(() => _network = {});
    } finally {
      _busy = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final budget = item['budget'] is Map
        ? Map<String, dynamic>.from(item['budget'])
        : null;
    final percent = (budget?['percent'] as num? ?? 0).toDouble();
    final points = (_network['points'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    String rate(String key) {
      if (_network['fresh'] != true || _network[key] is! num) return '—';
      final kbps = (_network[key] as num) * 8 / 1000;
      return kbps < 1000
          ? '${kbps.toStringAsFixed(1)} Kbps'
          : '${(kbps / 1000).toStringAsFixed(2)} Mbps';
    }

    final content = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!widget.embedded) ...[
          Row(
            children: [
              Expanded(
                child: Text(
                  item['name']?.toString() ?? '未知节点',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 14,
                    height: 1.1,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                '${item['onlineDevices'] ?? '—'} 台在线',
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ),
          Text(
            item['serverIp']?.toString() ?? '',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 10,
              height: 1.1,
              color: Color(0xFFBCCDE1),
            ),
          ),
          Text(
            '${item['kind'] == 'local' ? '面板节点' : '远端数据节点'} · ${_network['fresh'] == true ? '新鲜' : '暂无新鲜数据'}',
            style: const TextStyle(
              fontSize: 10,
              height: 1.1,
              color: Color(0xFFBCCDE1),
            ),
          ),
        ],
        if (widget.showTelemetry) ...[
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                flex: 6,
                child: SizedBox(
                  height: 26,
                  child: points.isEmpty
                      ? const Center(
                          child: Text('暂无采样', style: TextStyle(fontSize: 11)),
                        )
                      : CustomPaint(painter: RatePainter([points], 7.5)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                flex: 4,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '↓ ${rate('rx')}',
                      style: const TextStyle(
                        color: Color(0xFF00E1DF),
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      '↑ ${rate('tx')}',
                      style: const TextStyle(
                        color: Color(0xFFBC9BEF),
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
        if (widget.showBudget) ...[
          const SizedBox(height: 4),
          LinearProgressIndicator(
            value: budget == null ? 0 : (percent / 100).clamp(0, 1),
            color: const Color(0xFF96BBFF),
            minHeight: 5,
          ),
          const SizedBox(height: 4),
          Text(
            budget == null
                ? '未设置预算 · 已用 ${formatPanelBytes((item['txBytes'] as num? ?? 0) + (item['rxBytes'] as num? ?? 0))}'
                : '${formatPanelBytes(budget['usedBytes'])} / ${formatPanelBytes(budget['limitBytes'])} · ${percent.toStringAsFixed(1)}%',
            style: const TextStyle(
              color: Color(0xFF00E1DF),
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
          if ((budget?['forecastText']?.toString() ?? '').isNotEmpty)
            Text(
              budget!['forecastText'].toString(),
              style: const TextStyle(
                fontSize: 10,
                height: 1.1,
                color: Color(0xFFBCCDE1),
              ),
            ),
          if (widget.showActions &&
              (item['originId']?.toString() ?? '').isNotEmpty)
            BudgetActions(
              originId: item['originId'],
              budget: budget,
              resetLabel: budget?['nextResetDate'] == null
                  ? null
                  : '重置 ${budget!['nextResetDate']}',
            ),
        ],
      ],
    );
    return widget.embedded
        ? content
        : GlassCard(
            child: Padding(padding: const EdgeInsets.all(8), child: content),
          );
  }
}
