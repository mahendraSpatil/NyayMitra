import 'package:flutter/material.dart';

import '../../core/services/auth_service.dart';

/// Shown when a signed-in user's ID token carries no `role` claim. Reached
/// only after a forced token refresh (see RootRouter), so this genuinely
/// means the account hasn't been provisioned — not a stale-token false
/// positive.
class NotProvisionedScreen extends StatelessWidget {
  const NotProvisionedScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Account not provisioned',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              const Text(
                'This account has no assigned role yet. Ask an administrator '
                'to provision your access.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              OutlinedButton(
                onPressed: () => AuthService().signOut(),
                child: const Text('Sign out'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
