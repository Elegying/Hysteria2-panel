import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/design_fixture.dart';

void main() {
  testWidgets('capture management flow for compact layout review', (
    tester,
  ) async {
    final output = Platform.environment['UI_CAPTURE_DIR'];
    if (output == null) return;
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: '管理面板',
      packageName: 'test',
      version: '0.5.1',
      buildNumber: '37',
      buildSignature: '',
    );
    await tester.runAsync(() async {
      final loader = FontLoader('Roboto')
        ..addFont(
          Future.value(
            ByteData.sublistView(
              File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
                  .readAsBytesSync(),
            ),
          ),
        );
      await loader.load();
      await (FontLoader('Ahem')..addFont(
            Future.value(
              ByteData.sublistView(
                File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
                    .readAsBytesSync(),
              ),
            ),
          ))
          .load();
      await (FontLoader(
        'MaterialIcons',
      )..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'))).load();
    });
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    tester.binding.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(disableAnimations: true);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
      tester.binding.platformDispatcher.clearAccessibilityFeaturesTestValue();
    });
    final key = GlobalKey();
    Future<void> capture(String name) async {
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      final boundary =
          key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      await tester.runAsync(() async {
        final image = await boundary.toImage();
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(output).create(recursive: true);
        await File('$output/$name.png')
            .writeAsBytes(bytes!.buffer.asUint8List());
        image.dispose();
      });
    }

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appControllerProvider.overrideWith((_) => DesignFixtureController()),
        ],
        child: RepaintBoundary(key: key, child: const Hysteria2ManagerApp()),
      ),
    );
    await capture('01-home');
    var i = 2;
    for (final label in ['用户', '节点', '设置']) {
      await tester.tap(
        find
            .descendant(
              of: find.byType(AppBottomDock),
              matching: find.text(label),
            )
            .hitTestable()
            .first,
      );
      await capture('0${i++}-$label');
    }
    Future<void> tab(String label) async {
      await tester.tap(
        find
            .descendant(
              of: find.byType(AppBottomDock),
              matching: find.text(label),
            )
            .hitTestable()
            .first,
      );
      await tester.pumpAndSettle();
    }

    await tab('用户');
    await tester.tap(find.text('新增用户'));
    await capture('05-create-user');
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('示例用户 1').hitTestable().first);
    await capture('06-user-details');
    await tester.ensureVisible(find.text('订阅管理'));
    await tester.tap(find.text('订阅管理'));
    await capture('10-subscription');
    await tester.pageBack();
    await tester.pumpAndSettle();
    Navigator.of(tester.element(find.byType(AppBottomDock))).pop();
    await tester.pumpAndSettle();
    await tab('节点');
    await tester.tap(find.text('边缘节点').hitTestable().first);
    await capture('07-node-details');
    Navigator.of(tester.element(find.byType(AppBottomDock))).pop();
    await tester.pumpAndSettle();
    await tab('首页');
    await tester.scrollUntilVisible(
      find.text('一键对接'),
      150,
      scrollable: find.byType(Scrollable).hitTestable().first,
    );
    await tester.tap(find.text('一键对接'));
    await capture('08-enrollment');
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(
      ProviderScope(
        key: const ValueKey('login-capture'),
        overrides: [
          appControllerProvider.overrideWith(
            (_) => DesignFixtureController(loggedIn: false),
          ),
        ],
        child: RepaintBoundary(key: key, child: const Hysteria2ManagerApp()),
      ),
    );
    await capture('09-login');
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
