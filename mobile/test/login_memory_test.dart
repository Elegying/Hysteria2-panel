import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/login_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DelayedHintController extends AppController {
  final hint = Completer<({String address, String port, String username})?>();
  @override
  Future<({String address, String port, String username})?> rememberedLogin() =>
      hint.future;
}

void main() {
  testWidgets(
    'remembered panel restores endpoint and account but not password',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'panel_base_url': 'https://panel.example.test:19998',
        'panel_username': 'example-admin',
      });
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appControllerProvider.overrideWith((ref) => AppController()),
          ],
          child: const MaterialApp(home: LoginScreen()),
        ),
      );
      await tester.pumpAndSettle();
      final fields = tester
          .widgetList<TextFormField>(find.byType(TextFormField))
          .toList();
      expect(fields.map((f) => f.controller!.text), [
        'https://panel.example.test',
        '19998',
        'example-admin',
        '',
      ]);
    },
  );

  testWidgets('late history never overwrites manual input', (tester) async {
    final controller = DelayedHintController();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((ref) => controller)],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.enterText(
      find.byType(TextFormField).first,
      'new.example.test',
    );
    controller.hint.complete((
      address: 'https://old.example.test',
      port: '443',
      username: 'old',
    ));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<TextFormField>(find.byType(TextFormField).first)
          .controller!
          .text,
      'new.example.test',
    );
  });
}
