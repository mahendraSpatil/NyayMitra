import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../features/advocate/advocate_home.dart';
import '../features/auth/not_provisioned_screen.dart';
import '../features/auth/sign_in_screen.dart';
import '../features/family/family_home.dart';
import '../features/ngo/ngo_home.dart';
import 'models/user_profile.dart';
import 'services/auth_service.dart';

/// Routes to a portal based on the `role` custom claim on the signed-in
/// user's ID token. Never falls back to a default role.
///
/// Stateful rather than a StreamBuilder/FutureBuilder pair: the token
/// refresh below is a network round trip, and if it were issued from
/// inside build() (e.g. as a FutureBuilder's `future:` argument) it would
/// re-run on every rebuild this widget happens to go through, not just on
/// sign-in. Fetching it once in response to an auth-state change, and
/// caching the result in State, keeps it to exactly one refresh per
/// sign-in no matter how often the tree above this rebuilds.
class RootRouter extends StatefulWidget {
  const RootRouter({super.key});

  @override
  State<RootRouter> createState() => _RootRouterState();
}

class _RootRouterState extends State<RootRouter> {
  final _authService = AuthService();
  StreamSubscription<User?>? _authSubscription;

  User? _user;
  Map<String, dynamic>? _claims;
  bool _fetchingToken = false;

  @override
  void initState() {
    super.initState();
    _authSubscription = _authService.authStateChanges.listen(_handleAuthStateChanged);
  }

  @override
  void dispose() {
    _authSubscription?.cancel();
    super.dispose();
  }

  Future<void> _handleAuthStateChanged(User? user) async {
    setState(() {
      _user = user;
      _claims = null;
      _fetchingToken = user != null;
    });

    if (user == null) return;

    // Force a refresh: custom claims are baked into the ID token at mint
    // time, not read live from Firebase Auth on every request. A user
    // signed in before the seed script set their role claim (or one whose
    // token simply hasn't rotated yet) would otherwise carry a stale,
    // claim-less token for up to an hour. Without this, a freshly
    // provisioned user would land on the not-provisioned screen despite
    // their claim being set server-side. This looks like a redundant
    // network call — it isn't; an unforced refresh would happily return
    // that stale cached token.
    //
    // getRefreshedClaims decodes the JWT payload itself rather than using
    // IdTokenResult.claims, which is always null on Windows desktop
    // (flutterfire#11949) despite the token being correctly minted — see
    // AuthService.getRefreshedClaims for why that's safe to do here.
    final claims = await _authService.getRefreshedClaims(user);

    // The user may have signed out (or into a different account) while
    // the refresh above was in flight. Only apply a response that still
    // matches the user it was requested for.
    if (!mounted || _user?.uid != user.uid) return;

    setState(() {
      _claims = claims;
      _fetchingToken = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_user == null) {
      return const SignInScreen();
    }

    if (_fetchingToken || _claims == null) {
      return const _LoadingScreen();
    }

    final role = parseUserRole(_claims!['role'] as String?);

    switch (role) {
      case UserRole.advocate:
        return const AdvocateHome();
      case UserRole.ngo:
        return const NgoHome();
      case UserRole.family:
        return const FamilyHome();
      case null:
        return const NotProvisionedScreen();
    }
  }
}

class _LoadingScreen extends StatelessWidget {
  const _LoadingScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(child: CircularProgressIndicator()),
    );
  }
}
