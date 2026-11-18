import 'package:flutter/material.dart';
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
      await tester.ensureVisible(find.widgetWithText(OutlinedButton, '更多'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, '更多'));
      await tester.pumpAndSettle();
      final disable = find.widgetWithText(ListTile, '停用');
      await tester.ensureVisible(disable);
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
      expect(find.widgetWithText(ListTile, '启用'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
