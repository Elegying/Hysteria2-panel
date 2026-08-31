import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/core/formatters.dart';

void main() {
  test('formats traffic values for compact mobile cards', () {
    expect(formatBytes(0), '0 B');
    expect(formatBytes(1024), '1.0 KiB');
    expect(formatBytes(250 * 1024 * 1024 * 1024), '250 GiB');
  });

  test('normalizes the configured HTTPS panel endpoint', () {
    expect(
      AppController.normalizeBaseUrl('https://panel.example.com', 8443),
      'https://panel.example.com:8443',
    );
    expect(
      () => AppController.normalizeBaseUrl('http://panel.example.com', 8443),
      throwsA(isA<ApiException>()),
    );
  });
}
