import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import 'login_screen.dart';

/// The same two slots remain reachable on the home and login screens.
class PanelSwitcher extends ConsumerWidget {
  const PanelSwitcher({super.key});

  Future<void> _run(
    BuildContext context,
    Future<void> Function() action,
  ) async {
    try {
      await action();
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> _rename(BuildContext context, WidgetRef ref, int index) async {
    final name = await showDialog<String>(
      context: context,
      builder: (_) => _PanelNameDialog(
        name: ref.read(appControllerProvider).panels[index].name,
      ),
    );
    if (name != null && context.mounted) {
      await _run(
        context,
        () => ref.read(appControllerProvider.notifier).renamePanel(index, name),
      );
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, int index) async {
    final name = ref.read(appControllerProvider).panels[index].name;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('删除$name的登录信息？'),
        content: const Text('删除本机保存的地址、账号、密码并退出此面板。不会删除服务器上的用户、节点或设置。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed == true && context.mounted) {
      await _run(
        context,
        () => ref.read(appControllerProvider.notifier).forgetPanel(index),
      );
    }
  }

  Future<void> _menu(BuildContext context, WidgetRef ref, int index) async {
    final panel = ref.read(appControllerProvider).panels[index];
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(title: Text(panel.name)),
            for (final item in [
              ('rename', '重命名'),
              ('login', '登录 / 更换账号'),
              if (panel.baseUrl.isNotEmpty) ('delete', '删除登录记忆'),
            ])
              ListTile(
                title: Text(item.$2),
                onTap: () => Navigator.pop(context, item.$1),
              ),
          ],
        ),
      ),
    );
    if (!context.mounted) return;
    if (action == 'rename') return _rename(context, ref, index);
    if (action == 'delete') return _delete(context, ref, index);
    if (action == 'login') {
      await Navigator.of(context).push<void>(
        MaterialPageRoute(builder: (_) => LoginScreen(panelIndex: index)),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appControllerProvider);
    return Row(
      children: [
        for (var index = 0; index < 2; index++) ...[
          if (index > 0) const SizedBox(width: 8),
          Expanded(
            child: Semantics(
              selected: state.activePanel == index,
              hint: '长按管理面板',
              child: OutlinedButton(
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(0, 48),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 8,
                  ),
                  backgroundColor: state.activePanel == index
                      ? Theme.of(context).colorScheme.primaryContainer
                      : null,
                ),
                onLongPress: state.working
                    ? null
                    : () => _menu(context, ref, index),
                onPressed: state.working
                    ? null
                    : () => _run(context, () async {
                        if (index == state.activePanel) return;
                        if (state.panels[index].session == null &&
                            state.session != null) {
                          await Navigator.of(context).push<void>(
                            MaterialPageRoute(
                              builder: (_) => LoginScreen(panelIndex: index),
                            ),
                          );
                        } else {
                          await ref
                              .read(appControllerProvider.notifier)
                              .selectPanel(index);
                        }
                      }),
                child: Text(
                  state.panels[index].name,
                  style: Theme.of(context).textTheme.labelMedium,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _PanelNameDialog extends StatefulWidget {
  const _PanelNameDialog({required this.name});
  final String name;
  @override
  State<_PanelNameDialog> createState() => _PanelNameDialogState();
}

class _PanelNameDialogState extends State<_PanelNameDialog> {
  late final _input = TextEditingController(text: widget.name);
  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  void _save() {
    if (_input.text.trim().isNotEmpty) Navigator.pop(context, _input.text);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('重命名面板'),
    content: TextField(
      controller: _input,
      autofocus: true,
      maxLength: 24,
      decoration: const InputDecoration(labelText: '面板名称'),
      onSubmitted: (_) => _save(),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('取消'),
      ),
      TextButton(onPressed: _save, child: const Text('保存')),
    ],
  );
}
