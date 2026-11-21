import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';

import 'user_details_state_test.dart' show DetailsController;

void main() {
  testWidgets(
    'inline disable refreshes the card without popping the main page',
    (tester) async {
      final controller = DetailsController()..enabled = true;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((_) => controller)],
          child: const MaterialApp(home: Scaffold(body: UsersScreen())),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('details-user'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('details-user'));
      await tester.pumpAndSettle();
      for (final label in [
        '复制订阅',
        '二维码',
        '禁用',
        '编辑',
        '改密',
        '重置',
        '删除',
        '订阅管理',
      ]) {
        expect(find.widgetWithText(OutlinedButton, label), findsOneWidget);
      }
      final disable = find.widgetWithText(OutlinedButton, '禁用');
      await tester.ensureVisible(disable);
      await tester.pumpAndSettle();
      await tester.pumpAndSettle();
      await tester.tap(disable);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '确认'));
      await tester.pump();
      expect(
        controller.writes.single['path'],
        '/api/v1/mobile/users/1/disable',
      );
      controller.enabled = false;
      controller.pending.complete({});
      await tester.pumpAndSettle();
      expect(find.byType(UsersScreen), findsOneWidget);
      expect(find.text('操作已完成'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, '启用'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
  testWidgets('expanded premium user copies its subscription without sharing', (
    tester,
  ) async {
    final controller = DetailsController()..userType = 1;
    const url = 'https://example.invalid/subscription/test';
    controller.pending.complete({'uri': url});
    String? copied;
    final messenger = tester.binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String;
      }
      return null;
    });
    addTearDown(
      () => messenger.setMockMethodCallHandler(SystemChannels.platform, null),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((_) => controller)],
        child: const MaterialApp(home: Scaffold(body: UsersScreen())),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('专线用户'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('details-user'));
    await tester.tap(find.text('details-user'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(OutlinedButton, '启用'), findsOneWidget);
    final copy = find.widgetWithText(OutlinedButton, '复制订阅');
    await tester.ensureVisible(copy);
    await tester.tap(copy);
    await tester.pumpAndSettle();
    expect(copied, url);
    expect(controller.writes.single['path'], '/api/v1/mobile/users/1/share');
    expect(find.text('订阅链接已复制'), findsOneWidget);
    final reset = find.widgetWithText(OutlinedButton, '重置');
    await tester.ensureVisible(reset);
    await tester.tap(reset);
    await tester.pumpAndSettle();
    expect(find.text('重置用户流量'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, '取消'));
    await tester.pumpAndSettle();
    expect(controller.writes, hasLength(1));
  });
  testWidgets('confirming after an account switch sends no user operation', (
    tester,
  ) async {
    final controller = DetailsController()..enabled = true;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((_) => controller)],
        child: const MaterialApp(home: Scaffold(body: UsersScreen())),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('details-user'));
    await tester.pumpAndSettle();
    final disable = find.widgetWithText(OutlinedButton, '禁用');
    await tester.ensureVisible(disable);
    await tester.pumpAndSettle();
    await tester.tap(disable);
    await tester.pumpAndSettle();
    expect(find.textContaining('details-user 的当前连接'), findsOneWidget);
    controller.changeAccount();
    await tester.tap(find.widgetWithText(FilledButton, '确认'));
    await tester.pumpAndSettle();
    expect(controller.writes, isEmpty);
    expect(find.text('登录状态已改变，请重新打开用户'), findsOneWidget);
  });
}
