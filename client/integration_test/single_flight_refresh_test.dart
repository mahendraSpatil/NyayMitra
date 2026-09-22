// Permanent regression test (not a throwaway) for the single-flight
// refresh guarantee ApiClient depends on — see
// core/services/api_client.dart's class docstring for the full reasoning.
//
// Without single-flight, several requests hitting 401 at once each call
// POST /auth/refresh independently. The backend rotates a refresh token
// on every use and treats a second presentation of an already-rotated
// token as reuse (a stolen-token signal) by revoking every refresh token
// that user has (backend/app/routers/auth.py) — so a naive
// refresh-per-401 implementation logs the user out roughly every access
// token lifetime (15 minutes), exactly when nothing was actually wrong.
//
// Run with: flutter test integration_test/single_flight_refresh_test.dart -d windows
// (plain flutter_test has no platform channels, so flutter_secure_storage
// can't initialize under it — same reason this project's Firebase-era
// tests needed integration_test too.)

import 'dart:convert';

import 'package:client/core/config/api_config.dart';
import 'package:client/core/services/api_client.dart';
import 'package:client/core/services/token_storage.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';

const _email = 'advocate@nyaymitra.test';
const _password = 'NyayMitra@Dev1';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  final tokenStorage = TokenStorage();

  tearDown(() async {
    // Whatever refresh token is left standing, invalidate it server-side
    // too — leaves no session alive on the backend after this test runs,
    // matching the "clean up everything you touched" convention used
    // throughout this migration's verification passes.
    final refreshToken = await tokenStorage.refreshToken;
    if (refreshToken != null) {
      await http.post(
        Uri.parse('$apiBaseUrl/auth/logout'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'refreshToken': refreshToken}),
      );
    }
    await tokenStorage.clear();
  });

  testWidgets(
    'concurrent 401s collapse into exactly one refresh, session survives',
    (tester) async {
      // A pump is needed even though this test never touches the widget
      // tree directly — without at least one frame, the engine's plugin
      // channel bindings (flutter_secure_storage's platform channel,
      // specifically) don't appear to be fully live yet, and calls
      // through it just hang rather than erroring.
      await tester.pumpWidget(const SizedBox.shrink());

      final loginResponse = await http.post(
        Uri.parse('$apiBaseUrl/auth/login'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'email': _email, 'password': _password}),
      );
      expect(loginResponse.statusCode, 200);
      final tokens = jsonDecode(loginResponse.body) as Map<String, dynamic>;
      await tokenStorage.save(
        accessToken: tokens['accessToken'] as String,
        refreshToken: tokens['refreshToken'] as String,
      );

      // Poison the stored access token so every one of the concurrent
      // requests below gets a real 401 from the backend, not a
      // client-side skip — the failure this test guards against only
      // shows up when several requests discover the 401 at once.
      await tokenStorage.saveAccessToken('not-a-real-access-token');

      final responses = await Future.wait(
        List.generate(5, (_) => ApiClient.instance.get('/me')),
      );

      for (final response in responses) {
        expect(response.statusCode, 200);
      }

      // The actual proof: if single-flight had failed, at least one of
      // the five requests above would have presented the refresh token
      // *after* another one already rotated it, triggering reuse
      // detection and revoking the whole session server-side — in which
      // case even a fresh, correctly-obtained access token would be
      // sitting on top of a session that's already dead, and this next
      // call would fail no matter what token is used.
      final followUp = await ApiClient.instance.get('/me');
      expect(followUp.statusCode, 200);
    },
  );
}
