import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/app_controller.dart';
import '../core/theme_controller.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen>
    with AutomaticKeepAliveClientMixin {
  PackageInfo? _packageInfo;
  bool _checking = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    PackageInfo.fromPlatform().then((value) {
      if (mounted) setState(() => _packageInfo = value);
    });
  }

  Future<void> _checkUpdate() async {
    setState(() => _checking = true);
    try {
      final packageInfo = _packageInfo ?? await PackageInfo.fromPlatform();
      final response =
          await Dio(
            BaseOptions(
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 15),
              headers: const {
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
              },
            ),
          ).get(
            'https://api.github.com/repos/Elegying/Hysteria2-panel/releases?per_page=30',
          );
      final releases = response.data as List? ?? const [];
      _ReleaseApk? latest;
      final pattern = RegExp(
        r'^Hysteria2-Manager-v(\d+\.\d+\.\d+)\.apk$',
        caseSensitive: false,
      );
      for (final rawRelease in releases) {
        final release = Map<String, dynamic>.from(rawRelease as Map);
        if (release['draft'] == true || release['prerelease'] == true) continue;
        for (final rawAsset in release['assets'] as List? ?? const []) {
          final asset = Map<String, dynamic>.from(rawAsset as Map);
          final match = pattern.firstMatch(asset['name']?.toString() ?? '');
          if (match == null) continue;
          final candidate = _ReleaseApk(
            version: match.group(1)!,
            url: asset['browser_download_url'].toString(),
          );
          if (latest == null ||
              _compare(candidate.version, latest.version) > 0) {
            latest = candidate;
          }
        }
      }
      if (!mounted) return;
      final current = packageInfo.version;
      if (latest == null) {
        await _showMessage(
          '当前为内部测试版',
          'GitHub 暂时没有可用的 Android 正式版 APK。当前安装版本：v$current。',
        );
      } else if (_compare(latest.version, current) <= 0) {
        await _showMessage('已是最新版本', '当前版本 v$current 已经是最新版本。');
      } else {
        await showDialog<void>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('发现新版本'),
            content: Text(
              '当前版本 v$current，可更新到 v${latest!.version}。下载后请直接覆盖安装，固定签名会保留应用数据。',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('稍后'),
              ),
              FilledButton.icon(
                onPressed: () async {
                  final url = Uri.parse(latest!.url);
                  await launchUrl(url, mode: LaunchMode.externalApplication);
                  if (context.mounted) Navigator.pop(context);
                },
                icon: const Icon(Icons.download_rounded),
                label: const Text('下载 APK'),
              ),
            ],
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        await _showMessage('检查失败', '暂时无法连接 GitHub，请稍后重试。');
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  static int _compare(String a, String b) {
    final left = a.split('.').map(int.parse).toList();
    final right = b.split('.').map(int.parse).toList();
    for (var index = 0; index < 3; index++) {
      final value = left[index].compareTo(right[index]);
      if (value != 0) return value;
    }
    return 0;
  }

  Future<void> _showMessage(String title, String body) => showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(body),
      actions: [
        FilledButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('知道了'),
        ),
      ],
    ),
  );

  Future<void> _logout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('退出登录'),
        content: const Text('退出后会撤销当前手机的设备会话，需要重新输入面板账号和密码。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('退出登录'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(appControllerProvider.notifier).logout();
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final session = ref.watch(appControllerProvider).session;
    final settings = ref.watch(themeControllerProvider);
    final themeController = ref.read(themeControllerProvider.notifier);
    const colors = [
      Color(0xFF5F91F7),
      Color(0xFF25B99A),
      Color(0xFF8B72E8),
      Color(0xFFF09A44),
      Color(0xFFE45D86),
    ];
    return SafeArea(
      child: CustomScrollView(
        slivers: [
          const SliverAppBar(pinned: true, title: Text('设置')),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
            sliver: SliverList.list(
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Row(
                      children: [
                        SvgPicture.asset(
                          'assets/h2-icon.svg',
                          width: 58,
                          height: 58,
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Hysteria2管理',
                                style: Theme.of(context).textTheme.titleLarge
                                    ?.copyWith(fontWeight: FontWeight.w800),
                              ),
                              Text(
                                _packageInfo == null
                                    ? 'Android 版本读取中'
                                    : 'Android v${_packageInfo!.version} (${_packageInfo!.buildNumber})',
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                Card(
                  child: Column(
                    children: [
                      ListTile(
                        leading: const Icon(Icons.account_circle_outlined),
                        title: Text(session?.username ?? '未知管理员'),
                        subtitle: Text(session?.baseUrl ?? '未连接面板'),
                      ),
                      const Divider(height: 1),
                      ListTile(
                        leading: _checking
                            ? const SizedBox.square(
                                dimension: 24,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.system_update_alt_rounded),
                        title: const Text('检查 App 更新'),
                        subtitle: const Text('从 GitHub 获取固定签名的新版本 APK'),
                        trailing: const Icon(Icons.chevron_right_rounded),
                        onTap: _checking ? null : _checkUpdate,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '界面颜色',
                          style: Theme.of(context).textTheme.titleLarge
                              ?.copyWith(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          '主题模式',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        const SizedBox(height: 10),
                        SegmentedButton<ThemeMode>(
                          segments: const [
                            ButtonSegment(
                              value: ThemeMode.system,
                              icon: Icon(Icons.brightness_auto_rounded),
                              label: Text('跟随系统'),
                            ),
                            ButtonSegment(
                              value: ThemeMode.light,
                              icon: Icon(Icons.light_mode_rounded),
                              label: Text('浅色'),
                            ),
                            ButtonSegment(
                              value: ThemeMode.dark,
                              icon: Icon(Icons.dark_mode_rounded),
                              label: Text('深色'),
                            ),
                          ],
                          selected: {settings.mode},
                          showSelectedIcon: false,
                          onSelectionChanged: (value) =>
                              themeController.setMode(value.first),
                        ),
                        const SizedBox(height: 18),
                        Text(
                          '强调色',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          children: colors
                              .map(
                                (color) => Semantics(
                                  button: true,
                                  selected:
                                      settings.seedValue == color.toARGB32(),
                                  label: '选择界面强调色',
                                  child: InkWell(
                                    onTap: () => themeController.setSeed(color),
                                    borderRadius: BorderRadius.circular(999),
                                    child: Container(
                                      width: 44,
                                      height: 44,
                                      decoration: BoxDecoration(
                                        color: color,
                                        shape: BoxShape.circle,
                                        border: Border.all(
                                          color:
                                              settings.seedValue ==
                                                  color.toARGB32()
                                              ? Theme.of(context)
                                                    .colorScheme
                                                    .onSurface
                                              : Colors.transparent,
                                          width: 3,
                                        ),
                                      ),
                                      child:
                                          settings.seedValue == color.toARGB32()
                                          ? const Icon(
                                              Icons.check_rounded,
                                              color: Colors.white,
                                            )
                                          : null,
                                    ),
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                OutlinedButton.icon(
                  onPressed: _logout,
                  icon: Icon(
                    Icons.logout_rounded,
                    color: Theme.of(context).colorScheme.error,
                  ),
                  label: Text(
                    '退出登录',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReleaseApk {
  const _ReleaseApk({required this.version, required this.url});
  final String version;
  final String url;
}
