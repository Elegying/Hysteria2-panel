import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';
import '../core/glass.dart';
import 'network_monitor.dart';
import 'node_telemetry_card.dart';

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

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final data = _data;
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(10, 0, 10, 6),
          children: [
            const PanelHeading('总览'),
            if (_loading && data == null)
              const Center(child: CircularProgressIndicator()),
            if (_error != null) RefreshWarning(message: _error!),
            if (data != null) ...[
              _SummaryGrid(data: data),
              const SizedBox(height: 6),
              const NetworkMonitor(),
              const SizedBox(height: 6),
              for (final item
                  in (data['trafficBudgets'] as List? ?? []).whereType<Map>())
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: NodeTelemetryCard(
                    item: Map<String, dynamic>.from(item),
                  ),
                ),
              if ((data['trafficBudgets'] as List? ?? []).isEmpty)
                const GlassCard(
                  child: Padding(
                    padding: EdgeInsets.all(20),
                    child: Text('暂无节点流量数据'),
                  ),
                ),
            ],
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
    final users = data['users'] as Map? ?? {};
    final nodes = data['nodes'] as Map? ?? {};
    final traffic = data['traffic'] as Map? ?? {};
    final entries = [
      ('在线节点', '${nodes['online'] ?? 0}/${nodes['total'] ?? 0}'),
      ('在线设备', '${users['onlineDevices'] ?? 0}'),
      ('总上传流量', formatPanelBytes(traffic['txBytes'])),
      ('总下载流量', formatPanelBytes(traffic['rxBytes'])),
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: LayoutBuilder(
        builder: (context, box) {
          final columns = MediaQuery.textScalerOf(context).scale(14) > 21
              ? 1
              : 2;
          return Wrap(
            spacing: 12,
            runSpacing: 3,
            children: [
              for (final e in entries)
                SizedBox(
                  width: (box.maxWidth - (columns - 1) * 12) / columns,
                  child: Row(
                    children: [
                      Text(e.$1, style: const TextStyle(fontSize: 12)),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          e.$2,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
