import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/home_screen.dart';
import 'package:hysteria2_manager/screens/nodes_screen.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';

import 'users_screen_test.dart' show UserFormController;
import 'support/design_fixture.dart';

class AuditController extends DesignFixtureController {
  int writes = 0;
  int reads = 0;
  int online = 1;
  String status = 'online';
  Completer<Map<String, dynamic>>? pending;
  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) async {
    writes++;
    return pending == null
        ? {'deploymentCommand': '# audit placeholder - no token'}
        : pending!.future;
  }

  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    if (!path.endsWith('/nodes')) return super.getJson(path);
    reads++;
    return {
      'items': [
        {
          'kind': 'remote',
          'nodeId': 'audit-edge',
          'name': '审查节点',
          'status': status,
          'observedIp': '192.0.2.1',
          'expectedIp': '192.0.2.1',
          'onlineDevices': online,
          'dataPlaneState': 'direct_canary_passed',
          'canDisconnect': true,
          'canDeletePairing': true,
          'totalBytes': 0,
        },
      ],
    };
  }
}

Future<void> showScreen(
  WidgetTester tester,
  AuditController c,
  Widget child,
) async {
  tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [appControllerProvider.overrideWith((ref) => c)],
      child: MaterialApp(home: Scaffold(body: child)),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final status in [
    'pending_registration',
    'registration_expired',
    'disconnecting',
  ]) {
    testWidgets('node status $status fits 320px with 2x text', (tester) async {
      tester.view.physicalSize = const Size(320, 740);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
        tester.platformDispatcher.clearTextScaleFactorTestValue();
      });
      await showScreen(
        tester,
        AuditController()..status = status,
        const NodesScreen(),
      );
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
  testWidgets('user action error is exposed above the open details sheet', (
    tester,
  ) async {
    final c = UserFormController();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((ref) => c)],
        child: const MaterialApp(home: Scaffold(body: UsersScreen())),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('form-test-user').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ActionChip, '禁用'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '确认'));
    await tester.pumpAndSettle();
    final message = find.text('测试请求失败');
    expect(message, findsOneWidget);
    final visibleHitCount = message.hitTestable().evaluate().length;
    await tester.pumpWidget(const SizedBox.shrink());
    expect(
      visibleHitCount,
      1,
      reason: 'The modal sheet covers the Scaffold SnackBar',
    );
  });
  testWidgets('deployment code remains reachable when clipboard write fails', (
    tester,
  ) async {
    final c = AuditController();
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
          if (call.method == 'Clipboard.setData') {
            throw PlatformException(code: 'clipboard_denied');
          }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
    await showScreen(tester, c, const HomeScreen());
    await tester.scrollUntilVisible(
      find.text('一键对接'),
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('一键对接'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('一键对接'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).at(0), '审查节点');
    await tester.enterText(find.byType(TextField).at(1), '8.8.8.8');
    await tester.tap(
      find.descendant(
        of: find.byType(Dialog),
        matching: find.widgetWithText(FilledButton, '一键对接'),
      ),
    );
    await tester.pumpAndSettle();
    expect(c.writes, 1);
    expect(find.text('部署代码已生成'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('disconnect prevents a second request while first is pending', (
    tester,
  ) async {
    final c = AuditController()..pending = Completer<Map<String, dynamic>>();
    await showScreen(tester, c, const NodesScreen());
    await tester.tap(find.text('审查节点').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '一键断连').first);
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(Dialog),
        matching: find.widgetWithText(FilledButton, '一键断连'),
      ),
    );
    await tester.pumpAndSettle();
    final button = find.widgetWithText(FilledButton, '一键断连').first;
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsNothing);
    final writes = c.writes;
    c.pending!.complete({});
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox.shrink());
    expect(
      writes,
      1,
      reason: 'A pending destructive operation must not submit twice',
    );
  });
  testWidgets('open node details refresh after polling changes online count', (
    tester,
  ) async {
    final c = AuditController();
    await showScreen(tester, c, const NodesScreen());
    await tester.tap(find.text('审查节点').first);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('在线设备'),
      150,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.pumpAndSettle();
    final tile = find.ancestor(
      of: find.text('在线设备').last,
      matching: find.byType(ListTile),
    );
    expect(find.descendant(of: tile, matching: find.text('1')), findsOneWidget);
    final previousReads = c.reads;
    c.online = 17;
    await tester.pump(const Duration(seconds: 6));
    await tester.pumpAndSettle();
    expect(c.reads, greaterThan(previousReads));
    final actual = find
        .descendant(of: tile, matching: find.text('17'))
        .evaluate()
        .length;
    await tester.pumpWidget(const SizedBox.shrink());
    expect(
      actual,
      1,
      reason:
          'Polling occurred but the open details kept the previous snapshot',
    );
  });
}
