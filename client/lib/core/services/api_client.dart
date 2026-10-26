import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import 'token_storage.dart';

class ApiUnauthorizedException implements Exception {
  const ApiUnauthorizedException();

  @override
  String toString() => 'Session expired — please sign in again.';
}

/// The one place every backend HTTP call in the app goes through —
/// CaseService, InviteService, DocumentUploadService, ChatService, and
/// DataService's REST fetches all call this instead of raw
/// package:http, so single-flight refresh (below) applies universally
/// rather than needing to be reimplemented per service.
///
/// Single-flight matters because the alternative genuinely breaks
/// sessions: an access token is good for 15 minutes (backend/app/security/
/// tokens.py), so a screen that fires several requests at roughly the
/// same time — a case detail screen's case/hearings/documents streams
/// all refetching after a reconnect, say — can easily have all of them
/// hit 401 together. If each one independently called /auth/refresh,
/// the second call to arrive would present a refresh token the first
/// call already rotated past, and the backend's reuse-detection
/// (backend/app/routers/auth.py) would read that as a stolen token and
/// revoke the whole session — logging the user out roughly every 15
/// minutes, exactly when the token was actually fine. Caching the
/// in-flight refresh Future and having every concurrent 401 await the
/// same one avoids ever presenting a token twice.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final _http = http.Client();
  final _tokenStorage = TokenStorage();

  final _unauthenticatedController = StreamController<void>.broadcast();

  /// Fires when a refresh definitively failed (no refresh token stored,
  /// or the backend rejected it) — AuthService listens to this to know
  /// the session is gone and it should show the sign-in screen, without
  /// ApiClient needing to know anything about AuthService itself.
  Stream<void> get onSessionExpired => _unauthenticatedController.stream;

  Future<String>? _refreshInFlight;

  /// Endpoints that authenticate the caller themselves (or create a new,
  /// unauthenticated account) — a 401 from either means the credentials
  /// in the request itself were rejected, never an expired access token,
  /// so feeding it through the refresh-and-retry path below would be
  /// nonsensical: it would refresh using whatever (possibly unrelated,
  /// possibly stale) token happens to be in storage and then retry the
  /// exact same failing request. AuthService already calls both of these
  /// via plain http.post specifically to bypass ApiClient entirely (see
  /// its signIn/register) — this is the backstop in case that ever
  /// changes, so "never retried" is a property of ApiClient itself, not
  /// just a convention every caller has to remember.
  static const _noRetryPaths = {'/auth/login', '/auth/register'};

  Future<http.Response> get(String path) => _send('GET', path);

  Future<http.Response> post(String path, {Object? body}) =>
      _send('POST', path, body: body);

  Future<http.Response> put(String path, {Object? body}) =>
      _send('PUT', path, body: body);

  Future<http.Response> patch(String path, {Object? body}) =>
      _send('PATCH', path, body: body);

  Future<http.Response> delete(String path) => _send('DELETE', path);

  Future<http.Response> _send(
    String method,
    String path, {
    Object? body,
  }) async {
    var accessToken = await _tokenStorage.accessToken;
    var response = await _rawSend(method, path, accessToken, body);

    // At most one retry, ever — this branch runs once per call to
    // _send() (there is no loop, no recursion here), and only for paths
    // that actually mean "your access token expired," never for a 401
    // that means "the credentials themselves are wrong."  A refresh that
    // itself fails throws out of _refreshAccessToken() below and this
    // function returns without a second attempt at anything.
    if (response.statusCode == 401 && !_noRetryPaths.contains(path)) {
      try {
        accessToken = await _refreshAccessToken();
      } on ApiUnauthorizedException {
        rethrow;
      }
      response = await _rawSend(method, path, accessToken, body);
    }
    return response;
  }

  Future<http.Response> _rawSend(
    String method,
    String path,
    String? accessToken,
    Object? body,
  ) {
    final uri = Uri.parse('$apiBaseUrl$path');
    final headers = {
      'Content-Type': 'application/json',
      if (accessToken != null) 'Authorization': 'Bearer $accessToken',
    };
    final encodedBody = body == null ? null : jsonEncode(body);

    switch (method) {
      case 'GET':
        return _http.get(uri, headers: headers);
      case 'POST':
        return _http.post(uri, headers: headers, body: encodedBody);
      case 'PUT':
        return _http.put(uri, headers: headers, body: encodedBody);
      case 'PATCH':
        return _http.patch(uri, headers: headers, body: encodedBody);
      case 'DELETE':
        return _http.delete(uri, headers: headers);
      default:
        throw ArgumentError('Unsupported method: $method');
    }
  }

  /// Single-flight: the null-check-and-assign below runs synchronously
  /// with no `await` in between (calling an async function returns its
  /// Future immediately, without waiting for the function body), so every
  /// concurrent caller that reaches this line before the in-flight
  /// refresh completes sees the same non-null Future and awaits that one
  /// instead of starting a new refresh. Dart's cooperative, single-threaded
  /// event loop is what makes this safe without a lock: two calls can't
  /// interleave *inside* this synchronous check the way they could under
  /// true parallelism.
  Future<String> _refreshAccessToken() {
    return _refreshInFlight ??= _doRefresh().whenComplete(
      () => _refreshInFlight = null,
    );
  }

  Future<String> _doRefresh() async {
    final refreshToken = await _tokenStorage.refreshToken;
    if (refreshToken == null) {
      _unauthenticatedController.add(null);
      throw const ApiUnauthorizedException();
    }

    final response = await _http.post(
      Uri.parse('$apiBaseUrl/auth/refresh'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({'refreshToken': refreshToken}),
    );

    if (response.statusCode != 200) {
      await _tokenStorage.clear();
      _unauthenticatedController.add(null);
      throw const ApiUnauthorizedException();
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final newAccessToken = json['accessToken'] as String;
    await _tokenStorage.save(
      accessToken: newAccessToken,
      refreshToken: json['refreshToken'] as String,
    );
    return newAccessToken;
  }
}
