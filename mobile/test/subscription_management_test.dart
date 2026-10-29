import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/core/user_validity.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';

import 'users_screen_test.dart' show UserFormController;

class TierController extends UserFormController {
  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    final data = await super.getJson(path);
    final regular = Map<String, dynamic>.from(
      (data['items'] as List).first as Map,
    );
    data['items'] = [
      regular,
      {...regular, 'id': 2, 'name': 'premium-001', 'userType': 1},
    ];
    return data;
  }
}

void main() {
  test('validity is Beijing time regardless of device timezone', () {
    expect(
      userActivityLabel({'enabled': true, 'expiresAt': 100}, now: 100),
      '已到期',
    );
    expect(
      userActivityLabel({'enabled': true, 'startsAt': 200}, now: 100),
      '未开通',
    );
    expect(validityLabel(null), '永久');
    expect(validityLabel(1793318400), '2026-10-30 08:00');
  });
  testWidgets(
    'ordinary is default and premium creation sends tier and permanent dates',
    (tester) async {
      final controller = TierController();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((ref) => controller)],
          child: const MaterialApp(home: UsersScreen()),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('premium-001'), findsNothing);
      await tester.tap(find.text('专线用户'));
      await tester.pumpAndSettle();
      expect(find.text('form-test-user'), findsNothing);
      expect(find.text('premium-001'), findsWidgets);
      await tester.tap(find.text('新增用户'));
      await tester.pumpAndSettle();
      Finder field(String label) => find.byWidgetPredicate(
        (w) => w is TextField && w.decoration?.labelText == label,
      );
      expect(tester.widget<TextField>(field('设备数限制')).controller!.text, '100');
      await tester.enterText(field('用户名'), 'premium-002');
      await tester.tap(find.widgetWithText(FilledButton, '创建'));
      await tester.pumpAndSettle();
      expect(controller.requests.single['userType'], 1);
      expect(controller.requests.single['trafficLimitGb'], 250);
      expect(controller.requests.single['expiresAt'], isNull);
      expect(controller.requests.single.containsKey('allowUdp443'), isFalse);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
