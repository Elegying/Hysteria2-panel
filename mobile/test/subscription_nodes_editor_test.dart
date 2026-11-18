import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/subscription_nodes_screen.dart';
import 'package:hysteria2_manager/screens/subscription_screen.dart';

import 'support/design_fixture.dart';

class EditorController extends DesignFixtureController {
  bool failRead = false;
  final writes = <Map<String, dynamic>>[];
  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    if (failRead) throw const ApiException('读取失败');
    return {
      'revision': 7,
      'nodes': [
        {
          'id': 0,
          'label': '外部节点',
          'enabled': true,
          'host': 'example.invalid',
          'port': 443,
        },
      ],
    };
  }

  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) async {
    writes.add({'path': path, ...data});
    throw const ApiException('配置已变更，请重新加载');
  }
}

class LegacySubscriptionController extends DesignFixtureController {
  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    if (path.endsWith('/capabilities')) {
      return {
        'features': ['mobile-subscription-management'],
      };
    }
    return {
      'exists': true,
      'enabled': true,
      'userType': 0,
      'usesDefaults': false,
      'url': 'https://example.invalid/sub',
    };
  }
}

void main() {
  for (final embedded in [false, true]) {
    testWidgets(
      'legacy panel explains unavailable node editor (embedded: $embedded)',
      (tester) async {
        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              appControllerProvider.overrideWith(
                (_) => LegacySubscriptionController(),
              ),
            ],
            child: MaterialApp(
              home: Scaffold(
                body: SubscriptionScreen(
                  userId: 1,
                  name: 'test',
                  embedded: embedded,
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('编辑节点需升级面板接口'), findsOneWidget);
        expect(find.text('独立节点配置'), findsOneWidget);
        expect(find.textContaining('已选 0 个节点'), findsNothing);
      },
    );
  }

  testWidgets(
    'node editor rejects missing TLS fingerprint before saving draft',
    (tester) async {
      final controller = EditorController();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((_) => controller)],
          child: const MaterialApp(home: SubscriptionNodesScreen()),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('编辑').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('保存草稿'));
      await tester.pumpAndSettle();
      expect(find.text('请输入 64 位证书指纹（可含冒号）'), findsOneWidget);
      expect(controller.writes, isEmpty);
      await tester.tap(find.text('取消'));
      await tester.pumpAndSettle();
    },
  );

  testWidgets(
    'external editor preserves opaque credentials and revision after conflict',
    (tester) async {
      final controller = EditorController();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((_) => controller)],
          child: const MaterialApp(
            home: SubscriptionNodesScreen(external: true),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('发布'));
      await tester.pumpAndSettle();
      expect(controller.writes.single['revision'], 7);
      final nodes = controller.writes.single['nodes'] as List;
      expect(nodes.single['id'], 0);
      expect(nodes.single['uri'], '');
      expect(nodes.single.containsKey('host'), false);
      expect(find.text('配置已变更，请重新加载'), findsOneWidget);
      expect(find.text('外部节点'), findsWidgets);
    },
  );
  testWidgets(
    'failed initial load cannot publish an empty external configuration',
    (tester) async {
      final c = EditorController()..failRead = true;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((_) => c)],
          child: const MaterialApp(
            home: SubscriptionNodesScreen(external: true),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(find.widgetWithText(FilledButton, '发布'))
            .onPressed,
        isNull,
      );
      await tester.tap(find.text('发布'));
      expect(c.writes, isEmpty);
      c.failRead = false;
      await tester.tap(find.text('重新加载'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(find.widgetWithText(FilledButton, '发布'))
            .onPressed,
        isNotNull,
      );
    },
  );
  testWidgets('reloading a changed draft requires an explicit discard', (
    tester,
  ) async {
    final c = EditorController();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((_) => c)],
        child: const MaterialApp(home: SubscriptionNodesScreen(external: true)),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    await tester.tap(find.text('重新加载'));
    await tester.pumpAndSettle();
    expect(find.text('放弃未发布的修改？'), findsOneWidget);
    await tester.tap(find.text('继续编辑'));
    await tester.pumpAndSettle();
    expect(tester.widget<Switch>(find.byType(Switch)).value, isFalse);
    expect(c.writes, isEmpty);
  });
}
