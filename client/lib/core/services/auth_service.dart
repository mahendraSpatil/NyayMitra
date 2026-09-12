import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';

class AuthService {
  AuthService({FirebaseAuth? firebaseAuth})
      : _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance;

  final FirebaseAuth _firebaseAuth;

  Stream<User?> get authStateChanges => _firebaseAuth.authStateChanges();

  Future<void> signIn({required String email, required String password}) {
    return _firebaseAuth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
  }

  Future<void> signOut() => _firebaseAuth.signOut();

  /// Force-refreshes [user]'s ID token and returns its claims, decoded
  /// straight from the JWT payload rather than via IdTokenResult.claims.
  ///
  /// IdTokenResult.claims is always null on Windows desktop as of the
  /// installed firebase_auth version — a known FlutterFire bug
  /// (github.com/firebase/flutterfire/issues/11949) — even though the
  /// underlying token is correctly minted with the claim. Decoding the
  /// payload ourselves sidesteps that broken getter on every platform, not
  /// just Windows, so routing behaves the same everywhere.
  ///
  /// This is not a security-sensitive decode: the signature isn't checked
  /// here because none of this is used to authorize anything. It only
  /// picks which screen to show. Firestore's own rules read
  /// `request.auth.token.role` from Firebase's validated token
  /// infrastructure independently, unaffected by this client-side bug.
  Future<Map<String, dynamic>> getRefreshedClaims(User user) async {
    final token = await user.getIdToken(true);
    if (token == null) return const {};

    final segments = token.split('.');
    if (segments.length != 3) return const {};

    final payload = utf8.decode(base64Url.decode(base64Url.normalize(segments[1])));
    return jsonDecode(payload) as Map<String, dynamic>;
  }
}
