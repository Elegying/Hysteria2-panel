import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/core/glass.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/design_fixture.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Hysteria2管理',
      packageName: 'vip.ssrvpn.hysteria2manager',
      version: '0.3.3',
      buildNumber: '11',
      buildSignature: '',
    );
  });

  for (final scale in [1.0, 2.0]) {
    for (final dark in [false, true]) {
      testWidgets('all tabs and login fit 320px at scale $scale dark=$dark', (
        tester,
      ) async {
        tester.view.physicalSize = const Size(320, 740);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        tester.platformDispatcher.platformBrightnessTestValue = dark
            ? Brightness.dark
            : Brightness.light;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
          tester.platformDispatcher.clearTextScaleFactorTestValue();
          tester.platformDispatcher.clearPlatformBrightnessTestValue();
        });
        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              appControllerProvider.overrideWith(
                (ref) => DesignFixtureController(),
              ),
            ],
            child: const Hysteria2ManagerApp(),
          ),
        );
        await tester.pumpAndSettle();
        for (final label in ['首页', '用户', '节点', '设置']) {
          await tester.tap(
            find.descendant(
              of: find.byType(AppBottomDock),
              matching: find.text(label),
            ),
          );
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull, reason: label);
          // Titles and actions must share one compact toolbar, with no expanded blank header.
          final header = tester.widget<SliverAppBar>(find.byType(SliverAppBar));
          expect(header.expandedHeight, isNull);
          expect(header.toolbarHeight, lessThanOrEqualTo(64));
          if (label == '首页') {
            final title = find.descendant(
              of: find.byType(SliverAppBar),
              matching: find.text(label),
            );
            expect(
              (tester.getCenter(title).dy -
                      tester.getCenter(find.byTooltip('刷新')).dy)
                  .abs(),
              lessThan(8),
            );
          }
          final scrollable = find.byType(Scrollable).first;
          for (var i = 0; i < 4; i++) {
            await tester.drag(scrollable, const Offset(0, -350));
            await tester.pumpAndSettle();
            expect(tester.takeException(), isNull, reason: '$label scroll $i');
          }
        }
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              appControllerProvider.overrideWith(
                (ref) => DesignFixtureController(loggedIn: false),
              ),
            ],
            child: const Hysteria2ManagerApp(),
          ),
        );
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.widgetWithText(FilledButton, '登录'));
        await tester.tap(find.widgetWithText(FilledButton, '登录'));
        await tester.pumpAndSettle();
        expect(find.text('请输入面板账号'), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pumpAndSettle();
      });
    }
  }
  testWidgets('high contrast surfaces remain opaque', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(highContrast: true),
          child: GlassSurface(blurSigma: 24, child: Text('清晰内容')),
        ),
      ),
    );
    expect(find.byType(BackdropFilter), findsNothing);
  });
}
