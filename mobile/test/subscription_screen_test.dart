import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/subscription_screen.dart';

import 'support/design_fixture.dart';
import 'user_details_state_test.dart' as details;

class SubscriptionController extends DesignFixtureController {
  bool supported = true;
  final writes = <Map<String, dynamic>>[];
  Completer<Map<String, dynamic>>? pending;
  Map<String, dynamic> data = {
    'exists': true,
    'enabled': true,
    'url': 'https://panel.example.com/sub/fixed-test',
    'generation': 4,
    'revision': 'revision-4',
    'userType': 1,
    'premiumReadyCount': 4,
    'expiresAt': null,
    'usesDefaults': true,
  };
  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    if (path.endsWith('/capabilities')) {
      return {
        'features': supported ? ['mobile-subscription-management'] : [],
      };
    }
    return Map.from(data);
  }

  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> payload = const {},
  ]) async {
    writes.add({'path': path, ...payload});
    if (pending != null) return pending!.future;
    data = {...data, 'enabled': false, 'revision': 'revision-5'};
    return Map.from(data);
  }
}

Future<void> mount(
  WidgetTester tester,
  SubscriptionController controller,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [appControllerProvider.overrideWith((_) => controller)],
      child: const MaterialApp(
        home: SubscriptionScreen(userId: 7, name: '专线001'),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'subscription disable confirms and preserves link with exact revision',
    (tester) async {
      final c = SubscriptionController();
      await mount(tester, c);
      expect(find.text('专线节点 · 已就绪 4 / 4 地区'), findsOneWidget);
      expect(find.text('账号到期：永久'), findsOneWidget);
      await tester.tap(find.widgetWithText(OutlinedButton, '停用订阅'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('确认'));
      await tester.pumpAndSettle();
      expect(c.writes.single, {
        'path': '/api/v1/mobile/users/7/subscription-disable',
        'generation': 4,
        'revision': 'revision-4',
      });
      expect(find.text('订阅已停用'), findsOneWidget);
      expect(
        find.text('https://panel.example.com/sub/fixed-test'),
        findsOneWidget,
      );
    },
  );
  testWidgets('unsupported backend exposes explanation without a mutation', (
    tester,
  ) async {
    final c = SubscriptionController()..supported = false;
    await mount(tester, c);
    expect(find.textContaining('请先升级面板'), findsOneWidget);
    expect(find.text('重置订阅链接'), findsNothing);
    expect(c.writes, isEmpty);
  });
  testWidgets(
    'reset requires confirmation and blocks duplicate requests until reload after failure',
    (tester) async {
      final c = SubscriptionController()
        ..pending = Completer<Map<String, dynamic>>();
      await mount(tester, c);
      await tester.tap(find.text('链接泄露处理'));
      await tester.pumpAndSettle();
      final reset = find.widgetWithText(OutlinedButton, '重置订阅链接');
      await tester.ensureVisible(reset);
      await tester.tap(reset);
      await tester.pumpAndSettle();
      await tester.tap(find.text('取消'));
      await tester.pumpAndSettle();
      expect(c.writes, isEmpty);
      await tester.tap(reset);
      await tester.pumpAndSettle();
      await tester.tap(find.text('确认'));
      await tester.pump();
      expect(c.writes, hasLength(1));
      expect(tester.widget<OutlinedButton>(reset).onPressed, isNull);
      c.pending!.completeError(const ApiException('状态已变化'));
      await tester.pumpAndSettle();
      expect(find.textContaining('请刷新核对后再操作'), findsOneWidget);
      expect(tester.widget<OutlinedButton>(reset).onPressed, isNull);
    },
  );
  for (final scale in [1.0, 2.0]) {
    testWidgets('nine user actions have equal cells at 320px scale $scale', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 740);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
        tester.platformDispatcher.clearTextScaleFactorTestValue();
      });
      await details.openDetails(tester, details.DetailsController());
      final grid = find.byWidgetPredicate(
        (w) =>
            w is GridView &&
            w.gridDelegate is SliverGridDelegateWithFixedCrossAxisCount &&
            (w.gridDelegate as SliverGridDelegateWithFixedCrossAxisCount)
                    .crossAxisCount ==
                3,
      );
      expect(grid, findsOneWidget);
      final buttons = find.descendant(
        of: grid,
        matching: find.byType(OutlinedButton),
      );
      expect(buttons, findsNWidgets(9));
      final sizes = [
        for (final e in buttons.evaluate())
          tester.getSize(find.byWidget(e.widget)),
      ];
      for (final size in sizes) {
        expect(size.width, closeTo(sizes.first.width, .01));
        expect(size.height, closeTo(sizes.first.height, .01));
      }
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
