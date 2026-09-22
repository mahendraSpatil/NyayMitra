import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/user_profile.dart';
import 'api_client.dart';
import 'token_storage.dart';
import 'ws_client.dart';

class AuthServiceException implements Exception {
  AuthServiceException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Backend-JWT auth (POST /auth/login, /auth/refresh, /auth/logout,
/// GET /me), replacing FirebaseAuth as of step 5 of the Postgres
/// migration (NyayMitra.md). A true singleton — `AuthService()` returns
/// the same instance everywhere, same as before, but that now matters
/// for real: this instance is the one place the signed-in user's profile
/// and the broadcast stream RootRouter listens to actually live.
class AuthService {
  factory AuthService() => instance;
  AuthService._internal();
  static final AuthService instance = AuthService._internal();

  final _tokenStorage = TokenStorage();
  final _controller = StreamController<UserProfile?>.broadcast();

  /// Null means signed out. Emits once at startup (after initialize()
  /// resolves whether a stored session is still good) and again on every
  /// sign-in/sign-out — RootRouter's whole routing decision is driven off
  /// this, the same role authStateChanges played for FirebaseAuth.
  Stream<UserProfile?> get userChanges => _controller.stream;

  UserProfile? _current;
  UserProfile? get currentUser => _current;

  bool _initialized = false;

  /// Call once, before relying on [userChanges] — RootRouter does this in
  /// initState(). Idempotent: a second call is a no-op, so it's safe to
  /// call defensively from more than one place without double-restoring.
  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;

    ApiClient.instance.onSessionExpired.listen((_) => _applySignedOut());

    final refreshToken = await _tokenStorage.refreshToken;
    if (refreshToken == null) {
      _controller.add(null);
      return;
    }

    // A stored refresh token doesn't guarantee it's still good (it may
    // have expired or been revoked since the app last ran) — /me is the
    // real check, and ApiClient already retries once through
    // /auth/refresh on a 401, so this one call covers both "still
    // logged in" and "needs a silent refresh first" in one round trip.
    try {
      final response = await ApiClient.instance.get('/me');
      if (response.statusCode == 200) {
        _applyProfile(jsonDecode(response.body) as Map<String, dynamic>);
        return;
      }
    } catch (_) {
      // Network error on startup — fall through to signed-out rather
      // than leaving the stream never emitting, which would strand
      // RootRouter on its loading screen forever.
    }
    await _applySignedOut();
  }

  Future<void> signIn({required String email, required String password}) async {
    // Plain http.post, not ApiClient: a wrong-password 401 here means
    // exactly that, not an expired access token, and ApiClient's 401
    // handling would otherwise try to refresh (using whatever stale or
    // absent token happens to be in storage from a previous session)
    // and retry the same login call pointlessly before the real error
    // ever surfaces.
    final response = await http.post(
      Uri.parse('$apiBaseUrl/auth/login'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode != 200) {
      throw AuthServiceException(_readableError(response));
    }

    final tokens = jsonDecode(response.body) as Map<String, dynamic>;
    await _tokenStorage.save(
      accessToken: tokens['accessToken'] as String,
      refreshToken: tokens['refreshToken'] as String,
    );

    final meResponse = await ApiClient.instance.get('/me');
    if (meResponse.statusCode != 200) {
      throw AuthServiceException('Signed in, but could not load your profile.');
    }
    _applyProfile(jsonDecode(meResponse.body) as Map<String, dynamic>);
  }

  Future<void> signOut() async {
    final refreshToken = await _tokenStorage.refreshToken;
    if (refreshToken != null) {
      try {
        // Plain http.post, not ApiClient, on purpose: logout must still
        // clear local state even if this call fails (network error, the
        // refresh token already invalid), and ApiClient's own 401
        // handling would otherwise try to *refresh* using the very token
        // this call exists to invalidate.
        await http.post(
          Uri.parse('$apiBaseUrl/auth/logout'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'refreshToken': refreshToken}),
        );
      } catch (_) {
        // Best-effort — a refresh token whose owner has already cleared
        // local storage is dead to this client either way, and the
        // backend rejects it if it's ever replayed.
      }
    }
    await _applySignedOut();
  }

  Future<void> _applySignedOut() async {
    await _tokenStorage.clear();
    WsRegistry.closeAll();
    _current = null;
    _controller.add(null);
  }

  void _applyProfile(Map<String, dynamic> json) {
    _current = UserProfile.fromApi(json);
    _controller.add(_current);
  }

  String _readableError(http.Response response) {
    try {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return json['detail']?.toString() ?? response.body;
    } catch (_) {
      return 'Request failed (${response.statusCode}).';
    }
  }
}
