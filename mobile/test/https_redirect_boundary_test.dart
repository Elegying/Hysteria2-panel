import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FixtureTlsOverrides extends HttpOverrides {
  FixtureTlsOverrides(this.trust, this.certificate, this.port);
  final SecurityContext trust;
  final String certificate;
  final int port;

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(trust);
    // Pin only this ephemeral fixture identity; production TLS is unchanged.
    client.badCertificateCallback = (cert, host, peerPort) =>
        host == '127.0.0.1' && peerPort == port && cert.pem == certificate;
    return client;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('HTTPS API never accepts a plaintext redirect response', () async {
    final directory = await Directory.systemTemp.createTemp(
      'h2-redirect-test-',
    );
    addTearDown(() => directory.delete(recursive: true));
    final certificate = '${directory.path}/certificate.pem';
    final key = '${directory.path}/key.pem';
    final generated = await Process.run('openssl', [
      'req',
      '-x509',
      '-newkey',
      'rsa:2048',
      '-nodes',
      '-days',
      '1',
      '-keyout',
      key,
      '-out',
      certificate,
      '-subj',
      '/CN=localhost',
      '-addext',
      'subjectAltName=DNS:localhost,IP:127.0.0.1',
    ]);
    expect(generated.exitCode, 0);
    final serverContext = SecurityContext()
      ..useCertificateChain(certificate)
      ..usePrivateKey(key);
    final trust = SecurityContext()..setTrustedCertificates(certificate);
    final plaintext = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final secure = await HttpServer.bindSecure(
      InternetAddress.loopbackIPv4,
      0,
      serverContext,
    );
    addTearDown(() => plaintext.close(force: true));
    addTearDown(() => secure.close(force: true));
    var plaintextRequests = 0;
    plaintext.listen((request) async {
      plaintextRequests++;
      await request.drain<void>();
      request.response.headers.contentType = ContentType.json;
      request.response.write(
        jsonEncode({
          'data': {'value': 'plaintext-response'},
        }),
      );
      await request.response.close();
    });
    secure.listen((request) async {
      await request.drain<void>();
      if (request.uri.path.endsWith('/auth/refresh')) {
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode({
            'data': {
              'accessToken': 'fixture-access',
              'refreshToken': 'fixture-refresh',
            },
          }),
        );
      } else {
        request.response.statusCode = HttpStatus.found;
        request.response.headers.contentType = ContentType.json;
        request.response.headers.set(
          HttpHeaders.locationHeader,
          'http://127.0.0.1:${plaintext.port}/plaintext',
        );
        request.response.write(
          jsonEncode({
            'data': {'value': 'redirect-response'},
          }),
        );
      }
      await request.response.close();
    });
    SharedPreferences.setMockInitialValues({
      'panel_base_url': 'https://127.0.0.1:${secure.port}',
      'panel_username': 'fixture-admin',
    });
    FlutterSecureStorage.setMockInitialValues({
      'mobile_refresh_token': 'fixture-refresh',
      'mobile_device_id': 'fixture-device',
    });
    final overrides = FixtureTlsOverrides(
      trust,
      await File(certificate).readAsString(),
      secure.port,
    );
    await HttpOverrides.runZoned(() async {
      final controller = AppController();
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(
        controller.state.session?.accessToken,
        'fixture-access',
        reason: controller.state.error,
      );
      await expectLater(
        controller.getJson('/private'),
        throwsA(isA<ApiException>()),
      );
      expect(plaintextRequests, 0);
    }, createHttpClient: overrides.createHttpClient);
  });
}
