import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:integration_test/integration_test.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:package_info_plus/package_info_plus.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('native storage, HTTPS, panels, failure recovery and logout', (
    tester,
  ) async {
    final package = await PackageInfo.fromPlatform();
    expect(
      package.packageName,
      'vip.ssrvpn.hysteria2manager.preview.stability',
    );
    const encodedCa = String.fromEnvironment('ACCEPTANCE_CA');
    expect(
      encodedCa,
      isNotEmpty,
      reason: 'Start tests/mobile_fixture.py first',
    );
    final security = SecurityContext(withTrustedRoots: false)
      ..setTrustedCertificatesBytes(base64Decode(encodedCa));
    var offline = false;
    AppController createController() => AppController(
      dioFactory: (base) {
        final dio = Dio(
          BaseOptions(
            baseUrl: base,
            connectTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 20),
            followRedirects: false,
            validateStatus: (status) => status != null && status < 600,
          ),
        );
        dio.httpClientAdapter = IOHttpClientAdapter(
          createHttpClient: () => HttpClient(context: security),
        );
        dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              if (offline) {
                handler.reject(
                  DioException.connectionError(
                    requestOptions: options,
                    reason: 'isolated acceptance outage',
                  ),
                );
              } else {
                handler.next(options);
              }
            },
          ),
        );
        return dio;
      },
    );

    // Only this dedicated test application's storage is cleared.
    const storage = FlutterSecureStorage();
    await storage.deleteAll();
    final controller = createController();
    await controller.initialize();
    expect(controller.state.session, isNull);
    await expectLater(
      controller.login(
        address: 'http://127.0.0.1',
        port: 31888,
        username: 'Elegy',
        password: 'admin-password',
      ),
      throwsA(isA<ApiException>()),
    );
    for (final index in [0, 1]) {
      await controller.login(
        address: '127.0.0.1',
        port: index == 0
            ? const int.fromEnvironment('ACCEPTANCE_PORT', defaultValue: 31888)
            : const int.fromEnvironment(
                'ACCEPTANCE_PORT_2',
                defaultValue: 31889,
              ),
        username: 'Elegy',
        password: 'admin-password',
        panelIndex: index,
        rememberPassword: false,
      );
      expect(controller.state.session, isNotNull);
      final overview = await controller.getJson('/api/v1/mobile/overview');
      expect(overview['panelName'], 'acceptance-panel-${index + 1}');
    }
    expect(
      (await storage.readAll()).values.any(
        (value) => value.contains('admin-password'),
      ),
      isFalse,
    );
    debugPrint('ACCEPTANCE: HTTPS, two panels and native storage verified');
    controller.dispose();

    // A new controller has no in-memory tokens and restores through native storage.
    final restored = createController();
    await restored.initialize();
    expect(restored.state.session, isNotNull);
    await restored.selectPanel(0);
    expect(
      (await restored.getJson('/api/v1/mobile/overview'))['panelName'],
      'acceptance-panel-1',
    );
    offline = true;
    await expectLater(
      restored.getJson('/api/v1/mobile/overview'),
      throwsA(isA<ApiException>()),
    );
    offline = false;
    expect(
      (await restored.getJson('/api/v1/mobile/overview'))['panelName'],
      'acceptance-panel-1',
    );

    debugPrint(
      'ACCEPTANCE: controller recreation and request recovery verified',
    );
    await LiquidGlassWidgets.initialize(enablePerformanceMonitor: false);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((ref) => restored)],
        child: const Hysteria2ManagerApp(),
      ),
    );
    for (final label in ['用户', '节点', '设置', '首页']) {
      for (var frame = 0; frame < 10; frame++) {
        await tester.pump(const Duration(milliseconds: 200));
      }
      await tester.tap(find.text(label).hitTestable().last);
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.takeException(), isNull);
      debugPrint('ACCEPTANCE: navigation verified: $label');
    }
    await restored.logout();
    expect(restored.state.session, isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    final afterLogout = createController();
    await afterLogout.initialize();
    expect(afterLogout.state.session, isNull);
    afterLogout.dispose();
    debugPrint('ACCEPTANCE: logout persisted and all assertions completed');
  });
}
