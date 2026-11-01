import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart'
    show TargetPlatform, debugPrint, defaultTargetPlatform, kIsWeb;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const _devHost = 'localhost';
const _port = 8000;

/// Build-time default server, e.g.
/// `--dart-define=API_BASE_URL=https://nyaymitra.example.com` (no
/// `/api/v2` suffix). Empty when not passed.
const _baseUrlOverride = String.fromEnvironment('API_BASE_URL');

/// Where the demo laptop publishes its current public address
/// (demo/start_demo.ps1 writes `server.json` to this branch every time
/// the tunnel address changes). Empty SERVER_DISCOVERY_REPO turns
/// automatic discovery off.
const _discoveryRepo = String.fromEnvironment(
  'SERVER_DISCOVERY_REPO',
  defaultValue: 'mahendraSpatil/NyayMitra',
);
const _discoveryBranch = String.fromEnvironment(
  'SERVER_DISCOVERY_BRANCH',
  defaultValue: 'demo-server',
);

/// Which backend the app talks to, in priority order:
/// 1. an address typed in by hand (sign-in screen -> server icon) — an
///    explicit override, so automatic discovery leaves it alone;
/// 2. the address discovered automatically from [_discoveryRepo]
///    (refreshed at launch and whenever the server stops answering);
/// 3. the build-time API_BASE_URL;
/// 4. the per-platform localhost default (development).
class ServerConfig {
  ServerConfig._();

  static const _storage = FlutterSecureStorage();
  static const _manualKey = 'nyaymitra_server_manual';
  static const _discoveredKey = 'nyaymitra_server_discovered';
  // Builds before automatic discovery stored a hand-typed tunnel address
  // here. Those addresses expire, so it's dropped on upgrade: updated
  // phones start in automatic mode instead of stuck on a dead address.
  static const _legacyKey = 'nyaymitra_server_url';

  static String? _manual;
  static String? _discovered;
  static Future<bool>? _refreshInFlight;
  static DateTime? _lastRefresh;

  /// Call once in main() before runApp.
  static Future<void> load() async {
    try {
      _manual = _nonEmpty(await _storage.read(key: _manualKey));
      _discovered = _nonEmpty(await _storage.read(key: _discoveredKey));
      await _storage.delete(key: _legacyKey);
    } catch (_) {
      // Storage unavailable — fall back to defaults.
    }
  }

  /// The server root currently in use, without `/api/v2`.
  static String get current {
    if (_manual != null) return _manual!;
    if (_discovered != null) return _discovered!;
    if (_baseUrlOverride.isNotEmpty) return normalize(_baseUrlOverride);
    return 'http://${_host()}:$_port';
  }

  static bool get isManual => _manual != null;

  static bool get autoEnabled => _manual == null && _discoveryRepo.isNotEmpty;

  /// Typed-in override.
  static Future<void> saveManual(String url) async {
    final value = normalize(url);
    await _storage.write(key: _manualKey, value: value);
    _manual = value;
  }

  /// Back to automatic: drop the override and look the address up now.
  static Future<bool> useAutomatic() async {
    await _storage.delete(key: _manualKey);
    _manual = null;
    _lastRefresh = null;
    return refresh();
  }

  /// Looks up the published address. Returns true if it changed (callers
  /// retry their request then). Single-flight, and at most once every 10
  /// seconds, so a burst of failing requests doesn't hammer GitHub.
  static Future<bool> refresh() {
    if (!autoEnabled) return Future.value(false);
    final last = _lastRefresh;
    if (_refreshInFlight == null &&
        last != null &&
        DateTime.now().difference(last) < const Duration(seconds: 10)) {
      return Future.value(false);
    }
    return _refreshInFlight ??= _doRefresh().whenComplete(() {
      _refreshInFlight = null;
      _lastRefresh = DateTime.now();
    });
  }

  static Future<bool> _doRefresh() async {
    final found = await _fetchPublished();
    if (found == null || found == _discovered) return false;
    _discovered = found;
    try {
      await _storage.write(key: _discoveredKey, value: found);
    } catch (_) {}
    debugPrint('ServerConfig: server address is now $found');
    return true;
  }

  static Future<String?> _fetchPublished() async {
    // GitHub's API first: it isn't held in a CDN cache, so a new address
    // is visible within seconds. raw.githubusercontent.com (cached up to
    // ~5 min, hence the cache-busting query) is the fallback for when the
    // API's unauthenticated rate limit is hit.
    final now = DateTime.now().millisecondsSinceEpoch;
    final sources = [
      (
        Uri.parse(
          'https://api.github.com/repos/$_discoveryRepo/contents/server.json'
          '?ref=$_discoveryBranch',
        ),
        const {'Accept': 'application/vnd.github.raw+json'},
      ),
      (
        Uri.parse(
          'https://raw.githubusercontent.com/$_discoveryRepo/'
          '$_discoveryBranch/server.json?t=$now',
        ),
        const <String, String>{},
      ),
    ];
    for (final (uri, headers) in sources) {
      try {
        final response = await http
            .get(uri, headers: headers)
            .timeout(const Duration(seconds: 8));
        if (response.statusCode != 200) continue;
        final json = jsonDecode(response.body);
        final url = json is Map ? json['url'] : null;
        if (url is! String) continue;
        final value = normalize(url);
        // Only ever an https server — never let a bad file point the app
        // at plain http.
        if (!value.startsWith('https://') || Uri.tryParse(value) == null) {
          continue;
        }
        return value;
      } catch (_) {
        continue;
      }
    }
    return null;
  }

  /// Accepts what people actually paste: missing scheme, trailing slash,
  /// or a trailing /api/v2 (which would otherwise double up).
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

  static String? _nonEmpty(String? value) =>
      (value == null || value.isEmpty) ? null : value;
}

/// Runs [send] (which must read [apiBaseUrl] itself, so a retry picks up
/// a new address). If the server can't be reached — no such host, refused,
/// or Cloudflare's 530/502 for a tunnel that has gone away — looks up the
/// current published address and, if it moved, tries once more there.
Future<http.Response> sendWithFailover(
  Future<http.Response> Function() send,
) async {
  try {
    final response = await send();
    if ((response.statusCode == 530 || response.statusCode == 502) &&
        await ServerConfig.refresh()) {
      return send();
    }
    return response;
  } on http.ClientException {
    if (await ServerConfig.refresh()) return send();
    rethrow;
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
