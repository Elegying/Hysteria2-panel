import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'multi_panel_test.dart' as fixture;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({
      'mobile_device_id': 'transition-device',
    });
  });

  test(
    'login cannot skip a logout queued behind a slow secure write',
    () async {
      final storage = BarrierStorage();
      final revoked = <String>[];
      final controller = fixture.controller(
        secureStorage: storage,
        handle: (options, handler) {
          if (options.path.endsWith('/auth/logout')) {
            revoked.add(options.data['refreshToken'] as String);
          }
          fixture.respond(options, handler);
        },
      );
      addTearDown(controller.dispose);
      await fixture.login(controller, 0);
      storage.pauseNext = true;
      final rename = controller.renamePanel(0, '保存中');
      await storage.blocked.future;
      final logout = controller.logout();
      final login = fixture
          .login(controller, 1)
          .then((_) => true, onError: (Object _) => false);
      storage.release.complete();
      await Future.wait([rename, logout]);
      if (!await login) await fixture.login(controller, 1);
      expect(revoked, contains('panel1.example.test-refresh'));
      expect(controller.state.panels[0].session, isNull);
      expect(controller.state.panels[1].session, isNotNull);
      final saved = jsonDecode(
        (await fixture.storage.read(key: fixture.profilesKey))!,
      ) as Map;
      expect((saved['panels'] as List)[0]['refreshToken'], isNull);
    },
  );

  test('repeated logout shares the durable credential removal', () async {
    final storage = BarrierStorage();
    final revoked = <String>[];
    final controller = fixture.controller(
      secureStorage: storage,
      handle: (options, handler) {
        if (options.path.endsWith('/auth/logout')) {
          revoked.add(options.data['refreshToken'] as String);
        }
        fixture.respond(options, handler);
      },
    );
    addTearDown(controller.dispose);
    await fixture.login(controller, 0);
    storage.pauseNext = true;
    final rename = controller.renamePanel(0, '保存中');
    await storage.blocked.future;
    final first = controller.logout();
    final second = controller.logout();
    storage.release.complete();
    await Future.wait([rename, first, second]);
    expect(revoked, ['panel1.example.test-refresh']);
    expect(controller.state.session, isNull);
    expect(controller.state.working, isFalse);
  });

  test(
    'an earlier network logout does not replace the next local logout',
    () async {
      final started = Completer<void>();
      late RequestOptions heldOptions;
      late RequestInterceptorHandler heldHandler;
      final controller = fixture.controller(
        handle: (options, handler) {
          if (options.path.endsWith('/auth/logout') && !started.isCompleted) {
            heldOptions = options;
            heldHandler = handler;
            started.complete();
            return;
          }
          fixture.respond(options, handler);
        },
      );
      addTearDown(controller.dispose);
      await fixture.login(controller, 0);
      final first = controller.logout();
      await started.future;
      expect(controller.state.working, isFalse);
      await fixture.login(controller, 1);
      final second = controller.logout();
      try {
        for (var i = 0; i < 20 && controller.state.working; i++) {
          await Future<void>.delayed(Duration.zero);
        }
        expect(controller.state.session, isNull);
        final saved = jsonDecode(
          (await fixture.storage.read(key: fixture.profilesKey))!,
        ) as Map;
        expect((saved['panels'] as List)[1]['refreshToken'], isNull);
        expect(
          (saved['pendingRevocations'] as List).map(
            (item) => item['refreshToken'],
          ),
          contains('panel2.example.test-refresh'),
        );
      } finally {
        fixture.respond(heldOptions, heldHandler);
        await Future.wait([first, second]);
      }
    },
  );

  test(
    'a full revocation queue rejects login before issuing a new session',
    () async {
      final original = fixture.controller();
      await fixture.login(original, 0);
      original.dispose();
      final saved = jsonDecode(
        (await fixture.storage.read(key: fixture.profilesKey))!,
      ) as Map<String, dynamic>;
      saved['pendingRevocations'] = List.generate(
        32,
        (index) => {
          'baseUrl': 'https://offline.example.test',
          'accessToken': 'access-$index',
          'refreshToken': 'refresh-$index',
          'revocationToken': 'revoke-$index',
        },
      );
      await fixture.storage.write(
        key: fixture.profilesKey,
        value: jsonEncode(saved),
      );
      var issued = 0;
      final controller = fixture.controller(
        handle: (options, handler) {
          if (options.path.endsWith('/auth/logout')) {
            handler.reject(
              DioException(
                requestOptions: options,
                type: DioExceptionType.connectionError,
              ),
            );
            return;
          }
          if (options.path.endsWith('/auth/login')) issued++;
          fixture.respond(options, handler);
        },
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await expectLater(fixture.login(controller, 0), throwsA(anything));
      expect(issued, 0);
      expect(controller.state.panels[0].session, isNotNull);
    },
  );
}

class BarrierStorage extends FlutterSecureStorage {
  bool pauseNext = false;
  final blocked = Completer<void>();
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
    if (pauseNext && key == fixture.profilesKey) {
      pauseNext = false;
      blocked.complete();
      await release.future;
    }
    await super.write(key: key, value: value);
  }
}
