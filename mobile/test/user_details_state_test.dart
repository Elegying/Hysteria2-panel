import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';

class DetailsController extends AppController {
  bool enabled = false;
  bool exists = true;
  int generation = 0;
  int reads = 0;
  final writes = <Map<String, dynamic>>[];
  Completer<Map<String, dynamic>> pending = Completer();

  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    reads++;
    return {
      'items': [
        if (exists)
          {
            'id': 1,
            'name': 'details-user',
            'enabled': enabled,
            'generation': generation,
            'deviceLimit': 3,
            'trafficLimitBytes': 5 * 1073741824,
            'allowUdp443': false,
            'onlineDevices': 0,
            'usedBytes': 0,
            'txBytes': 0,
            'rxBytes': 0,
          },
      ],
    };
  }

  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) {
    writes.add({'path': path, ...data});
    return pending.future;
  }

  @override
  Future<Map<String, dynamic>> deleteJson(
    String path,
    Map<String, dynamic> data,
  ) => postJson(path, data);
}

Future<void> openDetails(
  WidgetTester tester,
  DetailsController controller,
) async {
  tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [appControllerProvider.overrideWith((ref) => controller)],
      child: const MaterialApp(home: Scaffold(body: UsersScreen())),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text('details-user').first);
  await tester.pumpAndSettle();
}

Future<void> refresh(WidgetTester tester) async {
  tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
  tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
  await tester.pumpAndSettle();
}

void main() {
  for (final action in ['启用', '禁用', '重置', '改密', '删除']) {
    testWidgets(
      '$action blocks repeated writes and permits retry after failure',
      (tester) async {
        final controller = DetailsController()..enabled = action == '禁用';
        await openDetails(tester, controller);
        final button = find.widgetWithText(ActionChip, action);
        await tester.ensureVisible(button);
        await tester.tap(button);
        await tester.pumpAndSettle();
        if (action != '启用') {
          await tester.tap(find.widgetWithText(FilledButton, '确认'));
          await tester.pumpAndSettle();
        }
        expect(controller.writes, hasLength(1));
        expect(tester.widget<ActionChip>(button).onPressed, isNull);
        await tester.tap(button);
        await tester.pump();
        expect(controller.writes, hasLength(1));
        expect(find.text('正在处理，请稍候…'), findsOneWidget);
        controller.pending.completeError(const ApiException('操作失败，请重试'));
        await tester.pumpAndSettle();
        expect(find.text('操作失败，请重试').hitTestable(), findsOneWidget);
        // Dismiss the error route before checking the restored operation.
        Navigator.of(tester.element(find.text('操作失败，请重试'))).pop();
        await tester.pumpAndSettle();
        expect(tester.widget<ActionChip>(button).onPressed, isNotNull);
        await tester.pumpWidget(const SizedBox.shrink());
      },
    );
  }

  testWidgets('details refresh status and submit the current generation', (
    tester,
  ) async {
    final controller = DetailsController();
    await openDetails(tester, controller);
    final reads = controller.reads;
    controller.enabled = true;
    controller.generation = 9;
    await refresh(tester);
    expect(controller.reads, greaterThan(reads));
    expect(find.widgetWithText(ActionChip, '启用'), findsNothing);
    await tester.tap(find.widgetWithText(ActionChip, '禁用'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, '取消'));
    await tester.pumpAndSettle();
    expect(controller.writes, isEmpty);
    await tester.tap(find.widgetWithText(ActionChip, '禁用'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '确认'));
    await tester.pumpAndSettle();
    expect(controller.writes.single['generation'], 9);
    controller.pending.complete({});
    await tester.pumpAndSettle();
    expect(find.widgetWithText(ActionChip, '禁用'), findsNothing);
    expect(find.text('操作已完成'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
    'deleted account replaces stale detail actions with a close action',
    (tester) async {
      final controller = DetailsController();
      await openDetails(tester, controller);
      controller.exists = false;
      await refresh(tester);
      expect(find.text('此用户已从面板删除。'), findsOneWidget);
      expect(find.byType(ActionChip), findsNothing);
      await tester.tap(find.text('关闭详情'));
      await tester.pumpAndSettle();
      expect(find.text('此用户已从面板删除。'), findsNothing);
      expect(controller.writes, isEmpty);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('refresh keeps unsaved user form input', (tester) async {
    final controller = DetailsController();
    await openDetails(tester, controller);
    await tester.tap(find.widgetWithText(ActionChip, '编辑'));
    await tester.pumpAndSettle();
    final field = find.byWidgetPredicate(
      (widget) =>
          widget is TextField && widget.decoration?.labelText == '设备数限制',
    );
    await tester.enterText(field, '7');
    controller.generation = 2;
    await refresh(tester);
    expect(tester.widget<TextField>(field).controller!.text, '7');
    await tester.tap(find.widgetWithText(TextButton, '取消'));
    await tester.pumpAndSettle();
    expect(controller.writes, isEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
