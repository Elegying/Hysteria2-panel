import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/domain_usage_screen.dart';
import 'package:hysteria2_manager/screens/home_screen.dart';
import 'package:hysteria2_manager/screens/nodes_screen.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';

import 'support/design_fixture.dart';

class DeepReviewController extends DesignFixtureController {
  int writes = 0;
  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    if (path.endsWith('/domain-usage')) {
      return {
        'month': '2026-10',
        'items': [
          {
            'domain': 'very-long-domain-for-small-screen.example.com',
            'txBytes': 9223372036854775807,
            'rxBytes': 0,
            'usedBytes': 9223372036854775807,
          },
        ],
      };
    }
    return super.getJson(path);
  }

  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) async {
    writes++;
    return {'uri': 'hysteria2://fixture@example.invalid:19999', 'name': '测试节点'};
  }
}

Future<void> display(
  WidgetTester tester,
  DeepReviewController controller,
  Widget child, {
  bool dark = false,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [appControllerProvider.overrideWith((ref) => controller)],
      child: MaterialApp(
        theme: dark ? ThemeData.dark() : ThemeData.light(),
        home: Scaffold(body: child),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('node copy success feedback is visible above the details sheet', (
    tester,
  ) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (_) async => null,
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
    await display(tester, DeepReviewController(), const NodesScreen());
    await tester.tap(find.text('边缘节点').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('复制节点 ID'));
    await tester.pumpAndSettle();
    expect(find.text('节点 ID 已复制').hitTestable(), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('node clipboard failure stays visible above node details', (
    tester,
  ) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          throw PlatformException(code: 'denied');
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
    await display(tester, DeepReviewController(), const NodesScreen());
    await tester.tap(find.text('边缘节点').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('复制节点 ID'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('复制失败，请重试或长按节点 ID 手动复制'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  for (final dark in [false, true]) {
    testWidgets(
      'domain totals and long names fit 320px with 2x text dark=$dark',
      (tester) async {
        tester.view.physicalSize = const Size(320, 740);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
          tester.platformDispatcher.clearTextScaleFactorTestValue();
        });
        await display(
          tester,
          DeepReviewController(),
          const DomainUsageScreen.global(),
          dark: dark,
        );
        await tester.drag(find.byType(Scrollable).first, const Offset(0, -350));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.text('合计 8192 PiB'), findsOneWidget);
        expect(
          tester
              .getSize(
                find.text('very-long-domain-for-small-screen.example.com'),
              )
              .width,
          greaterThan(180),
          reason: 'Large text must not squeeze the domain between its rank and total',
        );
        await tester.pumpWidget(const SizedBox.shrink());
      },
    );
  }

  for (final action in ['停止', '重启服务器']) {
    testWidgets('$action rapid taps open only one confirmation', (
      tester,
    ) async {
      final c = DeepReviewController();
      await display(tester, c, const HomeScreen());
      final trigger = action == '停止'
          ? find.text(action)
          : find.byTooltip(action);
      await tester.scrollUntilVisible(
        trigger,
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.ensureVisible(trigger);
      await tester.pumpAndSettle();
      await tester.tap(trigger);
      await tester.tap(trigger, warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(find.byType(Dialog), findsOneWidget);
      await tester.tap(find.widgetWithText(TextButton, '取消'));
      await tester.pumpAndSettle();
      expect(c.writes, 0);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets('system share failure remains recoverable above user details', (
    tester,
  ) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/share'),
      (_) async => throw PlatformException(code: 'unavailable'),
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/share'),
        null,
      ),
    );
    final c = DeepReviewController();
    await display(tester, c, const UsersScreen());
    await tester.scrollUntilVisible(
      find.text('示例用户 1'),
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('示例用户 1'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ActionChip, '分享'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('无法打开系统分享，请稍后重试'), findsOneWidget);
    await tester.tap(
      find.descendant(
        of: find.byType(Dialog).last,
        matching: find.widgetWithText(TextButton, '关闭'),
      ),
    );
    await tester.pumpAndSettle();
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/share'),
      (_) async => 'test-target',
    );
    await tester.tap(find.widgetWithText(ActionChip, '分享'));
    await tester.pumpAndSettle();
    expect(c.writes, 2);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('created credentials retain their dialog after share failure', (
    tester,
  ) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/share'),
      (_) async => throw PlatformException(code: 'unavailable'),
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/share'),
        null,
      ),
    );
    final c = DeepReviewController();
    await display(tester, c, const UsersScreen());
    await tester.tap(find.text('新增用户'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byWidgetPredicate(
        (w) => w is TextField && w.decoration?.labelText == '用户名',
      ),
      'share-test-user',
    );
    await tester.tap(find.widgetWithText(FilledButton, '创建'));
    await tester.pumpAndSettle();
    expect(find.text('用户已创建'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '分享'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('无法打开系统分享，请稍后重试'), findsOneWidget);
    await tester.tap(
      find.descendant(
        of: find.byType(Dialog).last,
        matching: find.widgetWithText(TextButton, '关闭'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('用户已创建'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
