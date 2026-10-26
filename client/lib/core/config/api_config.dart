import 'package:flutter/foundation.dart'
    show TargetPlatform, defaultTargetPlatform, kIsWeb;

const _devHost = 'localhost';
const _port = 8000;

/// Build-time override for a physical device. Pass
/// `--dart-define=API_BASE_URL=http://127.0.0.1:8000` for a phone on USB
/// with `adb reverse tcp:8000 tcp:8000` running (README.md), or
/// `http://<laptop-LAN-IP>:8000` for a phone on the same Wi-Fi as the
/// backend. String.fromEnvironment resolves at compile time, so this is
/// empty (never null) when the define isn't passed, and web/desktop/
/// emulator builds fall through to the existing per-platform localhost
/// logic unchanged.
const _baseUrlOverride = String.fromEnvironment('API_BASE_URL');

/// Every backend call in the app goes through this, directly or via
/// ApiClient/WsClient — one place that knows how a given platform reaches
/// this machine, instead of a hardcoded 'localhost' baked into every
/// service file (which is what this app had until step 5 of the Postgres
/// migration, NyayMitra.md).
String get apiBaseUrl {
  if (_baseUrlOverride.isNotEmpty) return '$_baseUrlOverride/api/v2';
  final host = _host();
  return 'http://$host:$_port/api/v2';
}

String get wsBaseUrl {
  if (_baseUrlOverride.isNotEmpty) {
    return '${_toWsScheme(_baseUrlOverride)}/api/v2';
  }
  final host = _host();
  return 'ws://$host:$_port/api/v2';
}

/// Derives the WebSocket URL from the same override rather than reading a
/// second dart-define — one value to pass, not two that could drift apart.
String _toWsScheme(String httpUrl) {
  if (httpUrl.startsWith('https://')) return 'wss://${httpUrl.substring(8)}';
  if (httpUrl.startsWith('http://')) return 'ws://${httpUrl.substring(7)}';
  return httpUrl;
}

String _host() {
  if (kIsWeb) return _devHost;
  // The Android emulator's own loopback interface is not the host
  // machine's — 10.0.2.2 is the special alias the emulator provides for
  // that. A physical Android device needs the host's real LAN IP instead,
  // via the API_BASE_URL override above.
  if (defaultTargetPlatform == TargetPlatform.android) return '10.0.2.2';
  return _devHost;
}
