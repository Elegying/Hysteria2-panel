import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';

class NetworkMonitor extends ConsumerStatefulWidget {
  const NetworkMonitor({super.key});
  @override
  ConsumerState<NetworkMonitor> createState() => _MonitorState();
}

class _MonitorState extends ConsumerState<NetworkMonitor>
    with WidgetsBindingObserver {
  Timer? _timer;
  String _range = '5m';
  Map<String, dynamic>? _data;
  String? _error;
  bool _busy = false;
  int _generation = 0;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _load();
    }
  }

  Future<void> _load() async {
    if (_busy) return;
    _busy = true;
    final generation = ++_generation;
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/line-monitor?range=$_range');
      if (mounted && generation == _generation) {
        setState(() {
          _data = data;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() => _error = e.toString());
      }
    } finally {
      _busy = false;
      if (mounted && generation != _generation) _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final network = Map<String, dynamic>.from(_data?['network'] as Map? ?? {});
    final samples = network.values.whereType<Map>().toList();
    double rate(String key) => samples.fold(
      0,
      (sum, s) =>
          sum +
          (s['fresh'] == true
              ? (s[key] as num? ?? 0).toDouble() * 8 / 1000000
              : 0),
    );
    final history = _range == 'today'
        ? Map<String, dynamic>.from(
            (_data?['today'] as Map?)?['network'] as Map? ?? {},
          )
        : network;
    final now = DateTime.now().millisecondsSinceEpoch / 1000;
    final series = <List<Map<String, dynamic>>>[];
    for (final row in history.values.whereType<Map>()) {
      series.add(
        (row['points'] as List? ?? [])
            .whereType<Map>()
            .map((p) => Map<String, dynamic>.from(p))
            .where(
              (p) => _range == 'today' || (p['at'] as num? ?? 0) >= now - 300,
            )
            .toList(),
      );
    }
    final buckets = <int, Map<String, Map<String, dynamic>>>{};
    final step = _range == 'today' ? 60 : 5;
    for (var origin = 0; origin < series.length; origin++) {
      for (final point in series[origin]) {
        final bucket = ((point['at'] as num).toDouble() / step).floor();
        (buckets[bucket] ??= {})['$origin'] = point;
      }
    }
    final keys = buckets.keys.toList()..sort();
    final totals = <Map<String, dynamic>>[];
    for (final key in keys) {
      final rows = buckets[key]!.values;
      final complete =
          rows.length == series.length &&
          rows.every((row) => row['rx'] is num && row['tx'] is num);
      totals.add({
        'at': key * step,
        'rx': complete
            ? rows.fold<double>(0, (sum, row) => sum + (row['rx'] as num))
            : null,
        'tx': complete
            ? rows.fold<double>(0, (sum, row) => sum + (row['tx'] as num))
            : null,
      });
    }
    return GlassCard(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text('全网实时速率', style: Theme.of(context).textTheme.titleLarge),
                SegmentedButton<String>(
                  showSelectedIcon: false,
                  style: const ButtonStyle(
                    textStyle: WidgetStatePropertyAll(
                      TextStyle(fontSize: 11, fontFamily: 'Roboto'),
                    ),
                    padding: WidgetStatePropertyAll(
                      EdgeInsets.symmetric(horizontal: 8),
                    ),
                  ),
                  segments: const [
                    ButtonSegment(value: '5m', label: Text('近 5 分钟')),
                    ButtonSegment(value: 'today', label: Text('今日')),
                  ],
                  selected: {_range},
                  onSelectionChanged: (values) {
                    setState(() {
                      _range = values.single;
                      _data = null;
                      ++_generation;
                    });
                    if (!_busy) _load();
                  },
                ),
              ],
            ),
            const SizedBox(height: 4),
            Wrap(
              spacing: 16,
              children: [
                Text(
                  '↓ 入站 ${samples.any((s) => s['fresh'] == true) ? rate('rx').toStringAsFixed(2) : '—'} Mbps',
                  style: const TextStyle(color: Color(0xFF00D9D0)),
                ),
                Text(
                  '↑ 出站 ${samples.any((s) => s['fresh'] == true) ? rate('tx').toStringAsFixed(2) : '—'} Mbps',
                  style: const TextStyle(color: Color(0xFFB29BFF)),
                ),
              ],
            ),
            if (_error != null) RefreshWarning(message: _error!),
            const SizedBox(height: 4),
            if (series.every((s) => s.isEmpty))
              const SizedBox(height: 60, child: Center(child: Text('暂无速率采样')))
            else
              SizedBox(
                height: (MediaQuery.sizeOf(context).height - 710).clamp(
                  62.0,
                  108.0,
                ),
                width: double.infinity,
                child: CustomPaint(
                  painter: RatePainter([totals], step * 1.5, axes: true),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class RatePainter extends CustomPainter {
  RatePainter(this.series, this.maxGap, {this.axes = false});
  final bool axes;
  final double maxGap;
  final List<List<Map<String, dynamic>>> series;
  @override
  void paint(Canvas canvas, Size size) {
    final points = series.expand((s) => s).toList();
    if (points.isEmpty) return;
    final times = points.map((p) => (p['at'] as num).toDouble());
    final start = times.reduce(math.min), end = times.reduce(math.max);
    final peak = points.fold<double>(
      1,
      (m, p) => math.max(
        m,
        math.max(
          (p['rx'] as num? ?? 0).toDouble(),
          (p['tx'] as num? ?? 0).toDouble(),
        ),
      ),
    );
    final left = axes ? 40.0 : 0.0;
    final bottom = axes ? 16.0 : 0.0;
    void label(String text, Offset at) {
      final painter = TextPainter(
        text: TextSpan(
          text: text,
          style: const TextStyle(
            color: Color(0xFFBCCDE1),
            fontSize: 8,
            fontFamily: 'Roboto',
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      painter.paint(canvas, at);
    }

    if (axes) {
      for (var i = 0; i < 4; i++) {
        label(
          '${(peak * 8 / 1000000 * (1 - i / 3)).round()} Mbps',
          Offset(0, (size.height - bottom) * i / 3),
        );
      }
      for (var i = 0; i < 4; i++) {
        final time = DateTime.fromMillisecondsSinceEpoch(
          ((start + (end - start) * i / 3) * 1000).round(),
        );
        label(
          '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}',
          Offset(left + (size.width - left - 26) * i / 3, size.height - 12),
        );
      }
    }
    canvas.save();
    canvas.translate(left, 0);
    size = Size(size.width - left, size.height - bottom);
    final grid = Paint()
      ..color = const Color(0xFF2D506A)
      ..strokeWidth = .5;
    for (var i = 0; i < 4; i++) {
      final y = size.height * i / 3;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }
    for (final field in ['rx', 'tx']) {
      final paint = Paint()
        ..color = field == 'rx'
            ? const Color(0xFF00D9D0)
            : const Color(0xFFB29BFF)
        ..strokeWidth = 1.8
        ..style = PaintingStyle.stroke;
      for (final samples in series) {
        final path = Path();
        double? previous;
        for (final point in samples) {
          final at = (point['at'] as num).toDouble();
          final value = point[field] as num?;
          if (value == null) {
            previous = null;
            continue;
          }
          final x = (at - start) / math.max(1, end - start) * size.width;
          final y = size.height * (1 - value / peak);
          if (previous == null || at - previous > maxGap) {
            path.moveTo(x, y);
          } else {
            path.lineTo(x, y);
          }
          previous = at;
        }
        canvas.drawPath(path, paint);
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(RatePainter oldDelegate) => oldDelegate.series != series;
}
