// Permanent regression test: a failed sign-in (wrong password — a
// terminal 401, never an expired-token 401) must hit POST /auth/login
// exactly once. AuthService.signIn uses plain http.post specifically to
// bypass ApiClient's refresh-and-retry (see its own comment), and
// ApiClient._send independently refuses to retry /auth/login or
// /auth/register at all (see its _noRetryPaths) — this test is the
// backstop that catches either guarantee regressing, not just one of
// them.
//
// Counts real outgoing HTTP calls via HttpOverrides rather than mocking
// anything AuthService talks to — this project's tests run against the
// real backend (see single_flight_refresh_test.dart), so the fix here is
// proven against the genuine network path signIn() actually uses, not a
// stand-in for it.
//
// Run with: flutter test integration_test/failed_login_no_retry_test.dart -d windows

import 'dart:io';

import 'package:client/core/services/auth_service.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

const _email = 'advocate@nyaymitra.test';

/// Forwards everything to a real HttpClient except openUrl, which it
/// counts before delegating — the one method package:http's IOClient
/// actually calls to issue a request, so counting here sees every
/// outgoing call regardless of which convenience method on `http`
/// produced it. Relies on Dart's noSuchMethod fallback to stand in for
/// every other HttpClient interface member (userAgent, idleTimeout,
/// addCredentials, ...) this test never touches.
class _CountingHttpClient implements HttpClient {
  _CountingHttpClient(this._inner, this._onOpenUrl);

  final HttpClient _inner;
  final void Function(String method, Uri url) _onOpenUrl;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) {
    _onOpenUrl(method, url);
    return _inner.openUrl(method, url);
  }

  @override
  void close({bool force = false}) => _inner.close(force: force);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _CountingHttpOverrides extends HttpOverrides {
  int loginRequestCount = 0;

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final real = super.createHttpClient(context);
    return _CountingHttpClient(real, (method, url) {
      if (method == 'POST' && url.path.endsWith('/auth/login')) {
        loginRequestCount++;
      }
    });
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a failed login results in exactly one POST to /auth/login', (
    tester,
  ) async {
    // See single_flight_refresh_test.dart's identical comment — plugin
    // platform channels aren't fully live without at least one pump.
    await tester.pumpWidget(const SizedBox.shrink());

    final overrides = _CountingHttpOverrides();
    HttpOverrides.global = overrides;
    addTearDown(() => HttpOverrides.global = null);

    await expectLater(
      AuthService().signIn(
        email: _email,
        password: 'definitely-the-wrong-password',
      ),
      throwsA(isA<AuthServiceException>()),
    );

    expect(overrides.loginRequestCount, 1);
  });
}
