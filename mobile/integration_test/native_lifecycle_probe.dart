// USB-driven acceptance entrypoint, never used by a production build.
// The host writes a private JSON config/command through `adb shell run-as`.
// Reports contain assertions and lifecycle events, never session credentials.
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:package_info_plus/package_info_plus.dart';

const _package = 'vip.ssrvpn.hysteria2manager.preview.stability';
const _directory = '/data/user/0/$_package/files';
const _accountsKey = 'mobile_panel_accounts_v1';
final _report = File('$_directory/lifecycle-report.jsonl');

void record(Map<String, Object?> event) {
  _report.writeAsStringSync(
    '${jsonEncode({'at': DateTime.now().toUtc().toIso8601String(), 'pid': pid, ...event})}\n',
    mode: FileMode.append,
    flush: true,
  );
}

void check(bool condition, String name) {
  record({'check': name, 'passed': condition});
  if (!condition) throw StateError(name);
}

class LifecycleRecorder extends WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    record({'lifecycle': state.name});
  }
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final package = await PackageInfo.fromPlatform();
  if (package.packageName != _package || !Platform.isAndroid) {
    throw StateError(
      'Only the independent Android acceptance package is allowed',
    );
  }
  final config = jsonDecode(
    await File('$_directory/lifecycle-config.json').readAsString(),
  ) as Map<String, dynamic>;
  final mode = config['mode'] as String;
  record({'started': mode});
  WidgetsBinding.instance.addObserver(LifecycleRecorder());
  FlutterError.onError = (details) {
    record({'frameworkError': details.exception.runtimeType.toString()});
    FlutterError.presentError(details);
  };
  try {
    final security = SecurityContext(withTrustedRoots: false)
      ..setTrustedCertificatesBytes(
        base64Decode(config['ACCEPTANCE_CA'] as String),
      );
    final controller = AppController(
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
        return dio;
      },
    );
    const storage = FlutterSecureStorage();
    if (mode == 'seed') await storage.deleteAll();
    final saved = await storage.read(key: _accountsKey);
    await controller.initialize();
    if (mode == 'seed') {
      check(controller.state.session == null, 'empty test storage');
      for (var index = 0; index < 2; index++) {
        await controller.login(
          address: config['ACCEPTANCE_HOST'] as String? ?? '127.0.0.1',
          port:
              config[index == 0 ? 'ACCEPTANCE_PORT' : 'ACCEPTANCE_PORT_2']
                  as int,
          username: config['ACCEPTANCE_USERNAME'] as String? ?? 'Elegy',
          password:
              config['ACCEPTANCE_PASSWORD'] as String? ?? 'admin-password',
          panelIndex: index,
          rememberPassword: false,
        );
      }
      check(
        controller.state.panels.every((panel) => panel.session != null),
        'two sessions saved',
      );
      final accounts =
          jsonDecode((await storage.read(key: _accountsKey))!) as Map;
      check(
        (accounts['panels'] as List).every((panel) => panel['password'] == ''),
        'password not remembered',
      );
    } else if (mode == 'restore') {
      check(saved != null, 'native account storage survived process death');
      final old = jsonDecode(saved!) as Map;
      check(
        controller.state.session != null,
        'session restored after process death',
      );
      check(
        controller.state.activePanel == old['active'],
        'active panel survived process death',
      );
      check(
        controller.state.session!.refreshToken !=
            (old['panels'] as List)[old['active'] as int]['refreshToken'],
        'refresh token rotated on restart',
      );
    } else if (mode == 'logged-out') {
      check(controller.state.session == null, 'logout survived process death');
    } else {
      throw StateError('Unknown acceptance mode');
    }
    await LiquidGlassWidgets.initialize(enablePerformanceMonitor: false);
    runApp(
      ProviderScope(
        overrides: [appControllerProvider.overrideWith((ref) => controller)],
        child: const Hysteria2ManagerApp(),
      ),
    );
    record({'ready': mode, 'activePanel': controller.state.activePanel});
    var sequence = 0;
    final commands = File('$_directory/lifecycle-command.json');
    while (true) {
      await Future<void>.delayed(const Duration(milliseconds: 200));
      if (!commands.existsSync()) continue;
      final command =
          jsonDecode(await commands.readAsString()) as Map<String, dynamic>;
      if ((command['sequence'] as int) <= sequence) continue;
      sequence = command['sequence'] as int;
      final action = command['action'] as String;
      final started = DateTime.now();
      try {
        if (action == 'overview') {
          final failure = command['expectFailure'] == true;
          final session = controller.state.session;
          var failed = false;
          try {
            final data = await controller.getJson('/api/v1/mobile/overview');
            check(
              data['panelName'] ==
                  'acceptance-panel-${controller.state.activePanel + 1}',
              'overview matches selected panel',
            );
          } on ApiException {
            failed = true;
          }
          check(
            failed == failure,
            failure
                ? 'real transport failure surfaced'
                : 'real request recovered',
          );
          check(
            controller.state.session != null &&
                controller.state.session!.deviceId == session!.deviceId,
            'recoverable request preserved session',
          );
        } else if (action == 'select') {
          await controller.selectPanel(command['panel'] as int);
          final data = await controller.getJson('/api/v1/mobile/overview');
          check(
            data['panelName'] ==
                'acceptance-panel-${(command['panel'] as int) + 1}',
            'panel switch matches response',
          );
        } else if (action == 'logout') {
          await controller.logout();
          check(
            controller.state.session == null,
            'logout cleared active session',
          );
        } else {
          throw StateError('Unknown acceptance action');
        }
        record({
          'sequence': sequence,
          'action': action,
          'passed': true,
          'milliseconds': DateTime.now().difference(started).inMilliseconds,
        });
      } catch (error) {
        record({
          'sequence': sequence,
          'action': action,
          'passed': false,
          'errorType': error.runtimeType.toString(),
        });
        rethrow;
      }
    }
  } catch (error) {
    record({'fatal': error.runtimeType.toString()});
    rethrow;
  }
}
