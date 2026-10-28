import 'package:flutter/foundation.dart'
    show TargetPlatform, defaultTargetPlatform, kIsWeb;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _devHost = 'localhost';
const _port = 8000;

/// Build-time default for a physical device, e.g.
/// `--dart-define=API_BASE_URL=https://nyaymitra.example.com` (no
/// `/api/v2` suffix — it's added here). Empty when not passed.
const _baseUrlOverride = String.fromEnvironment('API_BASE_URL');

/// Which backend the app talks to, in priority order:
/// 1. a server address saved in the app (sign-in screen → server icon) —
///    so one APK works with a changing tunnel URL or a new cloud host
///    without a rebuild;
/// 2. the build-time API_BASE_URL;
/// 3. the per-platform localhost default (dev).
class ServerConfig {
  ServerConfig._();

  static const _storage = FlutterSecureStorage();
  static const _key = 'nyaymitra_server_url';
  static String? _runtime;

  /// Call once in main() before runApp.
  static Future<void> load() async {
    try {
      final saved = await _storage.read(key: _key);
      _runtime = (saved == null || saved.isEmpty) ? null : saved;
    } catch (_) {
      _runtime = null; // storage unavailable — fall back to defaults
    }
  }

  /// The server root currently in use, without `/api/v2`.
  static String get current {
    if (_runtime != null) return _runtime!;
    if (_baseUrlOverride.isNotEmpty) return normalize(_baseUrlOverride);
    return 'http://${_host()}:$_port';
  }

  static bool get isCustom => _runtime != null;

  static Future<void> save(String url) async {
    final value = normalize(url);
    await _storage.write(key: _key, value: value);
    _runtime = value;
  }

  static Future<void> reset() async {
    await _storage.delete(key: _key);
    _runtime = null;
  }

  /// Accepts what people actually paste: missing scheme, trailing slash,
  /// or a trailing /api/v2 (which would otherwise double up — a mistake
  /// this project has already hit once).
  static String normalize(String raw) {
    var url = raw.trim();
    if (url.isEmpty) return url;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://$url';
    }
    while (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    if (url.endsWith('/api/v2')) {
      url = url.substring(0, url.length - '/api/v2'.length);
    }
    return url;
  }
}

/// Every backend call in the app goes through this, directly or via
/// ApiClient/WsClient.
String get apiBaseUrl => '${ServerConfig.current}/api/v2';

String get wsBaseUrl => '${_toWsScheme(ServerConfig.current)}/api/v2';

String _toWsScheme(String httpUrl) {
  if (httpUrl.startsWith('https://')) return 'wss://${httpUrl.substring(8)}';
  if (httpUrl.startsWith('http://')) return 'ws://${httpUrl.substring(7)}';
  return httpUrl;
}

String _host() {
  if (kIsWeb) return _devHost;
  // The Android emulator reaches the host machine via 10.0.2.2.
  if (defaultTargetPlatform == TargetPlatform.android) return '10.0.2.2';
  return _devHost;
}
