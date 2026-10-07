import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

const storage = FlutterSecureStorage();
const profilesKey = 'mobile_panel_accounts_v1';
const features = [
  'local-node-control',
  'one-click-node-pairing',
  'node-realtime-traffic',
  'server-reboot',
  'domain-traffic-top10',
];

typedef Handler = void Function(RequestOptions, RequestInterceptorHandler);

AppController controller({
  Handler? handle,
  FlutterSecureStorage? secureStorage,
}) => AppController(
  storage: secureStorage,
  dioFactory: (base) {
    final dio = Dio(BaseOptions(baseUrl: base));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          if (handle != null) {
            handle(options, handler);
            return;
          }
          respond(options, handler);
        },
      ),
    );
    return dio;
  },
);

void respond(
  RequestOptions options,
  RequestInterceptorHandler handler, {
  int status = 200,
}) {
  final host = Uri.parse(options.baseUrl).host;
  handler.resolve(
    Response(
      requestOptions: options,
      statusCode: status,
      data: status != 200
          ? {
              'error': {'message': '已失效'},
            }
          : {
              'data': options.path.endsWith('capabilities')
                  ? {'features': features}
                  : options.path.contains('/auth/')
                  ? {
                      'accessToken': '$host-access',
                      'refreshToken': '$host-refresh',
                    }
                  : {
                      'host': host,
                      'authorization': options.headers['Authorization'],
                    },
            },
    ),
  );
}

Future<void> login(AppController c, int index, {bool remember = true}) =>
    c.login(
      address: 'panel${index + 1}.example.test',
      port: 443,
      username: 'admin$index',
      password: 'synthetic-secret-$index',
      panelIndex: index,
      rememberPassword: remember,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({
      'mobile_device_id': 'test-device-id',
    });
  });

  test('two independent sessions survive switches and restart', () async {
    final c = controller();
    addTearDown(c.dispose);
    await c.initialize();
    await login(c, 0);
    await login(c, 1);
    await c.renamePanel(0, '私家车面板');
    await c.renamePanel(1, '私家车专线面板');
    for (final i in [0, 1, 0]) {
      await c.selectPanel(i);
      final result = await c.getJson('/overview');
      expect(result['host'], 'panel${i + 1}.example.test');
      expect(
        result['authorization'],
        'Bearer panel${i + 1}.example.test-access',
      );
    }
    final restored = controller();
    addTearDown(restored.dispose);
    await restored.initialize();
    expect(restored.state.activePanel, 0);
    expect(restored.state.panels.map((p) => p.name), ['私家车面板', '私家车专线面板']);
    expect(restored.state.panels.every((p) => p.session != null), isTrue);
    await restored.selectPanel(1);
    // Restored secondary access token is empty: force its normal refresh path.
    expect(restored.state.session!.refreshToken, 'panel2.example.test-refresh');
    expect(restored.state.panels[1].password, 'synthetic-secret-1');
    final preferences = await SharedPreferences.getInstance();
    expect(
      preferences.getKeys().any(
        (key) => preferences.get(key).toString().contains('synthetic-secret'),
      ),
      isFalse,
    );
  });

  test(
    'failed second login leaves first session and saved data intact',
    () async {
      var reject = false;
      final c = controller(
        handle: (options, handler) => respond(
          options,
          handler,
          status: reject && options.path.endsWith('/auth/login') ? 401 : 200,
        ),
      );
      addTearDown(c.dispose);
      await login(c, 0);
      final saved = await storage.read(key: profilesKey);
      reject = true;
      await expectLater(login(c, 1), throwsA(isA<ApiException>()));
      expect(c.state.activePanel, 0);
      expect(c.state.working, isFalse);
      expect((await c.getJson('/users'))['host'], 'panel1.example.test');
      expect(await storage.read(key: profilesKey), saved);
    },
  );

  for (final status in [200, 401]) {
    test(
      'late $status from panel one never returns data or retries on panel two',
      () async {
        final started = Completer<void>();
        late RequestOptions pending;
        late RequestInterceptorHandler handler;
        final calls = <String>[];
        final c = controller(
          handle: (options, h) {
            calls.add('${options.baseUrl}${options.path}');
            if (options.path == '/delayed-write') {
              pending = options;
              handler = h;
              started.complete();
            } else {
              respond(options, h);
            }
          },
        );
        addTearDown(c.dispose);
        await login(c, 0);
        await login(c, 1);
        await c.selectPanel(0);
        final request = expectLater(
          c.postJson('/delayed-write'),
          throwsA(isA<ApiException>()),
        );
        await started.future;
        await c.selectPanel(1);
        respond(pending, handler, status: status);
        await request;
        expect(c.state.session!.username, 'admin1');
        expect(calls.where((url) => url.endsWith('/delayed-write')), [
          'https://panel1.example.test/delayed-write',
        ]);
      },
    );
  }

  test(
    'switch waits for refresh rotation and retains the rotated token',
    () async {
      final started = Completer<void>();
      late RequestOptions pending;
      late RequestInterceptorHandler handler;
      final c = controller(
        handle: (options, h) {
          if (options.path.endsWith('/auth/refresh')) {
            pending = options;
            handler = h;
            started.complete();
          } else {
            respond(options, h, status: options.path == '/expired' ? 401 : 200);
          }
        },
      );
      addTearDown(c.dispose);
      await login(c, 0);
      await login(c, 1);
      await c.selectPanel(0);
      final request = expectLater(
        c.getJson('/expired'),
        throwsA(isA<ApiException>()),
      );
      await started.future;
      final switchPanel = c.selectPanel(1);
      expect(c.state.activePanel, 0);
      handler.resolve(
        Response(
          requestOptions: pending,
          statusCode: 200,
          data: {
            'data': {
              'accessToken': 'rotated-access',
              'refreshToken': 'rotated-refresh',
            },
          },
        ),
      );
      await switchPanel;
      await request;
      expect(c.state.activePanel, 1);
      expect(c.state.panels[0].session!.refreshToken, 'rotated-refresh');
      final saved = jsonDecode((await storage.read(key: profilesKey))!);
      expect(saved['panels'][0]['refreshToken'], 'rotated-refresh');
    },
  );

  test('logout clears only current session; delete also erases credentials after restart', () async {
    final c = controller();
    addTearDown(c.dispose);
    await login(c, 0);
    await login(c, 1);
    await c.logout();
    expect(c.state.session, isNull);
    expect(c.state.panels[1].password, 'synthetic-secret-1');
    await c.selectPanel(0);
    expect((await c.getJson('/nodes'))['host'], 'panel1.example.test');
    await c.forgetPanel(1);
    final restored = controller();
    addTearDown(restored.dispose);
    await restored.initialize();
    expect(restored.state.panels[1].baseUrl, isEmpty);
    expect(restored.state.panels[1].username, isEmpty);
    expect(restored.state.panels[1].password, isEmpty);
    expect(restored.state.panels[1].session, isNull);
    expect(restored.state.panels[0].session, isNotNull);
    expect(
      (await storage.read(key: profilesKey))!,
      isNot(contains('synthetic-secret-1')),
    );
  });

  test('expired current panel does not revoke the other panel', () async {
    final c = controller(
      handle: (o, h) => respond(
        o,
        h,
        status: o.path == '/expired' || o.path.endsWith('/auth/refresh')
            ? 401
            : 200,
      ),
    );
    addTearDown(c.dispose);
    await login(c, 0);
    await login(c, 1);
    await expectLater(c.getJson('/expired'), throwsA(isA<ApiException>()));
    expect(c.state.session, isNull);
    await c.selectPanel(0);
    expect((await c.getJson('/users'))['host'], 'panel1.example.test');
  });

  test(
    'remember-password opt-out keeps a session without storing password',
    () async {
      final c = controller();
      addTearDown(c.dispose);
      await login(c, 0, remember: false);
      expect(c.state.session, isNotNull);
      expect(c.state.panels[0].password, isEmpty);
      expect(
        await storage.read(key: profilesKey),
        isNot(contains('synthetic-secret')),
      );
    },
  );

  test('storage failure keeps previous panel and reports failure', () async {
    final secure = FailingStorage();
    final c = controller(secureStorage: secure);
    addTearDown(c.dispose);
    await login(c, 0);
    final saved = await storage.read(key: profilesKey);
    secure.fail = true;
    await expectLater(login(c, 1), throwsA(isA<ApiException>()));
    expect(c.state.activePanel, 0);
    expect(c.state.session!.username, 'admin0');
    expect(await storage.read(key: profilesKey), saved);
    await expectLater(
      c.renamePanel(0, 'new name'),
      throwsA(isA<ApiException>()),
    );
    expect(c.state.panels[0].name, '面板1');
  });
}

class FailingStorage extends FlutterSecureStorage {
  bool fail = false;
  @override
  Future<void> write({
    required String key,
    required String? value,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) {
    if (fail && key == profilesKey) throw StateError('test storage failure');
    return super.write(key: key, value: value);
  }
}
