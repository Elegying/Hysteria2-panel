import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class AppSession {
  const AppSession({
    required this.baseUrl,
    required this.username,
    required this.accessToken,
    required this.refreshToken,
    required this.deviceId,
  });

  final String baseUrl;
  final String username;
  final String accessToken;
  final String refreshToken;
  final String deviceId;

  AppSession copyWith({String? accessToken, String? refreshToken}) =>
      AppSession(
        baseUrl: baseUrl,
        username: username,
        accessToken: accessToken ?? this.accessToken,
        refreshToken: refreshToken ?? this.refreshToken,
        deviceId: deviceId,
      );
}

class PanelAccount {
  const PanelAccount({
    required this.name,
    this.baseUrl = '',
    this.username = '',
    this.password = '',
    this.session,
  });
  final String name;
  final String baseUrl;
  final String username;
  final String password;
  final AppSession? session;

  PanelAccount copyWith({
    String? name,
    AppSession? session,
    bool clearSession = false,
  }) => PanelAccount(
    name: name ?? this.name,
    baseUrl: baseUrl,
    username: username,
    password: password,
    session: clearSession ? null : session ?? this.session,
  );

  Map<String, dynamic> toJson() => {
    'name': name,
    'baseUrl': baseUrl,
    'username': username,
    'password': password,
    if (session != null) 'refreshToken': session!.refreshToken,
    if (session != null) 'deviceId': session!.deviceId,
  };

  factory PanelAccount.fromJson(Map<String, dynamic> json) {
    final baseUrl = json['baseUrl'] as String;
    final username = json['username'] as String;
    final token = json['refreshToken'] as String?;
    return PanelAccount(
      name: json['name'] as String,
      baseUrl: baseUrl,
      username: username,
      password: json['password'] as String? ?? '',
      session: token == null
          ? null
          : AppSession(
              baseUrl: baseUrl,
              username: username,
              accessToken: '',
              refreshToken: token,
              deviceId: json['deviceId'] as String,
            ),
    );
  }
}

const emptyPanels = [PanelAccount(name: '面板1'), PanelAccount(name: '面板2')];

class AppState {
  const AppState({
    this.initializing = true,
    this.working = false,
    this.session,
    this.error,
    this.panels = emptyPanels,
    this.activePanel = 0,
    this.contextRevision = 0,
  });

  final List<PanelAccount> panels;
  final int activePanel;
  final int contextRevision;
  final bool initializing;
  final bool working;
  final AppSession? session;
  final String? error;

  AppState copyWith({
    List<PanelAccount>? panels,
    int? activePanel,
    int? contextRevision,
    bool? initializing,
    bool? working,
    AppSession? session,
    bool clearSession = false,
    String? error,
    bool clearError = false,
  }) => AppState(
    panels: panels ?? this.panels,
    activePanel: activePanel ?? this.activePanel,
    contextRevision: contextRevision ?? this.contextRevision,
    initializing: initializing ?? this.initializing,
    working: working ?? this.working,
    session: clearSession ? null : session ?? this.session,
    error: clearError ? null : error ?? this.error,
  );
}

class ApiException implements Exception {
  const ApiException(this.message, {this.code, this.statusCode});

  final String message;
  final String? code;
  final int? statusCode;

  @override
  String toString() => message;
}

final appControllerProvider = StateNotifierProvider<AppController, AppState>((
  ref,
) {
  final controller = AppController();
  unawaited(controller.initialize());
  return controller;
});

class AppController extends StateNotifier<AppState> {
  AppController({
    Dio Function(String)? dioFactory,
    FlutterSecureStorage? storage,
  }) : _dioFactory = dioFactory ?? _createDio,
       _storage =
           storage ?? const FlutterSecureStorage(aOptions: AndroidOptions()),
       super(const AppState());

  final FlutterSecureStorage _storage;
  static const _panelsKey = 'mobile_panel_accounts_v1';
  static const _refreshKey = 'mobile_refresh_token';
  static const _deviceKey = 'mobile_device_id';
  static const _baseUrlKey = 'panel_base_url';
  static const _usernameKey = 'panel_username';

  final Dio Function(String) _dioFactory;
  Dio? _dio;
  Future<bool>? _refreshFuture;
  int _sessionGeneration = 0;
  Future<void> _storageFuture = Future<void>.value();

  bool _isCurrent(int generation) =>
      mounted && generation == _sessionGeneration;

  Future<void> _persistSession(
    int generation,
    Future<void> Function() action, {
    Future<void> Function()? onFailure,
  }) {
    final work = _storageFuture.then((_) async {
      if (_isCurrent(generation)) await action();
    });
    _storageFuture = work.then<void>(
      (_) {},
      onError: (Object _, StackTrace _) {},
    );
    if (onFailure == null) return work;
    return work.catchError((Object error, StackTrace stack) async {
      await onFailure();
      Error.throwWithStackTrace(error, stack);
    });
  }

  Future<void> initialize() async {
    final generation = ++_sessionGeneration;
    try {
      final preferences = await SharedPreferences.getInstance();
      final saved = await _storage.read(key: _panelsKey);
      if (!_isCurrent(generation)) return;
      if (saved != null) {
        final document = jsonDecode(saved) as Map<String, dynamic>;
        final panels = (document['panels'] as List)
            .map(
              (value) => PanelAccount.fromJson(
                Map<String, dynamic>.from(value as Map),
              ),
            )
            .toList();
        if (panels.length != 2) throw const FormatException();
        final active = document['active'] as int;
        final session = panels[active].session;
        _dio = session == null ? null : _dioFactory(session.baseUrl);
        state = AppState(
          initializing: false,
          panels: panels,
          activePanel: active,
          session: session,
        );
        if (session != null) await _refreshTokens();
        return;
      }
      final baseUrl = preferences.getString(_baseUrlKey) ?? '';
      final username = preferences.getString(_usernameKey) ?? '';
      var deviceId = await _storage.read(key: _deviceKey);
      if (deviceId == null || deviceId.length < 8) {
        deviceId = const Uuid().v4();
        await _storage.write(key: _deviceKey, value: deviceId);
      }
      final refreshToken = await _storage.read(key: _refreshKey);
      if (!_isCurrent(generation)) return;
      if (baseUrl.isNotEmpty && username.isNotEmpty && refreshToken != null) {
        _dio = _dioFactory(baseUrl);
        state = AppState(
          initializing: false,
          session: AppSession(
            baseUrl: baseUrl,
            username: username,
            accessToken: '',
            refreshToken: refreshToken,
            deviceId: deviceId,
          ),
        );
        final panels = [...emptyPanels];
        panels[0] = PanelAccount(
          name: '面板1',
          baseUrl: baseUrl,
          username: username,
          session: state.session,
        );
        state = state.copyWith(panels: panels);
        if (await _refreshTokens() || !_isCurrent(generation)) return;
      }
      if (baseUrl.isNotEmpty &&
          username.isNotEmpty &&
          state.panels[0].baseUrl.isEmpty) {
        state = state.copyWith(
          panels: [
            PanelAccount(name: '面板1', baseUrl: baseUrl, username: username),
            emptyPanels[1],
          ],
        );
      }
      state = state.copyWith(initializing: false, clearSession: true);
    } on ApiException catch (error) {
      if (_isCurrent(generation)) {
        state = state.copyWith(initializing: false, error: error.message);
      }
    } catch (_) {
      if (_isCurrent(generation)) {
        state = const AppState(initializing: false, error: '无法读取本机安全存储，请重新登录');
      }
    }
  }

  /// Remember only connection details; authentication stays in secure storage.
  Future<({String address, String port, String username})?>
  rememberedLogin() async {
    final panel = state.panels[state.activePanel];
    if (panel.baseUrl.isNotEmpty) {
      final uri = Uri.parse(panel.baseUrl);
      return (
        address: Uri(scheme: uri.scheme, host: uri.host).toString(),
        port: uri.port.toString(),
        username: panel.username,
      );
    }
    if (await _storage.read(key: _panelsKey) != null) return null;
    final preferences = await SharedPreferences.getInstance();
    final uri = Uri.tryParse(preferences.getString(_baseUrlKey) ?? '');
    final username = preferences.getString(_usernameKey) ?? '';
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        username.isEmpty) {
      return null;
    }
    return (
      address: Uri(scheme: 'https', host: uri.host).toString(),
      port: uri.port.toString(),
      username: username,
    );
  }

  static Dio _createDio(String baseUrl) => Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
      sendTimeout: const Duration(seconds: 20),
      headers: const {'Accept': 'application/json'},
      followRedirects: false,
      validateStatus: (status) => status != null && status < 600,
    ),
  );

  static String normalizeBaseUrl(String address, int port) {
    var value = address.trim();
    if (value.isEmpty) throw const ApiException('请输入面板地址');
    if (!value.contains('://')) value = 'https://$value';
    final source = Uri.tryParse(value);
    if (source == null || source.host.isEmpty) {
      throw const ApiException('面板地址格式无效');
    }
    if (source.scheme != 'https') {
      throw const ApiException('移动端只允许连接 HTTPS 面板');
    }
    if (source.userInfo.isNotEmpty ||
        source.query.isNotEmpty ||
        source.fragment.isNotEmpty ||
        (source.path.isNotEmpty && source.path != '/')) {
      throw const ApiException('面板地址不能包含账号、路径、查询参数或片段');
    }
    final effectivePort = source.hasPort ? source.port : port;
    if (effectivePort < 1 || effectivePort > 65535) {
      throw const ApiException('面板端口无效');
    }
    return Uri(
      scheme: 'https',
      host: source.host,
      port: effectivePort,
    ).toString().replaceAll(RegExp(r'/$'), '');
  }

  Future<void> login({
    required String address,
    required int port,
    required String username,
    required String password,
    int? panelIndex,
    bool rememberPassword = true,
  }) async {
    if (username.trim().isEmpty) throw const ApiException('请输入面板账号');
    if (password.isEmpty) throw const ApiException('请输入面板密码');
    final baseUrl = normalizeBaseUrl(address, port);
    final target = panelIndex ?? state.activePanel;
    if (target < 0 || target > 1) throw const ApiException('面板位置无效');
    if (state.working) throw const ApiException('请等待当前操作完成');
    final other = state.panels[1 - target];
    if (other.baseUrl == baseUrl &&
        other.username == username.trim() &&
        other.session != null) {
      throw ApiException('此账号已在${other.name}登录，请直接切换');
    }
    state = state.copyWith(working: true);
    // A retained panel must finish token rotation before another login begins.
    if (panelIndex != null && _refreshFuture != null) {
      try {
        await _refreshFuture;
      } on ApiException {
        /* Keep recoverable session. */
      }
    }
    if (!mounted) return;
    final previousState = state;
    final previousDio = _dio;
    final generation = ++_sessionGeneration;
    _refreshFuture = null;
    state = state.copyWith(working: true, clearError: true);
    final dio = _dioFactory(baseUrl);
    AppSession? issuedSession;
    try {
      final capabilities = await dio.get('/api/v1/mobile/capabilities');
      if (capabilities.statusCode == 404) {
        throw const ApiException('面板版本暂不支持 App，请先将面板升级到 v0.38.0 或更高版本');
      }
      final capabilityData = _unwrap(capabilities);
      final features = (capabilityData['features'] as List? ?? const [])
          .map((value) => value.toString())
          .toSet();
      const requiredFeatures = {
        'local-node-control',
        'one-click-node-pairing',
        'node-realtime-traffic',
        'server-reboot',
        'domain-traffic-top10',
      };
      if (!features.containsAll(requiredFeatures)) {
        throw const ApiException('面板版本暂不支持当前 App，请先将面板升级到 v0.39.0 或更高版本');
      }
      var deviceId = await _storage.read(key: _deviceKey);
      if (deviceId == null || deviceId.length < 8) {
        deviceId = const Uuid().v4();
        await _storage.write(key: _deviceKey, value: deviceId);
      }
      final data = _unwrap(
        await dio.post(
          '/api/v1/mobile/auth/login',
          data: {
            'username': username.trim(),
            'password': password,
            'deviceId': deviceId,
            'deviceName': '${Platform.operatingSystem} Hysteria2管理',
          },
        ),
      );
      final session = AppSession(
        baseUrl: baseUrl,
        username: username.trim(),
        accessToken: data['accessToken'] as String,
        refreshToken: data['refreshToken'] as String,
        deviceId: deviceId,
      );
      issuedSession = session;
      final panels = [...state.panels];
      final replaced = panels[target].session;
      panels[target] = PanelAccount(
        name: panels[target].name,
        baseUrl: baseUrl,
        username: username.trim(),
        password: rememberPassword ? password : '',
        session: session,
      );
      await _persistSession(generation, () async {
        await _savePanels(panels, target);
      });
      if (!_isCurrent(generation)) {
        await _revokeSession(dio, session.accessToken);
        throw const ApiException('登录操作已结束');
      }
      _dio = dio;
      state = AppState(
        initializing: false,
        session: session,
        panels: panels,
        activePanel: target,
        contextRevision: state.contextRevision + 1,
      );
      if (replaced != null && replaced.accessToken != session.accessToken) {
        unawaited(
          _revokeSession(_dioFactory(replaced.baseUrl), replaced.accessToken),
        );
      }
    } on DioException catch (error) {
      if (_isCurrent(generation)) {
        _dio = previousDio;
        state = previousState.copyWith(working: false);
      }
      throw ApiException(_networkMessage(error));
    } on ApiException {
      if (_isCurrent(generation)) {
        _dio = previousDio;
        state = previousState.copyWith(working: false);
      }
      rethrow;
    } catch (_) {
      if (_isCurrent(generation)) {
        _dio = previousDio;
        state = previousState.copyWith(working: false);
      }
      if (issuedSession != null) {
        await _revokeSession(dio, issuedSession.accessToken);
      }
      throw const ApiException('登录信息未能保存，请重试');
    }
  }

  Future<void> logout() async {
    final previous = state;
    final session = state.session;
    final dio = _dio;
    final generation = ++_sessionGeneration;
    _dio = null;
    _refreshFuture = null;
    final panels = [...state.panels];
    panels[state.activePanel] = panels[state.activePanel].copyWith(
      clearSession: true,
    );
    state = state.copyWith(
      initializing: false,
      working: false,
      clearSession: true,
      panels: panels,
      contextRevision: state.contextRevision + 1,
    );
    try {
      await _persistSession(generation, () async {
        await _savePanels(panels, previous.activePanel);
        // The new document is authoritative even if obsolete key cleanup fails.
        try {
          await _storage.delete(key: _refreshKey);
        } catch (_) {}
      });
    } catch (_) {
      if (_isCurrent(generation)) {
        _dio = dio;
        state = previous.copyWith(
          working: false,
          contextRevision: state.contextRevision + 1,
        );
      }
      throw const ApiException('无法清除本机登录状态，请重试');
    }
    if (session != null && dio != null) {
      await _revokeSession(dio, session.accessToken);
    }
  }

  Future<void> _savePanels(List<PanelAccount> panels, int active) =>
      _storage.write(
        key: _panelsKey,
        value: jsonEncode({
          'active': active,
          'panels': panels.map((panel) => panel.toJson()).toList(),
        }),
      );

  Future<void> selectPanel(int index) async {
    if (index < 0 || index > 1 || state.working || index == state.activePanel) {
      return;
    }
    state = state.copyWith(working: true);
    try {
      final refresh = _refreshFuture;
      if (refresh != null) {
        try {
          await refresh;
        } on ApiException {
          /* Offline panel remains saved. */
        }
      }
      if (!mounted) return;
      final generation = _sessionGeneration;
      await _persistSession(generation, () => _savePanels(state.panels, index));
      if (!_isCurrent(generation)) return;
      ++_sessionGeneration;
      _refreshFuture = null;
      final session = state.panels[index].session;
      _dio = session == null ? null : _dioFactory(session.baseUrl);
      state = state.copyWith(
        activePanel: index,
        session: session,
        clearSession: session == null,
        working: false,
        clearError: true,
        contextRevision: state.contextRevision + 1,
      );
    } catch (_) {
      if (mounted) state = state.copyWith(working: false);
      throw const ApiException('无法保存面板切换，请重试');
    }
  }

  Future<void> renamePanel(int index, String name) async {
    final trimmed = name.trim();
    if (trimmed.isEmpty || trimmed.length > 24) {
      throw const ApiException('面板名称请输入 1 至 24 个字符');
    }
    await _editPanel(index, (panel) => panel.copyWith(name: trimmed));
  }

  Future<void> forgetPanel(int index) async {
    final old = state.panels[index].session;
    await _editPanel(
      index,
      (_) => PanelAccount(name: '面板${index + 1}'),
      forget: true,
    );
    if (old != null) {
      unawaited(_revokeSession(_dioFactory(old.baseUrl), old.accessToken));
    }
  }

  Future<void> _editPanel(
    int index,
    PanelAccount Function(PanelAccount) edit, {
    bool forget = false,
  }) async {
    if (state.working) throw const ApiException('请等待当前操作完成');
    state = state.copyWith(working: true);
    try {
      if (_refreshFuture != null) {
        try {
          await _refreshFuture;
        } on ApiException {
          /* Keep other panel usable. */
        }
      }
      final generation = _sessionGeneration;
      final panels = [...state.panels];
      panels[index] = edit(panels[index]);
      await _persistSession(generation, () async {
        await _savePanels(panels, state.activePanel);
        if (forget) {
          // Remove legacy hints too, so a deleted account cannot reappear.
          try {
            final preferences = await SharedPreferences.getInstance();
            await preferences.remove(_baseUrlKey);
            await preferences.remove(_usernameKey);
            await _storage.delete(key: _refreshKey);
          } catch (_) {
            /* The secure document remains authoritative. */
          }
        }
      });
      if (!_isCurrent(generation)) return;
      final clear = forget && index == state.activePanel;
      if (clear) {
        ++_sessionGeneration;
        _dio = null;
        _refreshFuture = null;
      }
      state = state.copyWith(
        panels: panels,
        working: false,
        clearSession: clear,
        contextRevision: state.contextRevision + (clear ? 1 : 0),
      );
    } catch (_) {
      if (mounted) state = state.copyWith(working: false);
      throw const ApiException('无法保存面板信息，请重试');
    }
  }

  static Future<void> _revokeSession(Dio dio, String accessToken) async {
    if (accessToken.isNotEmpty) {
      try {
        await dio.post(
          '/api/v1/mobile/auth/logout',
          data: const <String, Object?>{},
          options: Options(headers: {'Authorization': 'Bearer $accessToken'}),
        );
      } catch (_) {
        // Local logout must still complete when the panel is unreachable.
      }
    }
  }

  Future<Map<String, dynamic>> getJson(String path) => _request('GET', path);

  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) => _request('POST', path, data: data);

  Future<Map<String, dynamic>> patchJson(
    String path,
    Map<String, dynamic> data,
  ) => _request('PATCH', path, data: data);

  Future<Map<String, dynamic>> deleteJson(
    String path,
    Map<String, dynamic> data,
  ) => _request('DELETE', path, data: data);

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? data,
    bool retryAfterRefresh = true,
  }) async {
    if (state.working) throw const ApiException('正在更新面板，请稍后重试');
    final session = state.session;
    final dio = _dio;
    final generation = _sessionGeneration;
    if (session == null || dio == null) throw const ApiException('请重新登录');
    try {
      final response = await dio.request(
        path,
        data: data,
        options: Options(
          method: method,
          // These operations drain sessions before settling and stopping them.
          // Match the panel's maintenance deadline instead of the normal 20s.
          receiveTimeout:
              method == 'POST' &&
                  const {
                    '/api/v1/mobile/service/stop',
                    '/api/v1/mobile/service/restart',
                    '/api/v1/mobile/nodes/local/disable',
                    '/api/v1/mobile/system/reboot',
                  }.contains(path)
              ? const Duration(minutes: 15)
              : null,
          headers: {'Authorization': 'Bearer ${session.accessToken}'},
        ),
      );
      if (!_isCurrent(generation)) throw const ApiException('登录状态已改变，请重试');
      if (response.statusCode == 401 && retryAfterRefresh) {
        if (state.session?.accessToken != session.accessToken ||
            await _refreshTokens()) {
          if (!_isCurrent(generation)) throw const ApiException('登录状态已改变，请重试');
          return await _request(
            method,
            path,
            data: data,
            retryAfterRefresh: false,
          );
        }
      }
      return _unwrap(response);
    } on DioException catch (error) {
      throw ApiException(_networkMessage(error));
    }
  }

  Future<bool> _refreshTokens() {
    final inFlight = _refreshFuture;
    if (inFlight != null) return inFlight;
    late final Future<bool> future;
    future = _performRefresh().whenComplete(() {
      if (identical(_refreshFuture, future)) _refreshFuture = null;
    });
    _refreshFuture = future;
    return future;
  }

  Future<bool> _performRefresh() async {
    final session = state.session;
    final dio = _dio;
    final generation = _sessionGeneration;
    if (session == null || dio == null || session.refreshToken.isEmpty) {
      return false;
    }
    try {
      final data = _unwrap(
        await dio.post(
          '/api/v1/mobile/auth/refresh',
          data: {'refreshToken': session.refreshToken},
        ),
      );
      final updated = session.copyWith(
        accessToken: data['accessToken'] as String,
        refreshToken: data['refreshToken'] as String,
      );
      final panels = [...state.panels];
      panels[state.activePanel] = panels[state.activePanel].copyWith(
        session: updated,
      );
      await _persistSession(generation, () async {
        await _savePanels(panels, state.activePanel);
      }, onFailure: () => _revokeSession(dio, updated.accessToken));
      if (!_isCurrent(generation)) {
        await _revokeSession(dio, updated.accessToken);
        return false;
      }
      state = state.copyWith(
        session: updated,
        panels: panels,
        initializing: false,
        clearError: true,
      );
      return true;
    } on DioException catch (error) {
      if (!_isCurrent(generation)) return false;
      throw ApiException(_networkMessage(error));
    } on ApiException catch (error) {
      if (!_isCurrent(generation)) return false;
      if (error.statusCode != 401) rethrow;
      await logout();
      return false;
    } catch (_) {
      if (!_isCurrent(generation)) return false;
      throw const ApiException('无法恢复登录状态，请稍后重试');
    }
  }

  static Map<String, dynamic> _unwrap(Response<dynamic> response) {
    final body = response.data;
    if (body is! Map) {
      throw ApiException('服务器返回了无法识别的数据', statusCode: response.statusCode);
    }
    final map = Map<String, dynamic>.from(body);
    final error = map['error'];
    if (response.statusCode == null ||
        response.statusCode! >= 300 ||
        error != null) {
      if (error is Map) {
        throw ApiException(
          error['message']?.toString() ?? '操作未完成',
          code: error['code']?.toString(),
          statusCode: response.statusCode,
        );
      }
      throw ApiException(
        '操作未完成（${response.statusCode ?? '未知状态'}）',
        statusCode: response.statusCode,
      );
    }
    final data = map['data'];
    if (data is! Map) {
      throw ApiException('服务器返回了无法识别的数据', statusCode: response.statusCode);
    }
    for (final field in const ['items', 'trafficBudgets']) {
      if (data.containsKey(field) &&
          (data[field] is! List ||
              (data[field] as List).any((item) => item is! Map))) {
        throw ApiException('服务器返回了无法识别的数据', statusCode: response.statusCode);
      }
    }
    return Map<String, dynamic>.from(data);
  }

  static String _networkMessage(DioException error) {
    if (error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout) {
      return '连接超时，请检查面板地址、端口和网络';
    }
    if (error.type == DioExceptionType.badCertificate) {
      return '面板 HTTPS 证书无效或不受系统信任';
    }
    if (error.type == DioExceptionType.connectionError) {
      return '无法连接面板，请检查地址、端口和 HTTPS 配置';
    }
    return '网络请求失败，请稍后重试';
  }
}
