import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';

class BackupControls extends ConsumerStatefulWidget {
  const BackupControls({super.key});
  @override
  ConsumerState<BackupControls> createState() => _BackupState();
}

class _BackupState extends ConsumerState<BackupControls> {
  bool _busy = false;
  String? _message;
  Future<void> _run(bool restore) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    File? file;
    try {
      final controller = ref.read(appControllerProvider.notifier);
      if (restore) {
        final path = await const MethodChannel('hy2/files')
            .invokeMethod<String>('pickBackup');
        if (!mounted || path == null) return;
        file = File(path);
        final approved = await showDialog<bool>(
          context: context,
          builder: (context) => GlassDialog(
            title: const Text('恢复面板备份'),
            content: const Text('恢复会替换面板数据并使当前登录失效。确认使用所选 ZIP 备份？'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('恢复'),
              ),
            ],
          ),
        );
        if (!mounted || approved != true) return;
        await controller.restoreBackup(file);
        if (mounted) setState(() => _message = '恢复已受理，请稍后重新登录并核对数据');
      } else {
        file = await controller.downloadBackup();
        if (!mounted) return;
        await SharePlus.instance.share(
          ShareParams(files: [XFile(file.path)], text: '面板备份'),
        );
        if (mounted) setState(() => _message = '备份已下载，请在分享窗口选择保存位置');
      }
    } catch (e) {
      if (mounted) setState(() => _message = '操作失败：$e');
    } finally {
      if (file != null) {
        try {
          if (await file.exists()) await file.delete();
          if (!restore &&
              file.parent.path
                  .split(Platform.pathSeparator)
                  .last
                  .startsWith('hy2-backup-')) {
            await file.parent.delete();
          }
        } catch (_) {
          /* A cache cleanup error must not mask the operation result. */
        }
      }
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => GlassCard(
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('备份与恢复', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          ActionGrid(
            children: [
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF00E1DF),
                  side: const BorderSide(color: Color(0xFF00E1DF)),
                ),
                onPressed: _busy ? null : () => _run(false),
                child: const Text('下载备份'),
              ),
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFFBC9BEF),
                  side: const BorderSide(color: Color(0xFFBC9BEF)),
                ),
                onPressed: _busy ? null : () => _run(true),
                child: const Text('上传恢复'),
              ),
            ],
          ),
          if (_busy) const LinearProgressIndicator(),
          if (_message != null) Text(_message!),
        ],
      ),
    ),
  );
}
