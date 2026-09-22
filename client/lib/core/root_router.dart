import 'dart:async';

import 'package:flutter/material.dart';

import '../features/advocate/advocate_home.dart';
import '../features/auth/not_provisioned_screen.dart';
import '../features/auth/sign_in_screen.dart';
import '../features/family/family_home.dart';
import '../features/ngo/ngo_home.dart';
import 'models/user_profile.dart';
import 'services/auth_service.dart';

/// Routes to a portal based on the signed-in user's role, as reported by
/// GET /me. Never falls back to a default role.
///
/// Simpler than its Firebase-era version: role used to require a forced
/// ID-token refresh and decoding the JWT payload by hand (a Windows
/// FlutterFire bug meant IdTokenResult.claims came back null) just to
/// read a custom claim. /me just answers the question directly — no
/// token decoding on the client at all, since role was never something
/// this screen needed to verify, only to know which portal to show.
class RootRouter extends StatefulWidget {
  const RootRouter({super.key});

  @override
  State<RootRouter> createState() => _RootRouterState();
}

class _RootRouterState extends State<RootRouter> {
  final _authService = AuthService();
  StreamSubscription<UserProfile?>? _subscription;

  bool _restoring = true;
  UserProfile? _user;

  @override
  void initState() {
    super.initState();
    _subscription = _authService.userChanges.listen((user) {
      if (!mounted) return;
      setState(() {
        _user = user;
        _restoring = false;
      });
    });
    // initialize() is idempotent and safe to call every time RootRouter
    // is built — it only actually does the session-restore round trip
    // once (AuthService's own _initialized guard).
    _authService.initialize();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_restoring) {
      return const _LoadingScreen();
    }

    final user = _user;
    if (user == null) {
      return const SignInScreen();
    }

    switch (user.role) {
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
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}
