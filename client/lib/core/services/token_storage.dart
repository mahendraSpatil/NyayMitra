import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Access + refresh tokens, in the platform keystore/keychain — never
/// SharedPreferences (plaintext) and never held only in memory (a
/// refresh token in memory alone wouldn't survive an app restart, and
/// Firebase's own sessions persisted across restarts; this should too).
class TokenStorage {
  static const _storage = FlutterSecureStorage();
  static const _accessKey = 'nyaymitra_access_token';
  static const _refreshKey = 'nyaymitra_refresh_token';

  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _accessKey, value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
  }

  Future<void> saveAccessToken(String accessToken) {
    return _storage.write(key: _accessKey, value: accessToken);
  }

  Future<String?> get accessToken => _storage.read(key: _accessKey);

  Future<String?> get refreshToken => _storage.read(key: _refreshKey);

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
