import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/home_screen.dart';

import 'support/design_fixture.dart';

class DelayedCapabilities extends DesignFixtureController {
  int reads = 0;
  Completer<Map<String, dynamic>> pending = Completer();
  @override
  Future<Map<String, dynamic>> getJson(String path) {
    if (path.endsWith('/capabilities')) {
      reads++;
      return pending.future;
    }
    return super.getJson(path);
  }
}

void main() {
  testWidgets(
    'slow capability check admits one enrollment dialog and releases guard after cancel',
    (tester) async {
      final controller = DelayedCapabilities();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((ref) => controller)],
          child: const MaterialApp(home: HomeScreen()),
        ),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('一键对接'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('一键对接'));
      await tester.tap(find.text('一键对接'));
      expect(controller.reads, 1);
      controller.pending.complete({
        'features': ['typed-node-enrollment-hopping'],
      });
      await tester.pumpAndSettle();
      expect(find.text('对接新节点'), findsOneWidget);
      await tester.tap(find.widgetWithText(TextButton, '取消'));
      await tester.pumpAndSettle();
      controller.pending = Completer();
      await tester.tap(find.text('一键对接'));
      expect(controller.reads, 2);
      controller.pending.complete({'features': []});
      await tester.pumpAndSettle();
      expect(find.text('对接新节点'), findsNothing);
      expect(find.text('请先升级面板移动接口，以支持节点类型和端口跳跃对接'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
