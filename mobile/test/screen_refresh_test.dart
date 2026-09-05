import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/domain_usage_screen.dart';
import 'package:hysteria2_manager/screens/home_screen.dart';
import 'package:hysteria2_manager/screens/nodes_screen.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';

class PendingRefreshController extends AppController {
  final requests = <Completer<Map<String, dynamic>>>[];

  @override
  Future<Map<String, dynamic>> getJson(String path) {
    final request = Completer<Map<String, dynamic>>();
    requests.add(request);
    return request.future;
  }
}

Map<String, dynamic> snapshot(
  String label, {
  int observedAt = 0,
  int totalBytes = 0,
}) => {
  'panelName': label,
  'observedAt': observedAt,
  'items': [
    {
      'id': 1,
      'nodeId': 'local',
      'name': label,
      'domain': label,
      'enabled': true,
      'generation': 0,
      'usedBytes': 0,
      'totalBytes': totalBytes,
      'onlineDevices': 0,
      'observedIp': '192.0.2.1',
      'status': 'online',
    },
  ],
};

Future<PendingRefreshController> mountPage(
  WidgetTester tester,
  Widget screen,
) async {
  final controller = PendingRefreshController();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [appControllerProvider.overrideWith((ref) => controller)],
      child: MaterialApp(
        theme: ThemeData.dark(useMaterial3: true),
        home: Scaffold(body: screen),
      ),
    ),
  );
  await tester.pump();
  return controller;
}

void refreshPage(WidgetTester tester) => unawaited(
  tester.widget<RefreshIndicator>(find.byType(RefreshIndicator)).onRefresh(),
);

void main() {
  final screens = <String, Widget>{
    'overview': const HomeScreen(),
    'users': const UsersScreen(),
    'nodes': const NodesScreen(),
    'domains': const DomainUsageScreen.global(),
  };
  for (final entry in screens.entries) {
    for (final outcome in ['success', 'failure', 'old-failure']) {
      final latestFails = outcome == 'failure';
      testWidgets('${entry.key} ignores obsolete refresh results ($outcome)', (
        tester,
      ) async {
        final controller = await mountPage(tester, entry.value);
        expect(controller.requests, hasLength(1));
        refreshPage(tester);
        await tester.pump();
        expect(controller.requests, hasLength(2));
        if (latestFails) {
          controller.requests[1].completeError(const ApiException('最新刷新失败'));
        } else {
          controller.requests[1].complete(snapshot('new-snapshot'));
        }
        await tester.pumpAndSettle();
        final latest = find.textContaining(
          latestFails ? '最新刷新失败' : 'new-snapshot',
        );
        expect(latest, findsWidgets);
        if (outcome == 'old-failure') {
          controller.requests[0].completeError(const ApiException('过期请求失败'));
        } else {
          controller.requests[0].complete(snapshot('old-snapshot'));
        }
        await tester.pumpAndSettle();
        expect(latest, findsWidgets);
        expect(find.textContaining('old-snapshot'), findsNothing);
        expect(find.textContaining('过期请求失败'), findsNothing);
        expect(tester.takeException(), isNull);
        refreshPage(tester);
        await tester.pump();
        final pending = controller.requests.last;
        await tester.pumpWidget(const SizedBox.shrink());
        pending.complete(snapshot('disposed-page'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      });
    }
    if (entry.key == 'domains') continue;
    testWidgets('${entry.key} polling waits for a slow request', (
      tester,
    ) async {
      final controller = await mountPage(tester, entry.value);
      await tester.pump(const Duration(seconds: 21));
      expect(controller.requests, hasLength(1));
      controller.requests.single.complete(snapshot('slow-snapshot'));
      await tester.pumpAndSettle();
      expect(find.textContaining('slow-snapshot'), findsWidgets);
      await tester.pump(const Duration(seconds: 15));
      expect(controller.requests, hasLength(2));
      await tester.pumpWidget(const SizedBox.shrink());
      controller.requests.last.complete(snapshot('disposed-page'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
    if (entry.key == 'overview') continue;
    testWidgets('${entry.key} identifies stale data after a failed refresh', (
      tester,
    ) async {
      final controller = await mountPage(tester, entry.value);
      controller.requests.single.complete(snapshot('cached-snapshot'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('刷新'));
      controller.requests.last.completeError(const ApiException('网络暂时不可用'));
      await tester.pumpAndSettle();
      expect(find.textContaining('cached-snapshot'), findsWidgets);
      expect(find.textContaining('数据刷新失败：网络暂时不可用'), findsOneWidget);
      await tester.tap(find.byTooltip('刷新'));
      controller.requests.last.complete(snapshot('recovered-snapshot'));
      await tester.pumpAndSettle();
      expect(find.textContaining('recovered-snapshot'), findsWidgets);
      expect(find.textContaining('数据刷新失败'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
    });
  }
  testWidgets('obsolete node traffic cannot change the next rate baseline', (
    tester,
  ) async {
    final controller = await mountPage(tester, const NodesScreen());
    refreshPage(tester);
    controller.requests[1].complete(
      snapshot('rate-node', observedAt: 20, totalBytes: 200),
    );
    await tester.pumpAndSettle();
    controller.requests[0].complete(
      snapshot('rate-node', observedAt: 10, totalBytes: 100),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('刷新'));
    controller.requests.last.complete(
      snapshot('rate-node', observedAt: 25, totalBytes: 300),
    );
    await tester.pumpAndSettle();
    expect(find.text('20 B/s'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
  });
}
