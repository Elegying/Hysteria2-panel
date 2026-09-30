import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';
import '../core/glass.dart';

/// A single bounded month, fetched only on entry or explicit refresh.
class UserTrafficHistoryScreen extends ConsumerStatefulWidget {
  const UserTrafficHistoryScreen({
    required this.userId,
    required this.userName,
    super.key,
  });

  final int userId;
  final String userName;

  @override
  ConsumerState<UserTrafficHistoryScreen> createState() =>
      _UserTrafficHistoryScreenState();
}

class _UserTrafficHistoryScreenState
    extends ConsumerState<UserTrafficHistoryScreen> {
  Map<String, dynamic>? _data;
  List<Map<String, dynamic>> _days = [];
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  bool _validNumber(Object? value) =>
      value is num && value.isFinite && value >= 0;

  Future<void> _load() async {
    if (!mounted || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/users/${widget.userId}/traffic-history');
      final days = (data['days'] as List)
          .map((day) => Map<String, dynamic>.from(day as Map))
          .toList();
      if (data['userId'] != widget.userId ||
          days.length > 31 ||
          data['timezone'] != 'Asia/Shanghai' ||
          !_validNumber(data['totalBytes']) ||
          data['month'] is! String) {
        throw const FormatException();
      }
      for (final day in days) {
        if (day['date'] is! String ||
            !_validNumber(day['totalBytes']) ||
            !_validNumber(day['percent']) ||
            day['percent'] > 100 ||
            (day['hours'] as List).length != 24) {
          throw const FormatException();
        }
        for (final hour in day['hours'] as List) {
          if (hour is! Map ||
              hour['hour'] is! int ||
              hour['hour'] < 0 ||
              hour['hour'] > 23 ||
              !_validNumber(hour['totalBytes']) ||
              !_validNumber(hour['percent']) ||
              hour['percent'] > 100) {
            throw const FormatException();
          }
        }
      }
      if (mounted) {
        setState(() {
          _data = data;
          _days = days;
        });
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(
          () => _error = error.statusCode == 404
              ? '用户已不存在，或面板尚未支持流量历史。请确认用户并升级面板至 v0.39.32 或更新版本。'
              : error.message,
        );
      }
    } catch (_) {
      if (mounted) setState(() => _error = '流量数据暂时无法读取，请稍后重试');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverAppBar(
                leading: const GlassControlSurface(child: BackButton()),
                title: const Text('流量记录'),
                actions: [
                  GlassControlSurface(
                    child: IconButton(
                      onPressed: _loading ? null : _load,
                      tooltip: '刷新流量记录',
                      icon: const Icon(Icons.refresh_rounded),
                    ),
                  ),
                ],
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                sliver: SliverList.list(
                  children: [
                    GlassCard(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              widget.userName,
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const SizedBox(height: 8),
                            Text('${_data?['month'] ?? '本月'} · 已记录流量'),
                            const SizedBox(height: 4),
                            Text(
                              _data == null
                                  ? '—'
                                  : formatBytes(_data!['totalBytes']),
                              style: Theme.of(context).textTheme.headlineMedium
                                  ?.copyWith(
                                    color: trafficHistoryColor(context),
                                    fontWeight: FontWeight.w800,
                                  ),
                            ),
                            const SizedBox(height: 12),
                            const Text('上传＋下载 · 北京时间\n仅保留本月记录，每月 1 日清理'),
                          ],
                        ),
                      ),
                    ),
                    if (_loading)
                      const Padding(
                        padding: EdgeInsets.all(16),
                        child: Center(
                          child: CircularProgressIndicator(
                            semanticsLabel: '正在读取流量记录',
                          ),
                        ),
                      ),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: GlassCard(
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(_error!, semanticsLabel: '读取失败，$_error'),
                                if (_data != null) const Text('以下保留上次读取的记录'),
                                GlassControlSurface(
                                  child: TextButton.icon(
                                    onPressed: _loading ? null : _load,
                                    icon: const Icon(Icons.refresh_rounded),
                                    label: const Text('重试'),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    if (_data != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        '每日用量',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '占比为当天占本月，点开日期查看小时用量。',
                        style: TextStyle(color: colors.onSurfaceVariant),
                      ),
                      if ((_data!['totalBytes'] as num) == 0)
                        const Padding(
                          padding: EdgeInsets.only(top: 12),
                          child: Text('本月暂无流量记录'),
                        ),
                      const Padding(
                        padding: EdgeInsets.only(top: 8),
                        child: Text('仅显示功能启用后采集的记录，无记录不代表此前未使用。'),
                      ),
                    ],
                  ],
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                sliver: GlassSliverList(
                  itemCount: _days.length,
                  itemBuilder: (context, index) => _TrafficDay(
                    key: ValueKey(_days[index]['date']),
                    day: _days[index],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Color trafficHistoryColor(BuildContext context) =>
    Theme.of(context).brightness == Brightness.dark
    ? const Color(0xFF58DBA5)
    : const Color(0xFF087844);

class _TrafficDay extends StatefulWidget {
  const _TrafficDay({required this.day, super.key});
  final Map<String, dynamic> day;
  @override
  State<_TrafficDay> createState() => _TrafficDayState();
}

class _TrafficDayState extends State<_TrafficDay> {
  bool _expanded = false;
  Widget _hourRow(BuildContext context, Map hour) {
    final label = Text(
      '${hour['hour'].toString().padLeft(2, '0')}:00–${(hour['hour'] + 1).toString().padLeft(2, '0')}:00',
    );
    final amount = Text(
      formatBytes(hour['totalBytes']),
      textAlign: TextAlign.right,
      style: TextStyle(
        fontWeight: FontWeight.w700,
        color: trafficHistoryColor(context),
      ),
    );
    final percent = Text(
      '${(hour['percent'] as num).toStringAsFixed(1)}%',
      textAlign: TextAlign.right,
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        if (MediaQuery.textScalerOf(context).scale(14) > 21 ||
            constraints.maxWidth < 280) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              label,
              const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(child: amount),
                  const SizedBox(width: 16),
                  percent,
                ],
              ),
            ],
          );
        }
        return Row(
          children: [
            Expanded(flex: 5, child: label),
            Expanded(flex: 3, child: amount),
            const SizedBox(width: 8),
            Expanded(flex: 2, child: percent),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final day = widget.day;
    final percent = (day['percent'] as num).toDouble().clamp(0.0, 100.0);
    return GlassCard(
      child: ExpansionTile(
        onExpansionChanged: (value) => setState(() => _expanded = value),
        tilePadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 6),
        childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 16),
        title: Text(day['date'].toString()),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 6),
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: [
                Text(
                  formatBytes(day['totalBytes']),
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                    color: trafficHistoryColor(context),
                  ),
                ),
                Text('${percent.toStringAsFixed(1)}%'),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(
              value: percent / 100,
              color: trafficHistoryColor(context),
              minHeight: 3,
              semanticsLabel: '占本月流量',
              semanticsValue: '${percent.toStringAsFixed(1)}%',
            ),
            if (day['hasRecords'] != true) const Text('暂无采集记录'),
          ],
        ),
        children: _expanded
            ? [
                const Divider(),
                const Align(
                  alignment: Alignment.centerLeft,
                  child: Text('小时用量 · 占当天比例'),
                ),
                const SizedBox(height: 8),
                for (final hour in day['hours'] as List)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 9),
                    child: _hourRow(context, hour as Map),
                  ),
              ]
            : const [],
      ),
    );
  }
}
