import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _refreshKey = 'mobile_refresh_token';
const _savedToken = 'synthetic-refresh-token';
const _storage = FlutterSecureStorage();

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'panel_base_url': 'https://panel.example.test:19998',
      'panel_username': 'test-admin',
    });
    FlutterSecureStorage.setMockInitialValues({
      _refreshKey: _savedToken,
      'mobile_device_id': 'synthetic-device-id',
    });
  });

  test(
    'maintenance operations use their deadline while normal calls stay bounded',
    () async {
      final timeouts = <String, Duration?>{};
      final controller = _controller((options, handler) {
        timeouts[options.path] = options.receiveTimeout;
        _respond(handler, options, 200, {
          'data': options.path.endsWith('/auth/refresh')
              ? {'accessToken': 'new-access', 'refreshToken': 'new-refresh'}
              : {'done': true},
        });
      });
      addTearDown(controller.dispose);
      await controller.initialize();
      for (final path in [
        '/api/v1/mobile/service/restart',
        '/api/v1/mobile/service/stop',
        '/api/v1/mobile/nodes/local/disable',
        '/api/v1/mobile/system/reboot',
      ]) {
        expect(await controller.postJson(path), {'done': true});
        expect(timeouts[path], const Duration(minutes: 15));
      }
      await controller.getJson('/api/v1/mobile/overview');
      await controller.postJson('/api/v1/mobile/users');
      await controller.postJson('/api/v1/mobile/service/start');
      expect(timeouts['/api/v1/mobile/overview'], const Duration(seconds: 20));
      expect(timeouts['/api/v1/mobile/users'], const Duration(seconds: 20));
      expect(
        timeouts['/api/v1/mobile/service/start'],
        const Duration(seconds: 20),
      );
    },
  );

  for (final failure in ['timeout', 'unavailable', 'invalid-response']) {
    test(
      'startup preserves credentials after $failure and can recover',
      () async {
        var recovered = false;
        var refreshes = 0;
        final controller = _controller((options, handler) {
          if (options.path.endsWith('/auth/refresh')) {
            refreshes++;
            if (!recovered) {
              _failRefresh(failure, options, handler);
              return;
            }
            expect(options.data['refreshToken'], _savedToken);
            _respond(handler, options, 200, {
              'data': {
                'accessToken': 'new-access',
                'refreshToken': 'new-refresh',
              },
            });
          } else if (options.headers['Authorization'] == 'Bearer new-access') {
            _respond(handler, options, 200, {
              'data': {'healthy': true},
            });
          } else {
            _respond(handler, options, 401, {
              'error': {'code': 'unauthorized', 'message': '请重新登录'},
            });
          }
        });
        addTearDown(controller.dispose);

        await controller.initialize();
        expect(controller.state.initializing, isFalse);
        expect(controller.state.session?.refreshToken, _savedToken);
        expect(await _storage.read(key: _refreshKey), _savedToken);

        recovered = true;
        expect(await controller.getJson('/test'), {'healthy': true});
        expect(refreshes, 2);
        expect(await _storage.read(key: _refreshKey), 'new-refresh');
        expect(controller.state.error, isNull);
      },
    );
  }

  test(
    'logout retains connection hints while removing authentication',
    () async {
      final controller = AppController();
      addTearDown(controller.dispose);
      await controller.logout();
      expect(await _storage.read(key: _refreshKey), isNull);
      expect(controller.state.session, isNull);
      expect(await controller.rememberedLogin(), (
        address: 'https://panel.example.test',
        port: '19998',
        username: 'test-admin',
      ));
    },
  );

  test('an explicitly rejected refresh token is removed', () async {
    final controller = _controller((options, handler) {
      _respond(handler, options, 401, {
        'error': {'code': 'refresh_expired', 'message': '登录已过期'},
      });
    });
    addTearDown(controller.dispose);

    await controller.initialize();
    expect(controller.state.session, isNull);
    expect(await _storage.read(key: _refreshKey), isNull);
  });

  test(
    'concurrent requests share a failed refresh and can retry later',
    () async {
      var unavailable = false;
      var refreshes = 0;
      final controller = _controller((options, handler) {
        if (options.path.endsWith('/auth/refresh')) {
          refreshes++;
          if (unavailable) {
            Future<void>.delayed(const Duration(milliseconds: 20), () {
              _failRefresh('unavailable', options, handler);
            });
          } else {
            _respond(handler, options, 200, {
              'data': {
                'accessToken': 'access-$refreshes',
                'refreshToken': 'refresh-$refreshes',
              },
            });
          }
        } else if (options.headers['Authorization'] == 'Bearer access-3') {
          _respond(handler, options, 200, {
            'data': {'healthy': true},
          });
        } else {
          _respond(handler, options, 401, {
            'error': {'code': 'unauthorized', 'message': '请重新登录'},
          });
        }
      });
      addTearDown(controller.dispose);
      await controller.initialize();

      unavailable = true;
      await Future.wait([
        for (var i = 0; i < 3; i++)
          expectLater(
            controller.getJson('/test'),
            throwsA(
              isA<ApiException>().having(
                (error) => error.statusCode,
                'statusCode',
                503,
              ),
            ),
          ),
      ]);
      expect(refreshes, 2);
      expect(controller.state.session?.refreshToken, 'refresh-1');
      expect(await _storage.read(key: _refreshKey), 'refresh-1');

      unavailable = false;
      expect(await controller.getJson('/test'), {'healthy': true});
      expect(refreshes, 3);
    },
  );

  test('a refresh arriving after logout cannot restore credentials', () async {
    final started = Completer<void>();
    late RequestOptions pendingOptions;
    late RequestInterceptorHandler pendingHandler;
    final controller = _controller((options, handler) {
      if (options.path.endsWith('/auth/refresh')) {
        pendingOptions = options;
        pendingHandler = handler;
        started.complete();
      } else {
        _respond(handler, options, 200, {'data': {}});
      }
    });
    addTearDown(controller.dispose);
    final initialization = controller.initialize();
    await started.future;
    final logout = controller.logout();
    _respond(pendingHandler, pendingOptions, 200, {
      'data': {'accessToken': 'late-access', 'refreshToken': 'late-refresh'},
    });
    await Future.wait([initialization, logout]);
    expect(controller.state.session, isNull);
    expect(await _storage.read(key: _refreshKey), isNull);
  });

  for (final status in [200, 401]) {
    test(
      'an old refresh with status $status cannot replace a new login',
      () async {
        var refreshes = 0;
        final started = Completer<void>();
        late RequestOptions pendingOptions;
        late RequestInterceptorHandler pendingHandler;
        final controller = _controller((options, handler) {
          if (options.path.endsWith('/capabilities')) {
            _respond(handler, options, 200, {
              'data': {
                'features': [
                  'local-node-control',
                  'one-click-node-pairing',
                  'node-realtime-traffic',
                  'server-reboot',
                  'domain-traffic-top10',
                ],
              },
            });
          } else if (options.path.endsWith('/auth/login')) {
            _respond(handler, options, 200, {
              'data': {
                'accessToken': 'new-login-access',
                'refreshToken': 'new-login-refresh',
              },
            });
          } else if (options.path.endsWith('/auth/refresh')) {
            if (++refreshes == 1) {
              _respond(handler, options, 200, {
                'data': {
                  'accessToken': 'old-access',
                  'refreshToken': 'old-refresh',
                },
              });
            } else {
              pendingOptions = options;
              pendingHandler = handler;
              started.complete();
            }
          } else if (options.path.endsWith('/auth/logout')) {
            _respond(handler, options, 200, {'data': {}});
          } else {
            _respond(handler, options, 401, {
              'error': {'message': 'expired'},
            });
          }
        });
        addTearDown(controller.dispose);
        await controller.initialize();
        final request = expectLater(
          controller.getJson('/test'),
          throwsA(isA<ApiException>()),
        );
        await started.future;
        final logout = controller.logout();
        await controller.login(
          address: 'new-panel.example.test',
          port: 19998,
          username: 'new-admin',
          password: 'synthetic-password',
        );
        _respond(
          pendingHandler,
          pendingOptions,
          status,
          status == 200
              ? {
                  'data': {
                    'accessToken': 'late-access',
                    'refreshToken': 'late-refresh',
                  },
                }
              : {
                  'error': {'message': 'expired'},
                },
        );
        await Future.wait([request, logout]);
        expect(controller.state.session?.username, 'new-admin');
        expect(
          controller.state.session?.baseUrl,
          'https://new-panel.example.test:19998',
        );
        expect(await _storage.read(key: _refreshKey), 'new-login-refresh');
      },
    );
  }

  test('an explicit invalid URL port is rejected before login', () {
    for (final port in [0, 65536, 999999999999]) {
      expect(
        () => AppController.normalizeBaseUrl(
          'https://panel.example.test:$port',
          19998,
        ),
        throwsA(isA<ApiException>()),
      );
    }
  });

  test(
    'logout waits for an in-flight credential write before clearing it',
    () async {
      final storage = _DelayedStorage();
      final controller = _controller((options, handler) {
        _respond(handler, options, 200, {
          'data': {
            'accessToken': 'late-access',
            'refreshToken': 'late-refresh',
          },
        });
      }, storage: storage);
      addTearDown(controller.dispose);
      final initialization = controller.initialize();
      await storage.started.future;
      final logout = controller.logout();
      expect(controller.state.session, isNull);
      storage.release.complete();
      await Future.wait([initialization, logout]);
      expect(await _storage.read(key: _refreshKey), isNull);
    },
  );

  test(
    'a late 401 reuses the refreshed access token without rotating again',
    () async {
      var refreshes = 0;
      final started = Completer<void>();
      late RequestOptions lateOptions;
      late RequestInterceptorHandler lateHandler;
      final controller = _controller((options, handler) {
        if (options.path.endsWith('/auth/refresh')) {
          refreshes++;
          _respond(handler, options, 200, {
            'data': {
              'accessToken': 'access-$refreshes',
              'refreshToken': 'refresh-$refreshes',
            },
          });
        } else if (options.headers['Authorization'] == 'Bearer access-2') {
          _respond(handler, options, 200, {
            'data': {'healthy': true},
          });
        } else if (options.path == '/late') {
          lateOptions = options;
          lateHandler = handler;
          started.complete();
        } else {
          _respond(handler, options, 401, {
            'error': {'message': 'expired'},
          });
        }
      });
      addTearDown(controller.dispose);
      await controller.initialize();
      final lateRequest = controller.getJson('/late');
      await started.future;
      expect(await controller.getJson('/fast'), {'healthy': true});
      _respond(lateHandler, lateOptions, 401, {
        'error': {'message': 'expired'},
      });
      expect(await lateRequest, {'healthy': true});
      expect(refreshes, 2);
    },
  );
  for (final mode in [
    'login-write',
    'login-delete',
    'refresh-write',
    'logout-delete',
  ]) {
    test(
      'storage failure in $mode cannot leave an orphan server session',
      () async {
        final storage = _FailingStorage();
        storage.failWrite = mode.endsWith('write');
        storage.failDelete = mode == 'login-delete';
        final active = <String>{};
        final controller = _controller((options, handler) {
          if (options.path.endsWith('/capabilities')) {
            _respond(handler, options, 200, {
              'data': {
                'features': [
                  'local-node-control',
                  'one-click-node-pairing',
                  'node-realtime-traffic',
                  'server-reboot',
                  'domain-traffic-top10',
                ],
              },
            });
          } else if (options.path.endsWith('/auth/login') ||
              options.path.endsWith('/auth/refresh')) {
            active.add('current-access');
            _respond(handler, options, 200, {
              'data': {
                'accessToken': 'current-access',
                'refreshToken': 'current-refresh',
              },
            });
          } else if (options.path.endsWith('/auth/logout')) {
            active.remove(
              options.headers['Authorization'].toString().substring(7),
            );
            _respond(handler, options, 200, {'data': {}});
          }
        }, storage: storage);
        addTearDown(controller.dispose);
        if (mode.startsWith('login')) {
          await expectLater(
            controller.login(
              address: 'new-panel.example.test',
              port: 19998,
              username: 'test-admin',
              password: 'fixture-password',
            ),
            throwsA(isA<ApiException>()),
          );
          expect(controller.state.session, isNull);
          if (mode == 'login-delete') {
            expect(await _storage.read(key: _refreshKey), _savedToken);
            final preferences = await SharedPreferences.getInstance();
            expect(
              preferences.getString('panel_base_url'),
              'https://panel.example.test:19998',
            );
          } else {
            expect(await _storage.read(key: _refreshKey), isNull);
            var refreshRequests = 0;
            final restarted = _controller((options, handler) {
              refreshRequests++;
              _respond(handler, options, 401, {
                'error': {'message': 'unexpected refresh'},
              });
            });
            addTearDown(restarted.dispose);
            await restarted.initialize();
            expect(refreshRequests, 0);
          }
        } else {
          await controller.initialize();
          if (mode == 'logout-delete') {
            storage.failDelete = true;
            await controller.logout();
            expect(controller.state.error, contains('安全存储清理失败'));
            expect(controller.state.session, isNull);
          } else {
            expect(
              controller.state.session?.accessToken,
              isNot('current-access'),
            );
            expect(await _storage.read(key: _refreshKey), _savedToken);
          }
        }
        expect(active, isEmpty);
      },
    );
  }
  for (final field in ['items', 'trafficBudgets']) {
    test(
      'malformed $field is rejected before rendering and can recover',
      () async {
        var malformed = true;
        final controller = _controller((options, handler) {
          if (options.path.endsWith('/auth/refresh')) {
            _respond(handler, options, 200, {
              'data': {
                'accessToken': 'valid-access',
                'refreshToken': 'valid-refresh',
              },
            });
          } else {
            _respond(handler, options, 200, {
              'data': {
                field: malformed
                    ? [42]
                    : [
                        {'name': 'valid'},
                      ],
              },
            });
          }
        });
        addTearDown(controller.dispose);
        await controller.initialize();
        await expectLater(
          controller.getJson('/list-payload'),
          throwsA(isA<ApiException>()),
        );
        expect(controller.state.session?.accessToken, 'valid-access');
        malformed = false;
        expect(await controller.getJson('/list-payload'), {
          field: [
            {'name': 'valid'},
          ],
        });
      },
    );
  }
  test('invalid response data is not reported as an empty success', () async {
    var malformed = true;
    final controller = _controller((options, handler) {
      if (options.path.endsWith('/auth/refresh')) {
        _respond(handler, options, 200, {
          'data': {
            'accessToken': 'valid-access',
            'refreshToken': 'valid-refresh',
          },
        });
      } else {
        _respond(handler, options, 200, {
          'data': malformed ? [] : {'healthy': true},
        });
      }
    });
    addTearDown(controller.dispose);
    await controller.initialize();
    await expectLater(
      controller.getJson('/list-payload'),
      throwsA(isA<ApiException>()),
    );
    malformed = false;
    expect(await controller.getJson('/list-payload'), {'healthy': true});
  });
}

AppController _controller(
  void Function(RequestOptions, RequestInterceptorHandler) onRequest, {
  FlutterSecureStorage? storage,
}) {
  return AppController(
    storage: storage,
    dioFactory: (baseUrl) {
      final dio = Dio(
        BaseOptions(
          baseUrl: baseUrl,
          receiveTimeout: const Duration(seconds: 20),
        ),
      );
      dio.interceptors.add(InterceptorsWrapper(onRequest: onRequest));
      return dio;
    },
  );
}

class _DelayedStorage extends FlutterSecureStorage {
  final started = Completer<void>();
  final release = Completer<void>();

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
  }) async {
    if (key == _refreshKey && value == 'late-refresh') {
      started.complete();
      await release.future;
    }
    await super.write(
      key: key,
      value: value,
      iOptions: iOptions,
      aOptions: aOptions,
      lOptions: lOptions,
      webOptions: webOptions,
      mOptions: mOptions,
      wOptions: wOptions,
    );
  }
}

void _respond(
  RequestInterceptorHandler handler,
  RequestOptions options,
  int status,
  Object body,
) {
  handler.resolve(
    Response<dynamic>(requestOptions: options, statusCode: status, data: body),
  );
}

void _failRefresh(
  String failure,
  RequestOptions options,
  RequestInterceptorHandler handler,
) {
  if (failure == 'timeout') {
    handler.reject(
      DioException(
        requestOptions: options,
        type: DioExceptionType.connectionTimeout,
      ),
    );
  } else if (failure == 'invalid-response') {
    _respond(handler, options, 502, '<html>upstream unavailable</html>');
  } else {
    _respond(handler, options, 503, {
      'error': {'message': '服务暂时不可用'},
    });
  }
}

class _FailingStorage extends FlutterSecureStorage {
  bool failWrite = false;
  bool failDelete = false;

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
  }) async {
    if (key == _refreshKey && failWrite) {
      throw StateError('synthetic write failure');
    }
    await super.write(key: key, value: value);
  }

  @override
  Future<void> delete({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (key == _refreshKey && failDelete) {
      throw StateError('synthetic delete failure');
    }
    await super.delete(key: key);
  }
}
