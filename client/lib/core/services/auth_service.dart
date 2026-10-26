import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart' show debugPrint;
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
    // Normalized here, not just trimmed in the sign-in form: the backend
    // stores/compares email the same way (RegisterRequest/LoginRequest's
    // _normalize_email, backend/app/models/auth.py) so a login attempt
    // and the registration it's matching against can never disagree on
    // case or stray whitespace — a trailing space from a paste, or a
    // capitalized first letter some platform's autofill added, used to
    // read as "wrong password" (a 401 indistinguishable from a real one)
    // rather than what it actually was.
    final normalizedEmail = _normalizeEmail(email);
    final requestBody = {'email': normalizedEmail, 'password': password};
    debugPrint(
      'AuthService.signIn: POST /auth/login body='
      '${jsonEncode({...requestBody, 'password': '<redacted>'})}',
    );

    // Plain http.post, not ApiClient: a wrong-password 401 here means
    // exactly that, not an expired access token, and ApiClient's 401
    // handling would otherwise try to refresh (using whatever stale or
    // absent token happens to be in storage from a previous session)
    // and retry the same login call pointlessly before the real error
    // ever surfaces.
    final response = await http.post(
      Uri.parse('$apiBaseUrl/auth/login'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(requestBody),
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

  /// Deliberately does not sign the caller in — the backend returns 201
  /// with no tokens (self-declared roles plus instant authentication
  /// would mean anyone who submits this form is immediately acting as
  /// whatever role they typed). Callers send the user to sign in
  /// explicitly afterward; RootRouter has nothing to react to here since
  /// no session was created.
  Future<void> register({
    required String email,
    required String password,
    required String displayName,
    required String role,
  }) async {
    // Same normalization signIn applies — this is what makes it safe for
    // signIn to assume a stored email is already trimmed/lowercased: both
    // paths agree on the same rule (see signIn's comment).
    final requestBody = {
      'email': _normalizeEmail(email),
      'password': password,
      'displayName': displayName,
      'role': role,
    };
    debugPrint(
      'AuthService.register: POST /auth/register body='
      '${jsonEncode({...requestBody, 'password': '<redacted>'})}',
    );

    final response = await http.post(
      Uri.parse('$apiBaseUrl/auth/register'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(requestBody),
    );
    if (response.statusCode != 201) {
      throw AuthServiceException(_readableError(response));
    }
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

  // Mirrors backend/app/models/auth.py's _normalize_email exactly — same
  // rule, applied on both sides, is what makes it safe to apply at all:
  // if only one side normalized, an already-registered mixed-case email
  // would still never match a lowercased login attempt.
  String _normalizeEmail(String email) => email.trim().toLowerCase();

  String _readableError(http.Response response) {
    try {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return json['detail']?.toString() ?? response.body;
    } catch (_) {
      return 'Request failed (${response.statusCode}).';
    }
  }
}
