import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/home_screen.dart';
import 'package:hysteria2_manager/screens/settings_screen.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';
import 'package:hysteria2_manager/screens/login_screen.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/design_fixture.dart';

class ReviewController extends DesignFixtureController {
  int writes = 0;
  void expire() => state = state.copyWith(clearSession: true);
  void refreshAccess() => state = state.copyWith(
    session: state.session!.copyWith(accessToken: 'refreshed-fixture'),
  );

  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) async {
    writes++;
    return {};
  }

  @override
  Future<void> logout() async => writes++;
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: '审查',
      packageName: 'test',
      version: '0.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
  });

  testWidgets(
    'session expiry removes dialogs from the authenticated navigator',
    (tester) async {
      tester.binding.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(
        () => tester.binding.platformDispatcher
            .clearAccessibilityFeaturesTestValue(),
      );
      final controller = ReviewController();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((ref) => controller)],
          child: const Hysteria2ManagerApp(),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find
            .descendant(
              of: find.byType(AppBottomDock),
              matching: find.text('用户'),
            )
            .hitTestable()
            .first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('新增用户'));
      await tester.pumpAndSettle();
      expect(find.byType(Dialog), findsOneWidget);
      controller.refreshAccess();
      await tester.pumpAndSettle();
      expect(find.byType(Dialog), findsOneWidget);
      controller.expire();
      await tester.pumpAndSettle();
      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byType(Dialog), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  for (final action in ['停止', '重启服务器', '退出登录', '禁用']) {
    testWidgets('$action confirmation cannot act after its page is disposed', (
      tester,
    ) async {
      final controller = ReviewController();
      var visible = true;
      late StateSetter changePage;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((ref) => controller)],
          child: MaterialApp(
            home: StatefulBuilder(
              builder: (context, setState) {
                changePage = setState;
                return visible
                    ? (action == '退出登录'
                          ? const SettingsScreen()
                          : action == '禁用'
                          ? const UsersScreen()
                          : const HomeScreen())
                    : const Scaffold(body: Text('登录页'));
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      if (action == '禁用') {
        await tester.scrollUntilVisible(
          find.text('示例用户 1'),
          250,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.ensureVisible(find.text('示例用户 1'));
        await tester.tap(find.text('示例用户 1'));
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(ActionChip, '禁用'));
      } else {
        final trigger = action == '重启服务器'
            ? find.byTooltip(action)
            : find.text(action);
        await tester.scrollUntilVisible(
          trigger,
          250,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.ensureVisible(trigger);
        await tester.pumpAndSettle();
        await tester.tap(trigger);
      }
      await tester.pumpAndSettle();
      expect(find.byType(Dialog), findsOneWidget);
      changePage(() => visible = false);
      await tester.pumpAndSettle();
      await tester.tap(
        find.descendant(
          of: find.byType(Dialog),
          matching: find.widgetWithText(
            FilledButton,
            action == '禁用' ? '确认' : action,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(controller.writes, 0);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
