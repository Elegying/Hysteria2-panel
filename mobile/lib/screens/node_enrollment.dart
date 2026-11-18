import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';

Future<void> showNodeEnrollment(BuildContext context, WidgetRef ref) async {
  try {
    final capabilities = await ref
        .read(appControllerProvider.notifier)
        .getJson('/api/v1/mobile/capabilities');
    if (!context.mounted) return;
    if (!(capabilities['features'] as List? ?? []).contains(
      'typed-node-enrollment-hopping',
    )) {
      await showGlassError(context, '请先升级面板移动接口，以支持节点类型和端口跳跃对接');
      return;
    }
  } on ApiException catch (error) {
    if (context.mounted) await showGlassError(context, error.message);
    return;
  }
  if (!context.mounted) return;
  final name = TextEditingController();
  final expectedIp = TextEditingController();
  final host = TextEditingController();
  var tier = 'standard';
  var region = 'hk';
  var hopping = true;
  var submitting = false;
  String? formError;
  final result = await showGlassFormDialog<Map<String, dynamic>>(
    context: context,
    builder: (dialogContext) => StatefulBuilder(
      builder: (context, setDialogState) => GlassDialog(
        title: const Text('对接新节点'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('生成前请先自行把需要的域名解析到目标服务器公网 IP。面板不会查询、修改或等待 DNS。'),
              const SizedBox(height: 16),
              GlassControlSurface(
                child: TextField(
                  controller: name,
                  decoration: const InputDecoration(labelText: '节点名称'),
                ),
              ),
              const SizedBox(height: 12),
              GlassControlSurface(
                child: TextField(
                  controller: expectedIp,
                  decoration: const InputDecoration(labelText: '目标服务器公网 IP'),
                ),
              ),
              GlassDropdownField<String>(
                initialValue: tier,
                decoration: const InputDecoration(labelText: '节点类型'),
                items: const [
                  DropdownMenuItem(value: 'standard', child: Text('普通节点')),
                  DropdownMenuItem(value: 'premium', child: Text('专线节点')),
                ],
                onChanged: (v) => setDialogState(() => tier = v!),
              ),
              GlassDropdownField<String>(
                initialValue: region,
                decoration: const InputDecoration(labelText: '地区'),
                items: const [
                  DropdownMenuItem(value: 'hk', child: Text('香港')),
                  DropdownMenuItem(value: 'us', child: Text('美国')),
                  DropdownMenuItem(value: 'jp', child: Text('日本')),
                  DropdownMenuItem(value: 'sg', child: Text('新加坡')),
                ],
                onChanged: (v) => setDialogState(() => region = v!),
              ),
              TextField(
                controller: host,
                decoration: const InputDecoration(
                  labelText: '订阅节点地址',
                  hintText: '例如 node.example.com',
                ),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('端口跳跃'),
                subtitle: const Text('端口由面板统一配置，无需手动填写'),
                value: hopping,
                onChanged: (v) => setDialogState(() => hopping = v),
              ),
              if (formError != null)
                Text(
                  formError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
            ],
          ),
        ),
        actions: [
          GlassControlSurface(
            child: TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
          ),
          GlassControlSurface(
            child: FilledButton(
              onPressed: submitting
                  ? null
                  : () async {
                      if (submitting) return;
                      if (name.text.trim().isEmpty ||
                          expectedIp.text.trim().isEmpty ||
                          host.text.trim().isEmpty) {
                        setDialogState(
                          () => formError = '请填写节点名称、订阅地址和目标服务器公网 IP',
                        );
                        return;
                      }
                      setDialogState(() {
                        submitting = true;
                        formError = null;
                      });
                      try {
                        final data = await ref
                            .read(appControllerProvider.notifier)
                            .postJson('/api/v1/mobile/node-enrollments', {
                              'name': name.text.trim(),
                              'expectedIp': expectedIp.text.trim(),
                              'tier': tier,
                              'region': region,
                              'subscriptionHost': host.text.trim(),
                              'portHopping': hopping,
                              'ttlMinutes': 10,
                              'mode': 'join',
                            });
                        if (dialogContext.mounted &&
                            ModalRoute.of(dialogContext)?.isCurrent == true) {
                          Navigator.pop(dialogContext, data);
                        }
                      } on ApiException catch (error) {
                        if (dialogContext.mounted &&
                            ModalRoute.of(dialogContext)?.isCurrent == true) {
                          setDialogState(() {
                            submitting = false;
                            formError = error.message;
                          });
                        }
                      }
                    },
              child: Text(submitting ? '生成中…' : '一键对接'),
            ),
          ),
        ],
      ),
    ),
  );
  name.dispose();
  expectedIp.dispose();
  host.dispose();
  if (result == null || !context.mounted) return;
  final command = result['deploymentCommand']?.toString() ?? '';
  var copied = false;
  try {
    await Clipboard.setData(ClipboardData(text: command));
    copied = true;
  } on PlatformException {
    // The enrollment has already been created. Always expose its result.
  }
  if (!context.mounted) return;
  await showDialog<void>(
    context: context,
    builder: (context) => StatefulBuilder(
      builder: (context, setResultState) => GlassDialog(
        title: const Text('部署代码已生成'),
        content: SizedBox(
          width: 620,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  copied
                      ? '代码已复制。请在目标服务器以 root 粘贴运行；短时授权只能使用一次。'
                      : '自动复制失败。请手动选择下方代码，或重试复制；短时授权只能使用一次。',
                ),
                const SizedBox(height: 12),
                SelectableText(
                  command,
                  style: Theme.of(context).textTheme.bodySmall
                      ?.copyWith(fontFamily: 'monospace'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          GlassControlSurface(
            child: TextButton(
              onPressed: () async {
                var succeeded = false;
                try {
                  await Clipboard.setData(ClipboardData(text: command));
                  succeeded = true;
                } on PlatformException {
                  // Keep the selectable command available for manual copying.
                }
                if (context.mounted) setResultState(() => copied = succeeded);
              },
              child: Text(copied ? '再次复制' : '重试复制'),
            ),
          ),
          GlassControlSurface(
            child: TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('关闭'),
            ),
          ),
        ],
      ),
    ),
  );
}
