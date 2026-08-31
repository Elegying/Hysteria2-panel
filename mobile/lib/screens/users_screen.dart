import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:share_plus/share_plus.dart';

import '../core/app_controller.dart';
import '../core/formatters.dart';

class UsersScreen extends ConsumerStatefulWidget {
  const UsersScreen({super.key});

  @override
  ConsumerState<UsersScreen> createState() => _UsersScreenState();
}

class _UsersScreenState extends ConsumerState<UsersScreen>
    with WidgetsBindingObserver, AutomaticKeepAliveClientMixin {
  final _search = TextEditingController();
  List<Map<String, dynamic>> _users = [];
  String _status = 'all';
  String _sort = 'traffic';
  String? _error;
  bool _loading = true;
  Timer? _timer;

  @override
  bool get wantKeepAlive => true;

  List<Map<String, dynamic>> get _filtered {
    final query = _search.text.trim().toLowerCase();
    final values = _users.where((user) {
      final matchesQuery =
          query.isEmpty ||
          user['name'].toString().toLowerCase().contains(query);
      final enabled = user['enabled'] == true;
      final matchesStatus =
          _status == 'all' ||
          (_status == 'enabled' && enabled) ||
          (_status == 'disabled' && !enabled) ||
          (_status == 'online' && (user['onlineDevices'] as num? ?? 0) > 0);
      return matchesQuery && matchesStatus;
    }).toList();
    values.sort((a, b) {
      switch (_sort) {
        case 'name':
          return a['name'].toString().toLowerCase().compareTo(
            b['name'].toString().toLowerCase(),
          );
        case 'online':
          return (b['onlineDevices'] as num? ?? 0).compareTo(
            a['onlineDevices'] as num? ?? 0,
          );
        default:
          return (b['usedBytes'] as num? ?? 0).compareTo(
            a['usedBytes'] as num? ?? 0,
          );
      }
    });
    return values;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _search.addListener(_redraw);
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

  void _redraw() => setState(() {});

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _search.removeListener(_redraw);
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent && mounted) setState(() => _loading = true);
    try {
      final data = await ref
          .read(appControllerProvider.notifier)
          .getJson('/api/v1/mobile/users');
      final items = (data['items'] as List? ?? const [])
          .map((value) => Map<String, dynamic>.from(value as Map))
          .toList();
      if (mounted) {
        setState(() {
          _users = items;
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

  void _message(String value, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(value),
        backgroundColor: error ? Theme.of(context).colorScheme.error : null,
      ),
    );
  }

  Future<void> _createUser() async {
    final name = TextEditingController();
    final deviceLimit = TextEditingController(text: '3');
    final trafficLimit = TextEditingController(text: '250');
    var udp443 = false;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('新增用户'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: name,
                  decoration: const InputDecoration(labelText: '用户名'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: deviceLimit,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '设备数限制'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: trafficLimit,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '流量额度（GiB）'),
                ),
                const SizedBox(height: 8),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('允许 UDP 443'),
                  value: udp443,
                  onChanged: (value) => setDialogState(() => udp443 = value),
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
                final devices = int.tryParse(deviceLimit.text);
                final traffic = int.tryParse(trafficLimit.text);
                if (name.text.trim().isEmpty ||
                    devices == null ||
                    traffic == null) {
                  return;
                }
                try {
                  final data = await ref
                      .read(appControllerProvider.notifier)
                      .postJson('/api/v1/mobile/users', {
                        'name': name.text.trim(),
                        'deviceLimit': devices,
                        'trafficLimitGb': traffic,
                        'allowUdp443': udp443,
                      });
                  if (dialogContext.mounted) Navigator.pop(dialogContext, data);
                } on ApiException catch (error) {
                  if (dialogContext.mounted) {
                    ScaffoldMessenger.of(dialogContext)
                        .showSnackBar(SnackBar(content: Text(error.message)));
                  }
                }
              },
              child: const Text('创建'),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    deviceLimit.dispose();
    trafficLimit.dispose();
    if (result != null && mounted) {
      await _showCredentials(result, title: '用户已创建');
      await _load(silent: true);
    }
  }

  Future<void> _showUser(Map<String, dynamic> user) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(
            20,
            0,
            20,
            20 + MediaQuery.viewInsetsOf(sheetContext).bottom,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                user['name'].toString(),
                style: Theme.of(sheetContext).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 4),
              Text(user['enabled'] == true ? '启用中' : '已禁用'),
              const SizedBox(height: 18),
              _UserFacts(user: user),
              const SizedBox(height: 20),
              Text(
                '用户操作',
                style: Theme.of(sheetContext).textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _ActionChipButton(
                    icon: Icons.share_rounded,
                    label: '分享',
                    onTap: () => _userAction(sheetContext, user, 'share'),
                  ),
                  _ActionChipButton(
                    icon: Icons.qr_code_rounded,
                    label: '二维码',
                    onTap: () => _userAction(sheetContext, user, 'qr'),
                  ),
                  _ActionChipButton(
                    icon: user['enabled'] == true
                        ? Icons.block_rounded
                        : Icons.check_circle_rounded,
                    label: user['enabled'] == true ? '禁用' : '启用',
                    onTap: () => _userAction(
                      sheetContext,
                      user,
                      user['enabled'] == true ? 'disable' : 'enable',
                    ),
                  ),
                  _ActionChipButton(
                    icon: Icons.password_rounded,
                    label: '改密',
                    onTap: () =>
                        _userAction(sheetContext, user, 'rotate-secret'),
                  ),
                  _ActionChipButton(
                    icon: Icons.restart_alt_rounded,
                    label: '重置',
                    onTap: () =>
                        _userAction(sheetContext, user, 'reset-traffic'),
                  ),
                  _ActionChipButton(
                    icon: Icons.edit_rounded,
                    label: '编辑',
                    onTap: () => _editUser(sheetContext, user),
                  ),
                  _ActionChipButton(
                    icon: Icons.delete_outline_rounded,
                    label: '删除',
                    destructive: true,
                    onTap: () => _userAction(sheetContext, user, 'delete'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<bool> _confirm(
    BuildContext context,
    String title,
    String message, {
    bool destructive = false,
  }) async {
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(title),
            content: Text(message),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('取消'),
              ),
              FilledButton(
                style: destructive
                    ? FilledButton.styleFrom(
                        backgroundColor: Theme.of(context).colorScheme.error,
                      )
                    : null,
                onPressed: () => Navigator.pop(context, true),
                child: const Text('确认'),
              ),
            ],
          ),
        ) ??
        false;
  }

  Future<void> _userAction(
    BuildContext sheetContext,
    Map<String, dynamic> user,
    String action,
  ) async {
    final userId = user['id'];
    final generation = user['generation'];
    if (action == 'delete') {
      final confirmed = await _confirm(
        sheetContext,
        '删除 ${user['name']}',
        '删除后该用户会立即失效，已有连接也会被断开。此操作无法撤销。',
        destructive: true,
      );
      if (!confirmed) return;
    } else if (action == 'rotate-secret') {
      final confirmed = await _confirm(
        sheetContext,
        '修改认证密钥',
        '改密后旧连接地址会立即失效，必须把新地址重新发给用户。',
      );
      if (!confirmed) return;
    } else if (action == 'reset-traffic') {
      final confirmed = await _confirm(
        sheetContext,
        '重置用户流量',
        '将该用户的上传和下载统计归零，确认继续吗？',
      );
      if (!confirmed) return;
    } else if (action == 'disable') {
      final confirmed = await _confirm(
        sheetContext,
        '禁用用户',
        '禁用后该用户的当前连接会被断开。',
      );
      if (!confirmed) return;
    }
    try {
      final controller = ref.read(appControllerProvider.notifier);
      if (action == 'delete') {
        await controller.deleteJson('/api/v1/mobile/users/$userId', {
          'generation': generation,
        });
      } else {
        final endpoint = action == 'qr' ? 'share' : action;
        final data = await controller.postJson(
          '/api/v1/mobile/users/$userId/$endpoint',
          {'generation': generation},
        );
        if (action == 'share') {
          final uri = data['uri']?.toString() ?? '';
          await SharePlus.instance.share(
            ShareParams(text: uri, subject: '${user['name']} 的 Hysteria2 连接'),
          );
        } else if (action == 'qr') {
          if (sheetContext.mounted) await _showQr(sheetContext, data);
        } else if (action == 'rotate-secret') {
          if (sheetContext.mounted) {
            await _showCredentials(data, title: '认证密钥已更新');
          }
        }
      }
      if (action != 'share' && action != 'qr') {
        if (sheetContext.mounted) Navigator.pop(sheetContext);
        await _load(silent: true);
        if (mounted) _message('操作已完成');
      }
    } on ApiException catch (error) {
      if (mounted) _message(error.message, error: true);
    }
  }

  Future<void> _editUser(
    BuildContext sheetContext,
    Map<String, dynamic> user,
  ) async {
    final devices = TextEditingController(text: '${user['deviceLimit']}');
    final gib = ((user['trafficLimitBytes'] as num? ?? 0) / 1073741824).round();
    final traffic = TextEditingController(text: '$gib');
    var udp443 = user['allowUdp443'] == true;
    final saved = await showDialog<bool>(
      context: sheetContext,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('编辑 ${user['name']}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: devices,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: '设备数限制'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: traffic,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: '流量额度（GiB）'),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('允许 UDP 443'),
                value: udp443,
                onChanged: (value) => setDialogState(() => udp443 = value),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () async {
                try {
                  await ref.read(appControllerProvider.notifier).patchJson(
                    '/api/v1/mobile/users/${user['id']}',
                    {
                      'generation': user['generation'],
                      'deviceLimit': int.parse(devices.text),
                      'trafficLimitGb': int.parse(traffic.text),
                      'allowUdp443': udp443,
                    },
                  );
                  if (dialogContext.mounted) Navigator.pop(dialogContext, true);
                } on ApiException catch (error) {
                  if (dialogContext.mounted) {
                    ScaffoldMessenger.of(dialogContext)
                        .showSnackBar(SnackBar(content: Text(error.message)));
                  }
                }
              },
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
    devices.dispose();
    traffic.dispose();
    if (saved == true) {
      if (sheetContext.mounted) Navigator.pop(sheetContext);
      await _load(silent: true);
      if (mounted) _message('用户配置已保存');
    }
  }

  Future<void> _showCredentials(
    Map<String, dynamic> data, {
    required String title,
  }) {
    final uri = data['uri']?.toString() ?? '';
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('连接地址包含认证凭据，请只发送给受信任的人。'),
              const SizedBox(height: 14),
              SelectableText(uri),
              const SizedBox(height: 16),
              QrImageView(data: uri, size: 230, backgroundColor: Colors.white),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
          FilledButton.icon(
            onPressed: () => SharePlus.instance.share(ShareParams(text: uri)),
            icon: const Icon(Icons.share_rounded),
            label: const Text('分享'),
          ),
        ],
      ),
    );
  }

  Future<void> _showQr(BuildContext context, Map<String, dynamic> data) {
    final uri = data['uri']?.toString() ?? '';
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(data['name']?.toString() ?? '连接二维码'),
        content: QrImageView(
          data: uri,
          size: 260,
          backgroundColor: Colors.white,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final filtered = _filtered;
    final top = [..._users]
      ..sort(
        (a, b) => (b['usedBytes'] as num? ?? 0).compareTo(
          a['usedBytes'] as num? ?? 0,
        ),
      );
    return SafeArea(
      child: Scaffold(
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _createUser,
          icon: const Icon(Icons.person_add_alt_1_rounded),
          label: const Text('新增用户'),
        ),
        body: RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverAppBar(
                pinned: true,
                title: const Text('用户'),
                actions: [
                  IconButton(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh_rounded),
                    tooltip: '刷新',
                  ),
                ],
              ),
              if (_loading && _users.isEmpty)
                const SliverFillRemaining(
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null && _users.isEmpty)
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
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '高流量用户',
                          style: Theme.of(context).textTheme.titleLarge
                              ?.copyWith(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 9),
                        SizedBox(
                          height: 100,
                          child: top.isEmpty
                              ? const Card(child: Center(child: Text('暂无用户')))
                              : ListView.separated(
                                  scrollDirection: Axis.horizontal,
                                  itemCount: top.take(5).length,
                                  separatorBuilder: (_, _) =>
                                      const SizedBox(width: 9),
                                  itemBuilder: (context, index) {
                                    final user = top[index];
                                    return SizedBox(
                                      width: 190,
                                      child: Card(
                                        child: InkWell(
                                          borderRadius: BorderRadius.circular(
                                            18,
                                          ),
                                          onTap: () => _showUser(user),
                                          child: Padding(
                                            padding: const EdgeInsets.all(13),
                                            child: Column(
                                              crossAxisAlignment:
                                                  CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  '${index + 1}. ${user['name']}',
                                                  maxLines: 1,
                                                  overflow:
                                                      TextOverflow.ellipsis,
                                                  style: const TextStyle(
                                                    fontWeight: FontWeight.w800,
                                                  ),
                                                ),
                                                const Spacer(),
                                                Text(
                                                  formatBytes(
                                                    user['usedBytes'],
                                                  ),
                                                  style: Theme.of(context)
                                                      .textTheme
                                                      .titleMedium,
                                                ),
                                                Text(
                                                  '${(user['trafficPercent'] as num? ?? 0).toStringAsFixed(1)}% · ${user['onlineDevices']} 台在线',
                                                  style: Theme.of(context)
                                                      .textTheme
                                                      .bodySmall,
                                                ),
                                              ],
                                            ),
                                          ),
                                        ),
                                      ),
                                    );
                                  },
                                ),
                        ),
                        const SizedBox(height: 14),
                        TextField(
                          controller: _search,
                          decoration: InputDecoration(
                            hintText: '搜索用户名',
                            prefixIcon: const Icon(Icons.search_rounded),
                            suffixIcon: _search.text.isEmpty
                                ? null
                                : IconButton(
                                    onPressed: _search.clear,
                                    icon: const Icon(Icons.clear_rounded),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 9),
                        Row(
                          children: [
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                initialValue: _status,
                                decoration: const InputDecoration(
                                  labelText: '状态',
                                ),
                                items: const [
                                  DropdownMenuItem(
                                    value: 'all',
                                    child: Text('全部状态'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'enabled',
                                    child: Text('已启用'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'disabled',
                                    child: Text('已禁用'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'online',
                                    child: Text('当前在线'),
                                  ),
                                ],
                                onChanged: (value) =>
                                    setState(() => _status = value ?? 'all'),
                              ),
                            ),
                            const SizedBox(width: 9),
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                initialValue: _sort,
                                decoration: const InputDecoration(
                                  labelText: '排序',
                                ),
                                items: const [
                                  DropdownMenuItem(
                                    value: 'traffic',
                                    child: Text('流量降序'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'online',
                                    child: Text('在线设备'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'name',
                                    child: Text('用户名'),
                                  ),
                                ],
                                onChanged: (value) =>
                                    setState(() => _sort = value ?? 'traffic'),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Text(
                          '显示 ${filtered.length} / 全部 ${_users.length} 位用户',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ),
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
                  sliver: filtered.isEmpty
                      ? const SliverToBoxAdapter(
                          child: Card(
                            child: Padding(
                              padding: EdgeInsets.all(24),
                              child: Center(child: Text('没有符合条件的用户')),
                            ),
                          ),
                        )
                      : SliverList.separated(
                          itemCount: filtered.length,
                          separatorBuilder: (_, _) => const SizedBox(height: 8),
                          itemBuilder: (context, index) => _CompactUserCard(
                            user: filtered[index],
                            onTap: () => _showUser(filtered[index]),
                          ),
                        ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _CompactUserCard extends StatelessWidget {
  const _CompactUserCard({required this.user, required this.onTap});
  final Map<String, dynamic> user;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = user['enabled'] == true;
    final percent = (user['trafficPercent'] as num? ?? 0).toDouble();
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor: enabled
                    ? Colors.green.withValues(alpha: .14)
                    : Theme.of(context).colorScheme.errorContainer,
                child: Icon(
                  enabled ? Icons.person_rounded : Icons.person_off_rounded,
                  color: enabled
                      ? Colors.green
                      : Theme.of(context).colorScheme.error,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            user['name'].toString(),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                        ),
                        Text(
                          enabled ? '启用' : '禁用',
                          style: TextStyle(
                            color: enabled
                                ? Colors.green
                                : Theme.of(context).colorScheme.error,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '${user['onlineDevices']} / ${user['deviceLimit']} 台设备 · ${formatBytes(user['usedBytes'])} / ${formatBytes(user['trafficLimitBytes'])}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 6),
                    LinearProgressIndicator(value: (percent / 100).clamp(0, 1)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded),
            ],
          ),
        ),
      ),
    );
  }
}

class _UserFacts extends StatelessWidget {
  const _UserFacts({required this.user});
  final Map<String, dynamic> user;

  @override
  Widget build(BuildContext context) {
    final values = [
      ('在线设备', '${user['onlineDevices']} / ${user['deviceLimit']}'),
      ('上传流量', formatBytes(user['txBytes'])),
      ('下载流量', formatBytes(user['rxBytes'])),
      ('流量额度', formatBytes(user['trafficLimitBytes'])),
      ('UDP 443', user['allowUdp443'] == true ? '允许' : '禁止'),
      ('使用比例', '${(user['trafficPercent'] as num? ?? 0).toStringAsFixed(1)}%'),
    ];
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 2.25,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
      ),
      itemCount: values.length,
      itemBuilder: (context, index) => DecoratedBox(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest
              .withValues(alpha: .5),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.all(11),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                values[index].$1,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              Text(
                values[index].$2,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActionChipButton extends StatelessWidget {
  const _ActionChipButton({
    required this.icon,
    required this.label,
    required this.onTap,
    this.destructive = false,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool destructive;

  @override
  Widget build(BuildContext context) => ActionChip(
    avatar: Icon(
      icon,
      size: 18,
      color: destructive ? Theme.of(context).colorScheme.error : null,
    ),
    label: Text(
      label,
      style: TextStyle(
        color: destructive ? Theme.of(context).colorScheme.error : null,
      ),
    ),
    onPressed: onTap,
  );
}
