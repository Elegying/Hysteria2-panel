import 'package:hysteria2_manager/core/app_controller.dart';

class DesignFixtureController extends AppController {
  DesignFixtureController({bool loggedIn = true}) {
    state = AppState(
      initializing: false,
      session: loggedIn
          ? const AppSession(
              baseUrl: 'https://panel.example.com',
              username: '预览管理员',
              accessToken: 'fixture',
              refreshToken: 'fixture',
              deviceId: 'fixture',
            )
          : null,
    );
  }

  @override
  Future<Map<String, dynamic>> getJson(String path) async {
    if (path.endsWith('/overview')) {
      return {
        'serviceStatus': 'active',
        'panelName': 'H2 私有网络',
        'panelVersion': '0.39.6',
        'users': {'total': 128, 'onlineDevices': 36},
        'nodes': {'online': 3, 'total': 3},
        'traffic': {'totalBytes': 268435456000},
        'resources': {
          'cpuPercent': 12,
          'memoryPercent': 28,
          'diskPercent': 36,
          'uptime': '12 天',
        },
        'trafficBudgets': [
          {
            'name': '主节点',
            'onlineDevices': 24,
            'budget': {
              'percent': 25,
              'usedBytes': 268435456000,
              'limitBytes': 1073741824000,
            },
          },
        ],
      };
    }
    if (path.endsWith('/nodes')) {
      return {
        'total': 2,
        'online': 2,
        'statusCounts': {},
        'observedAt': 1,
        'items': [
          for (final name in ['主节点', '边缘节点'])
            {
              'nodeId': name == '主节点' ? 'local' : 'edge',
              'name': name,
              'status': 'online',
              'observedIp': '192.0.2.1',
              'expectedIp': '192.0.2.1',
              'onlineDevices': 18,
              'totalBytes': 12345,
            },
        ],
      };
    }
    return {
      'items': [
        for (var i = 1; i <= 4; i++)
          {
            'id': i,
            'name': '示例用户 $i',
            'enabled': true,
            'generation': 0,
            'deviceLimit': 3,
            'trafficLimitBytes': 107374182400,
            'allowUdp443': false,
            'onlineDevices': 2,
            'usedBytes': i * 1073741824,
            'txBytes': 1073741824,
            'rxBytes': 1073741824,
            'trafficPercent': i.toDouble(),
          },
      ],
    };
  }
}
