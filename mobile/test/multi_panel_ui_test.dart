import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';
import 'package:hysteria2_manager/screens/login_screen.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/design_fixture.dart';

class TwoPanels extends DesignFixtureController {
  TwoPanels()
    : super(
        dioFactory: (base) => Dio(BaseOptions(baseUrl: base))
          ..interceptors.add(
            InterceptorsWrapper(
              onRequest: (options, handler) => handler.resolve(
                Response(
                  requestOptions: options,
                  statusCode: 200,
                  data: {
                    'data': {'revoked': true},
                  },
                ),
              ),
            ),
          ),
      ) {
    state = AppState(
      initializing: false,
      session: accounts[0].session,
      panels: accounts,
    );
  }
  static final accounts = List.generate(2, (i) {
    final session = AppSession(
      baseUrl: 'https://panel${i + 1}.example.test:19998',
      username: '管理员${i + 1}',
      accessToken: '',
      refreshToken: 'test-token-$i',
      deviceId: 'test-device',
    );
    return PanelAccount(
      name: '面板${i + 1}',
      baseUrl: session.baseUrl,
      username: session.username,
      password: 'synthetic-secret-$i',
      session: session,
    );
  });
  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    final i = state.activePanel;
    final data = await super.getJson(path);
    if (path.endsWith('/overview')) data['panelName'] = '当前面板${i + 1}';
    if (data['items'] is List) {
      for (final item in data['items'] as List) {
        item['name'] = '面板${i + 1}-${item['name']}';
      }
    }
    return data;
  }
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    binding.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(disableAnimations: true);
    SharedPreferences.setMockInitialValues({
      'theme_mode': 'dark',
      'theme_mode_panel_2': 'light',
    });
    FlutterSecureStorage.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Hysteria2管理',
      packageName: 'test',
      version: '0.4.7',
      buildNumber: '30',
      buildSignature: '',
    );
  });
  tearDown(
    () => binding.platformDispatcher.clearAccessibilityFeaturesTestValue(),
  );

  Future<void> mount(
    WidgetTester tester,
    AppController c, {
    double width = 390,
    double scale = 1,
  }) async {
    tester.view.physicalSize = Size(width, 844);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = scale;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
      tester.platformDispatcher.clearTextScaleFactorTestValue();
    });
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((ref) => c)],
        child: const Hysteria2ManagerApp(),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> tab(WidgetTester tester, String name) async {
    await tester.tap(
      find
          .descendant(of: find.byType(AppBottomDock), matching: find.text(name))
          .hitTestable()
          .first,
    );
    await tester.pumpAndSettle();
  }

  testWidgets('switch rebuilds overview users nodes settings and panel theme', (
    tester,
  ) async {
    final c = TwoPanels();
    await mount(tester, c);
    expect(find.text('当前面板1'), findsOneWidget);
    await tab(tester, '用户');
    expect(find.text('面板1-示例用户 1'), findsWidgets);
    await tab(tester, '首页');
    await tester.tap(find.text('面板2').hitTestable().first);
    await tester.pumpAndSettle();
    expect(find.text('当前面板2'), findsOneWidget);
    expect(find.text('当前面板1'), findsNothing);
    await tab(tester, '用户');
    expect(find.text('面板2-示例用户 1'), findsWidgets);
    expect(find.text('面板1-示例用户 1'), findsNothing);
    await tab(tester, '节点');
    expect(find.text('面板2-主节点'), findsWidgets);
    await tab(tester, '设置');
    expect(find.text('管理员2'), findsOneWidget);
    expect(find.text('https://panel2.example.test:19998'), findsOneWidget);
    expect(
      Theme.of(tester.element(find.text('管理员2'))).brightness,
      Brightness.light,
    );
    await tab(tester, '首页');
    await tester.tap(find.text('面板1').hitTestable().first);
    await tester.pumpAndSettle();
    await tab(tester, '设置');
    expect(find.text('管理员1'), findsOneWidget);
    expect(
      Theme.of(tester.element(find.text('管理员1'))).brightness,
      Brightness.dark,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'logout restores hidden password and delete erases remembered form',
    (tester) async {
      final c = TwoPanels();
      await mount(tester, c);
      final logout = c.logout();
      await tester.pumpAndSettle();
      await logout;
      final fields = tester
          .widgetList<TextFormField>(find.byType(TextFormField))
          .toList();
      expect(fields.map((f) => f.controller!.text), [
        'https://panel1.example.test',
        '19998',
        '管理员1',
        'synthetic-secret-0',
      ]);
      expect(
        tester
            .widgetList<EditableText>(find.byType(EditableText))
            .last
            .obscureText,
        isTrue,
      );
      await tester.longPress(find.text('面板1').hitTestable().first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('删除登录记忆'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('删除'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widgetList<TextFormField>(find.byType(TextFormField))
            .every((f) => f.controller!.text.isEmpty),
        isTrue,
      );
      await tester.tap(find.text('面板2').hitTestable().first);
      await tester.pumpAndSettle();
      expect(find.byType(LoginScreen), findsNothing);
      expect(find.text('当前面板2'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'rename is discoverable and long names fit small screens at large text',
    (tester) async {
      final c = TwoPanels();
      await mount(tester, c, width: 320, scale: 2);
      await tester.longPress(find.text('面板1').hitTestable().first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('重命名'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '私家车专线面板');
      await tester.tap(find.text('保存'));
      await tester.pumpAndSettle();
      expect(find.text('私家车专线面板'), findsOneWidget);
      expect(c.state.panels[0].name, '私家车专线面板');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('switch discards old detail route', (tester) async {
    final c = TwoPanels();
    await mount(tester, c);
    final context = tester.element(find.byType(HomeShell));
    Navigator.of(context).push<void>(
      MaterialPageRoute(builder: (_) => const Scaffold(body: Text('旧面板详情'))),
    );
    await tester.pumpAndSettle();
    await c.selectPanel(1);
    await tester.pumpAndSettle();
    expect(find.text('旧面板详情'), findsNothing);
    expect(find.text('当前面板2'), findsOneWidget);
  });

  testWidgets('panel login and home previews', (tester) async {
    const fontPath = String.fromEnvironment('PANEL_UI_FONT');
    if (fontPath.isNotEmpty) {
      await tester.runAsync(() async {
        final bytes = ByteData.sublistView(await File(fontPath).readAsBytes());
        for (final family in ['Ahem', 'Roboto']) {
          await (FontLoader(family)..addFont(Future.value(bytes))).load();
        }
        await (FontLoader(
          'MaterialIcons',
        )..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'))).load();
      });
    }
    final c = TwoPanels();
    await mount(tester, c);
    await c.renamePanel(0, '私家车面板');
    await c.renamePanel(1, '私家车专线面板');
    await tester.pumpAndSettle();
    if (const bool.fromEnvironment('CAPTURE_PANEL_UI')) {
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('../../.codex-artifacts/multi-panel/home.png'),
      );
    }
    final logout = c.logout();
    await tester.pumpAndSettle();
    await logout;
    if (const bool.fromEnvironment('CAPTURE_PANEL_UI')) {
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('../../.codex-artifacts/multi-panel/login.png'),
      );
    }
  });
}
