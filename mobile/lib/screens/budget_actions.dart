import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_controller.dart';
import '../core/glass.dart';

class BudgetActions extends ConsumerStatefulWidget {
  const BudgetActions({
    super.key,
    required this.originId,
    this.budget,
    this.resetLabel,
    this.extra,
  });
  final String originId;
  final String? resetLabel;
  final Widget? extra;
  final Map<String, dynamic>? budget;
  @override
  ConsumerState<BudgetActions> createState() => _BudgetState();
}

class _BudgetState extends ConsumerState<BudgetActions> {
  bool _busy = false;
  String? _message;
  Future<void> _run(bool edit) async {
    if (_busy) return;
    setState(() => _busy = true);
    final limit = TextEditingController(
      text:
          '${((widget.budget?['limitBytes'] as num? ?? 0) / 1073741824).round()}',
    );
    final warning = TextEditingController(
      text: '${widget.budget?['warningPercent'] ?? 80}',
    );
    final form = GlobalKey<FormState>();
    try {
      if (edit) {
        final approved = await showGlassFormDialog<bool>(
          context: context,
          builder: (context) => GlassDialog(
            title: const Text('编辑预算'),
            content: Form(
              key: form,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                spacing: 14,
                children: [
                  TextFormField(
                    controller: limit,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: '周期额度 GiB'),
                    validator: (v) =>
                        (int.tryParse(v ?? '') ?? -1) < 1 ? '请输入正整数' : null,
                  ),
                  TextFormField(
                    controller: warning,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: '预警百分比'),
                    validator: (v) {
                      final n = int.tryParse(v ?? '');
                      return n == null || n < 1 || n > 100 ? '请输入 1–100' : null;
                    },
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () {
                  if (form.currentState!.validate()) {
                    Navigator.pop(context, true);
                  }
                },
                child: const Text('保存'),
              ),
            ],
          ),
        );
        if (!mounted || approved != true) return;
      }
      await ref
          .read(appControllerProvider.notifier)
          .postJson(
            '/api/v1/mobile/usage-origins/${widget.originId}/${edit ? 'budget' : 'diagnostics'}',
            edit
                ? {
                    'limitGiB': int.parse(limit.text),
                    'warningPercent': int.parse(warning.text),
                  }
                : {},
          );
      if (mounted) {
        setState(() => _message = edit ? '预算已保存，下次刷新生效' : '检测已受理，请稍后刷新结果');
      }
    } catch (e) {
      if (mounted) setState(() => _message = e.toString());
    } finally {
      limit.dispose();
      warning.dispose();
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Wrap(
        spacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          if (widget.resetLabel != null)
            Text(widget.resetLabel!, style: const TextStyle(fontSize: 10)),
          TextButton(
            style: TextButton.styleFrom(
              minimumSize: const Size(0, 30),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              padding: const EdgeInsets.symmetric(horizontal: 8),
              textStyle: const TextStyle(fontSize: 11, fontFamily: 'Roboto'),
            ),
            onPressed: _busy ? null : () => _run(false),
            child: const Text('手动检测'),
          ),
          OutlinedButton(
            style: OutlinedButton.styleFrom(
              minimumSize: const Size(0, 30),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              padding: const EdgeInsets.symmetric(horizontal: 8),
              textStyle: const TextStyle(fontSize: 11, fontFamily: 'Roboto'),
            ),
            onPressed: _busy ? null : () => _run(true),
            child: const Text('编辑预算'),
          ),
          ?widget.extra,
        ],
      ),
      if (_busy) const LinearProgressIndicator(),
      if (_message != null) Text(_message!),
    ],
  );
}
