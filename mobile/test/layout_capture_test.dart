import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/design_fixture.dart';

class CaptureController extends DesignFixtureController {
  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    final nodeNames = ['私家车-美国-专线', '私家车1', '私家车2'];
    if (path.endsWith('/overview')) {
      return {
        'serviceStatus': 'active',
        'panelVersion': '0.39.58',
        'users': {'total': 365, 'onlineDevices': 55},
        'nodes': {'online': 3, 'total': 3},
        'traffic': {
          'txBytes': (518.1 * 1073741824).round(),
          'rxBytes': (4.2 * 1099511627776).round(),
        },
        'resources': {'tcpCongestionControl': 'bbr'},
        'trafficBudgets': [
          for (var i = 0; i < 3; i++)
            {
              'originId': i == 1 ? 'local:test' : 'node:n$i',
              'kind': i == 1 ? 'local' : 'remote',
              'name': nodeNames[i],
              'serverIp': '155.103.119.${[58, 90, 96][i]}',
              'onlineState': 'fresh',
              'onlineDevices': [7, 33, 16][i],
              'budget': {
                'percent': [15.1, 1.4, 1.0][i],
                'usedBytes': ([463.8, 42.1, 31.9][i] * 1073741824).round(),
                'limitBytes': 3 * 1099511627776,
                'nextResetDate': '2026-12-18',
              },
            },
        ],
      };
    }
    if (path.endsWith('/nodes')) {
      return {
        'observedAt': 1,
        'total': 3,
        'online': 3,
        'items': [
          for (var i = 0; i < 3; i++)
            {
              'nodeId': i == 1 ? 'local' : 'n$i',
              'tier': i == 0 ? 'premium' : 'standard',
              'originId': i == 1 ? 'local:test' : 'node:n$i',
              'name': nodeNames[i],
              'status': 'online',
              'onlineDevices': [7, 33, 16][i],
              'observedIp': '155.103.119.${[58, 90, 96][i]}',
              'canDisconnect': i != 1,
              'canDeletePairing': i != 1,
            },
        ],
      };
    }
    if (path.endsWith('/server-monitor')) {
      return {
        'servers': {
          'n0': {'fresh': true, 'cpu': 23, 'memory': 46, 'disk': 38},
        },
        'local': {'fresh': true, 'cpu': 23, 'memory': 46, 'disk': 38},
      };
    }
    if (path.endsWith('/settings')) {
      return {
        'certificate': {'level': 'ok'},
      };
    }
    if (path.endsWith('/users')) {
      return {
        'subscriptionManagement': true,
        'items': [
          for (var i = 0; i < 8; i++)
            {
              'id': 8 - i,
              'name': '示例用户 ${(i + 1).toString().padLeft(2, '0')}',
              'enabled': i != 2 && i != 5,
              'generation': 0,
              'userType': 0,
              'deviceLimit': 3,
              'onlineDevices': 2,
              'trafficLimitBytes': 100 * 1073741824,
              'usedBytes':
                  ([42.1, 15.3, 78.6, 8.9, 120.4, 5.2, 66.7, 22.0][i] *
                          1073741824)
                      .round(),
              'trafficPercent': [
                42.1,
                15.3,
                39.3,
                17.8,
                40.1,
                10.4,
                33.4,
                22.0,
              ][i],
              'expiresAt': 1797609600,
            },
        ],
      };
    }
    if (path.endsWith('/subscription')) {
      return {
        'exists': true,
        'enabled': true,
        'url': 'https://panel.example.com/sub/example',
        'generation': 0,
        'revision': 'example',
        'userType': 0,
        'subscriptionId': 1,
        'usesDefaults': false,
        'nodes': [{}, {}, {}],
      };
    }
    if (path.contains('/line-monitor')) {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      return {
        'network': {
          for (var node = 0; node < 3; node++)
            (node == 1 ? 'local:test' : 'node:n$node'): {
              'fresh': true,
              'rx': [23100, 2381250, 546250][node],
              'tx': [9837, 2557500, 577500][node],
              'points': [
                for (var i = 0; i < 60; i++)
                  {
                    'at': now - (59 - i) * 5,
                    'rx': 2000000 + (i % 9) * 400000,
                    'tx': 2400000 + (i % 7) * 300000,
                  },
              ],
            },
        },
      };
    }
    if (path.endsWith('/subscriptions')) {
      return {
        'items': [
          for (var i = 1; i <= 8; i++)
            {
              'id': i,
              'user_id': i,
              'user_name': '示例用户 ${i.toString().padLeft(2, '0')}',
              'user_type': i % 2,
              'enabled': true,
            },
        ],
      };
    }
    return super.getJson(path);
  }
}

void main() {
  for (final width in [412.0, 320.0]) {
    testWidgets('capture five pages at $width', (tester) async {
      SharedPreferences.setMockInitialValues({});
      PackageInfo.setMockInitialValues(
        appName: 'Panel',
        packageName: 'test',
        version: '0.5.5',
        buildNumber: '41',
        buildSignature: '',
      );
      await tester.runAsync(() async {
        await (FontLoader(
          'MaterialIcons',
        )..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'))).load();
        final bytes = ByteData.sublistView(
          await File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
              .readAsBytes(),
        );
        for (final family in ['Roboto', 'Ahem']) {
          await (FontLoader(family)..addFont(Future.value(bytes))).load();
        }
      });
      tester.view.physicalSize = Size(width, width == 412 ? 895 : 740);
      tester.view.devicePixelRatio = 1;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appControllerProvider.overrideWith((_) => CaptureController()),
          ],
          child: const Hysteria2ManagerApp(),
        ),
      );
      await tester.pumpAndSettle();
      final names = ['总览', '节点管理', '用户管理', '订阅管理', '设置'];
      for (var i = 0; i < names.length; i++) {
        await tester.tap(
          find.descendant(
            of: find.byType(AppBottomDock),
            matching: find.text(names[i]),
          ),
        );
        await tester.pumpAndSettle();
        if (i == 1) {
          await tester.tap(find.text('私家车-美国-专线').first);
          await tester.pumpAndSettle();
        }
        if (i == 2) {
          await tester.tap(find.text('示例用户 01').first);
          await tester.pumpAndSettle();
        }
        if (i == 3) {
          await tester.tap(find.text('示例用户 01').first);
          await tester.pumpAndSettle();
        }
        if (i == 3) {
          await tester.tap(find.text('更多⌄'));
          await tester.pumpAndSettle();
        }
        expect(tester.takeException(), isNull);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('../../output/ui-audit/$width-page-$i.png'),
        );
        if (i == 3) {
          await tester.tapAt(const Offset(5, 5));
          await tester.pumpAndSettle();
        }
      }
      await tester.pumpWidget(const SizedBox.shrink());
    }, skip: !const bool.fromEnvironment('CAPTURE_UI'));
  }
}
