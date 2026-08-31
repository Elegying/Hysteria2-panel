import 'dart:async';
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

class AppState {
  const AppState({
    this.initializing = true,
    this.working = false,
    this.session,
    this.error,
  });

  final bool initializing;
  final bool working;
  final AppSession? session;
  final String? error;

  AppState copyWith({
    bool? initializing,
    bool? working,
    AppSession? session,
    bool clearSession = false,
    String? error,
    bool clearError = false,
  }) => AppState(
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
  AppController() : super(const AppState());

  static const _storage = FlutterSecureStorage(aOptions: AndroidOptions());
  static const _refreshKey = 'mobile_refresh_token';
  static const _deviceKey = 'mobile_device_id';
  static const _baseUrlKey = 'panel_base_url';
  static const _usernameKey = 'panel_username';

  Dio? _dio;
  Future<bool>? _refreshFuture;

  Future<void> initialize() async {
    try {
      final preferences = await SharedPreferences.getInstance();
      final baseUrl = preferences.getString(_baseUrlKey) ?? '';
      final username = preferences.getString(_usernameKey) ?? '';
      var deviceId = await _storage.read(key: _deviceKey);
      if (deviceId == null || deviceId.length < 8) {
        deviceId = const Uuid().v4();
        await _storage.write(key: _deviceKey, value: deviceId);
      }
      final refreshToken = await _storage.read(key: _refreshKey);
      if (baseUrl.isNotEmpty && username.isNotEmpty && refreshToken != null) {
        _dio = _createDio(baseUrl);
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
        if (await _refreshTokens()) return;
      }
      state = const AppState(initializing: false);
    } catch (_) {
      state = const AppState(initializing: false, error: '无法读取本机安全存储，请重新登录');
    }
  }

  static Dio _createDio(String baseUrl) => Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
      sendTimeout: const Duration(seconds: 20),
      headers: const {'Accept': 'application/json'},
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
    if (port < 1 || port > 65535) throw const ApiException('面板端口无效');
    return Uri(
      scheme: 'https',
      host: source.host,
      port: source.hasPort ? source.port : port,
    ).toString().replaceAll(RegExp(r'/$'), '');
  }

  Future<void> login({
    required String address,
    required int port,
    required String username,
    required String password,
  }) async {
    if (username.trim().isEmpty) throw const ApiException('请输入面板账号');
    if (password.isEmpty) throw const ApiException('请输入面板密码');
    final baseUrl = normalizeBaseUrl(address, port);
    state = state.copyWith(working: true, clearError: true);
    try {
      final dio = _createDio(baseUrl);
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
        'node-realtime-traffic',
        'server-reboot',
      };
      if (!features.containsAll(requiredFeatures)) {
        throw const ApiException('面板版本暂不支持当前 App，请先将面板升级到 v0.38.0 或更高版本');
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
      _dio = dio;
      final preferences = await SharedPreferences.getInstance();
      await preferences.setString(_baseUrlKey, baseUrl);
      await preferences.setString(_usernameKey, username.trim());
      await _storage.write(key: _refreshKey, value: session.refreshToken);
      state = AppState(initializing: false, session: session);
    } on DioException catch (error) {
      state = state.copyWith(working: false);
      throw ApiException(_networkMessage(error));
    } on ApiException {
      state = state.copyWith(working: false);
      rethrow;
    } catch (_) {
      state = state.copyWith(working: false);
      throw const ApiException('登录失败，请稍后重试');
    }
  }

  Future<void> logout() async {
    final session = state.session;
    if (session != null && session.accessToken.isNotEmpty) {
      try {
        await _dio?.post(
          '/api/v1/mobile/auth/logout',
          data: const <String, Object?>{},
          options: Options(
            headers: {'Authorization': 'Bearer ${session.accessToken}'},
          ),
        );
      } catch (_) {
        // Local logout must still complete when the panel is unreachable.
      }
    }
    await _storage.delete(key: _refreshKey);
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(_baseUrlKey);
    await preferences.remove(_usernameKey);
    _dio = null;
    state = const AppState(initializing: false);
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
    final session = state.session;
    final dio = _dio;
    if (session == null || dio == null) throw const ApiException('请重新登录');
    try {
      final response = await dio.request(
        path,
        data: data,
        options: Options(
          method: method,
          headers: {'Authorization': 'Bearer ${session.accessToken}'},
        ),
      );
      if (response.statusCode == 401 && retryAfterRefresh) {
        if (await _refreshTokens()) {
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
    final future = _performRefresh();
    _refreshFuture = future;
    future.whenComplete(() => _refreshFuture = null);
    return future;
  }

  Future<bool> _performRefresh() async {
    final session = state.session;
    final dio = _dio;
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
      await _storage.write(key: _refreshKey, value: updated.refreshToken);
      state = state.copyWith(
        session: updated,
        initializing: false,
        working: false,
      );
      return true;
    } catch (_) {
      await _storage.delete(key: _refreshKey);
      state = const AppState(initializing: false);
      return false;
    }
  }

  static Map<String, dynamic> _unwrap(Response<dynamic> response) {
    final body = response.data;
    if (body is! Map) throw const ApiException('服务器返回了无法识别的数据');
    final map = Map<String, dynamic>.from(body);
    final error = map['error'];
    if (response.statusCode == null ||
        response.statusCode! >= 400 ||
        error != null) {
      if (error is Map) {
        throw ApiException(
          error['message']?.toString() ?? '操作未完成',
          code: error['code']?.toString(),
          statusCode: response.statusCode,
        );
      }
      throw ApiException('操作未完成（${response.statusCode ?? '未知状态'}）');
    }
    final data = map['data'];
    return data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};
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
