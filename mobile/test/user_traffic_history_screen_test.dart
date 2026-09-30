import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/core/app_theme.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';
import 'package:hysteria2_manager/screens/user_traffic_history_screen.dart';

Map<String, dynamic> history({int bytes = 1073741824}) => {
  'userId': 42,
  'month': '2026-09',
  'timezone': 'Asia/Shanghai',
  'totalBytes': bytes,
  'days': List.generate(
    30,
    (i) => {
      'date': '2026-09-${(30 - i).toString().padLeft(2, '0')}',
      'totalBytes': i == 0 ? bytes : 0,
      'percent': i == 0 && bytes > 0 ? 100 : 0,
      'hasRecords': i == 0 && bytes > 0,
      'hours': List.generate(
        24,
        (h) => {
          'hour': h,
          'totalBytes': i == 0 && h == 12 ? bytes : 0,
          'percent': i == 0 && h == 12 && bytes > 0 ? 100 : 0,
        },
      ),
    },
  ),
};

class HistoryController extends AppController {
  final paths = <String>[];
  Future<Map<String, dynamic>> Function() reply = () async => history();
  @override
  Future<Map<String, dynamic>> getJson(String path) {
    paths.add(path);
    if (path == '/api/v1/mobile/users') {
      return Future.value({
        'items': [
          {
            'id': 42,
            'name': '测试用户',
            'enabled': true,
            'generation': 0,
            'deviceLimit': 3,
            'trafficLimitBytes': 1073741824,
            'allowUdp443': true,
            'onlineDevices': 0,
            'usedBytes': 0,
            'txBytes': 0,
            'rxBytes': 0,
          },
        ],
      });
    }
    if (path.endsWith('/domain-usage')) {
      return Future.value({'month': '2026-09', 'items': []});
    }
    return reply();
  }
}

Future<void> mount(
  WidgetTester tester,
  HistoryController controller, {
  Widget? screen,
  double scale = 1,
  bool dark = true,
}) async {
  tester.view.physicalSize = const Size(375, 812);
  tester.view.devicePixelRatio = 1;
  tester.platformDispatcher.textScaleFactorTestValue = scale;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
    tester.platformDispatcher.clearTextScaleFactorTestValue();
  });
  await tester.pumpWidget(
    ProviderScope(
      overrides: [appControllerProvider.overrideWith((ref) => controller)],
      child: MaterialApp(
        theme: buildAppTheme(
          Colors.blue,
          dark ? Brightness.dark : Brightness.light,
        ),
        home:
            screen ??
            const UserTrafficHistoryScreen(userId: 42, userName: '测试用户'),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  for (final scale in [1.0, 2.0]) {
    testWidgets(
      'user entries navigate directly and retain left/right order scale=$scale',
      (tester) async {
        final c = HistoryController();
        await mount(
          tester,
          c,
          scale: scale,
          screen: const Scaffold(body: UsersScreen()),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('测试用户').first);
        await tester.pumpAndSettle();
        final visits = find.widgetWithText(OutlinedButton, '最常访问');
        final traffic = find.widgetWithText(OutlinedButton, '流量详情');
        expect(
          tester.getCenter(visits).dx,
          lessThan(tester.getCenter(traffic).dx),
        );
        await tester.tap(visits);
        await tester.pumpAndSettle();
        expect(c.paths.last, '/api/v1/mobile/users/42/domain-usage');
        expect(find.text('本月访问域名 TOP10'), findsOneWidget);
        expect(find.text('每日 / 每小时流量'), findsNothing);
        await tester.pageBack();
        await tester.pumpAndSettle();
        await tester.tap(traffic);
        await tester.pumpAndSettle();
        expect(c.paths.last, '/api/v1/mobile/users/42/traffic-history');
        expect(find.text('每日用量'), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
  }

  for (final dark in [true, false]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets(
        'daily/hour drilldown fits dark=$dark scale=$scale without polling',
        (tester) async {
          final c = HistoryController();
          await mount(tester, c, dark: dark, scale: scale);
          await tester.pumpAndSettle();
          expect(find.text('12:00–13:00'), findsNothing);
          await tester.scrollUntilVisible(
            find.text('2026-09-30'),
            160,
            scrollable: find.byType(Scrollable).first,
          );
          await tester.tap(find.text('2026-09-30'));
          await tester.pumpAndSettle();
          expect(find.text('12:00–13:00'), findsOneWidget);
          await tester.scrollUntilVisible(
            find.text('23:00–24:00'),
            200,
            scrollable: find.byType(Scrollable).first,
          );
          expect(tester.takeException(), isNull);
          await tester.pump(const Duration(seconds: 30));
          expect(c.paths.length, 1);
        },
      );
    }
  }

  testWidgets(
    'failed refresh retains content and allows retry; empty has an explanation',
    (tester) async {
      final c = HistoryController();
      await mount(tester, c);
      await tester.pumpAndSettle();
      c.reply = () async => throw const ApiException('网络暂不可用');
      await tester.tap(find.byTooltip('刷新流量记录'));
      await tester.pumpAndSettle();
      expect(find.text('以下保留上次读取的记录'), findsOneWidget);
      expect(find.text('1.0 GiB'), findsWidgets);
      c.reply = () async => history(bytes: 0);
      await tester.tap(find.text('重试'));
      await tester.pumpAndSettle();
      expect(find.text('本月暂无流量记录'), findsOneWidget);
      expect(find.text('网络暂不可用'), findsNothing);
    },
  );

  testWidgets(
    'missing feature and malformed cross-account data are safe errors',
    (tester) async {
      final c = HistoryController()
        ..reply = (() async =>
            throw const ApiException('missing', statusCode: 404));
      await mount(tester, c);
      await tester.pumpAndSettle();
      expect(find.textContaining('v0.39.32'), findsOneWidget);
      c.reply = () async => history()..['userId'] = 43;
      await tester.tap(find.text('重试'));
      await tester.pumpAndSettle();
      expect(find.text('流量数据暂时无法读取，请稍后重试'), findsOneWidget);
      expect(find.text('每日用量'), findsNothing);
    },
  );

  testWidgets(
    'in-flight request is not duplicated and cannot update after leaving',
    (tester) async {
      final pending = Completer<Map<String, dynamic>>();
      final c = HistoryController()..reply = (() => pending.future);
      await mount(tester, c);
      await tester.tap(find.byTooltip('刷新流量记录'));
      await tester.pump();
      expect(c.paths.length, 1);
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      pending.complete(history());
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );
}
