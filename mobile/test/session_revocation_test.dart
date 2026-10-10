import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'multi_panel_test.dart' as fixture;

Future<List<dynamic>> pending() async {
  final document = jsonDecode(
    (await fixture.storage.read(key: fixture.profilesKey))!,
  ) as Map;
  return document['pendingRevocations'] as List? ?? [];
}

void reply(
  RequestOptions options,
  RequestInterceptorHandler handler,
  Map<String, dynamic> data, {
  int status = 200,
}) {
  handler.resolve(
    Response(requestOptions: options, statusCode: status, data: {'data': data}),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({
      'mobile_device_id': 'audit-device',
    });
  });

  test(
    'deleting a restored inactive profile revokes its refresh credential',
    () async {
      final original = fixture.controller();
      await original.initialize();
      await fixture.login(original, 0);
      await fixture.login(original, 1);
      original.dispose();
      final logouts = <RequestOptions>[];
      final restored = fixture.controller(
        handle: (options, handler) {
          if (options.path.endsWith('/auth/logout')) logouts.add(options);
          fixture.respond(options, handler);
        },
      );
      addTearDown(restored.dispose);
      await restored.initialize();
      await restored.forgetPanel(0);
      expect(logouts, hasLength(1));
      expect(logouts.single.baseUrl, contains('panel1.example.test'));
      expect(
        logouts.single.data['refreshToken'],
        'panel1.example.test-refresh',
      );
      expect(restored.state.panels[0].session, isNull);
      expect(restored.state.panels[1].session, isNotNull);
      expect(await pending(), isEmpty);
    },
  );

  test(
    'offline logout atomically retains revocation and retries after restart',
    () async {
      var offline = false;
      final original = fixture.controller(
        handle: (options, handler) {
          if (options.path.endsWith('/auth/login')) {
            reply(options, handler, {
              'accessToken': 'access',
              'refreshToken': 'refresh',
              'revocationToken': 'stable-revoke',
            });
          } else if (offline && options.path.endsWith('/auth/logout')) {
            handler.reject(
              DioException(
                requestOptions: options,
                type: DioExceptionType.connectionError,
              ),
            );
          } else {
            fixture.respond(options, handler);
          }
        },
      );
      await fixture.login(original, 0);
      offline = true;
      await original.logout();
      expect(original.state.session, isNull);
      expect((await pending()).single['revocationToken'], 'stable-revoke');
      original.dispose();
      final requests = <RequestOptions>[];
      final restored = fixture.controller(
        handle: (options, handler) {
          if (options.path.endsWith('/auth/logout')) requests.add(options);
          fixture.respond(options, handler);
        },
      );
      addTearDown(restored.dispose);
      await restored.initialize();
      for (var i = 0; i < 20 && (await pending()).isNotEmpty; i++) {
        await Future<void>.delayed(Duration.zero);
      }
      expect(requests, hasLength(1));
      expect(requests.single.data['revocationToken'], 'stable-revoke');
      expect(await pending(), isEmpty);
      expect(restored.state.session, isNull);
    },
  );

  test(
    'forget waits for a concurrent refresh and revokes the updated credential',
    () async {
      final started = Completer<void>();
      late RequestOptions refreshRequest;
      late RequestInterceptorHandler refreshHandler;
      final revoked = <String>[];
      final controller = fixture.controller(
        handle: (options, handler) {
          if (options.path == '/protected' &&
              options.headers['Authorization'] != 'Bearer new-access') {
            fixture.respond(options, handler, status: 401);
          } else if (options.path.endsWith('/auth/refresh')) {
            refreshRequest = options;
            refreshHandler = handler;
            started.complete();
          } else if (options.path.endsWith('/auth/logout')) {
            revoked.add(options.data['refreshToken'] as String);
            reply(options, handler, {'revoked': true});
          } else {
            fixture.respond(options, handler);
          }
        },
      );
      addTearDown(controller.dispose);
      await fixture.login(controller, 0);
      final request = controller
          .getJson('/protected')
          .then<void>((_) {}, onError: (Object _) {});
      await started.future;
      final removal = controller.forgetPanel(0);
      reply(refreshRequest, refreshHandler, {
        'accessToken': 'new-access',
        'refreshToken': 'new-refresh',
        'revocationToken': 'stable-revoke',
      });
      await Future.wait([request, removal]);
      expect(revoked, ['new-refresh']);
      expect(controller.state.session, isNull);
      expect(await pending(), isEmpty);
    },
  );

  test(
    'old panel fallback refreshes only for revocation without restoring login',
    () async {
      final paths = <String>[];
      final controller = fixture.controller(
        handle: (options, handler) {
          paths.add(options.path);
          if (options.path.endsWith('/auth/logout')) {
            reply(
              options,
              handler,
              {},
              status: options.headers['Authorization'] == 'Bearer new-access'
                  ? 200
                  : 401,
            );
          } else if (options.path.endsWith('/auth/refresh')) {
            reply(options, handler, {
              'accessToken': 'new-access',
              'refreshToken': 'new-refresh',
            });
          } else {
            fixture.respond(options, handler);
          }
        },
      );
      addTearDown(controller.dispose);
      await fixture.login(controller, 0);
      paths.clear();
      await controller.logout();
      expect(paths, [
        '/api/v1/mobile/auth/logout',
        '/api/v1/mobile/auth/refresh',
        '/api/v1/mobile/auth/logout',
      ]);
      expect(controller.state.session, isNull);
      expect(await pending(), isEmpty);
    },
  );

  test(
    'failed profile write retains login and never revokes it in the background',
    () async {
      final storage = RejectingStorage();
      var logouts = 0;
      final controller = fixture.controller(
        secureStorage: storage,
        handle: (options, handler) {
          if (options.path.endsWith('/auth/logout')) logouts++;
          fixture.respond(options, handler);
        },
      );
      addTearDown(controller.dispose);
      await fixture.login(controller, 0);
      storage.reject = true;
      await expectLater(controller.forgetPanel(0), throwsA(anything));
      expect(controller.state.session, isNotNull);
      expect(logouts, 0);
      expect(await pending(), isEmpty);
    },
  );

  test(
    'expired legacy credentials do not permanently occupy the retry queue',
    () async {
      final controller = fixture.controller(
        handle: (options, handler) {
          if (options.path.endsWith('/auth/logout') ||
              options.path.endsWith('/auth/refresh')) {
            handler.resolve(
              Response(
                requestOptions: options,
                statusCode: 401,
                data: {
                  'error': {'code': 'REFRESH_EXPIRED', 'message': '已失效'},
                },
              ),
            );
          } else {
            fixture.respond(options, handler);
          }
        },
      );
      addTearDown(controller.dispose);
      await fixture.login(controller, 0);
      await controller.logout();
      expect(controller.state.session, isNull);
      expect(await pending(), isEmpty);
    },
  );
}

class RejectingStorage extends FlutterSecureStorage {
  bool reject = false;
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
    if (reject && key == fixture.profilesKey) {
      throw StateError('storage unavailable');
    }
    return super.write(key: key, value: value);
  }
}
