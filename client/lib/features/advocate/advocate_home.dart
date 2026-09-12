import 'package:flutter/material.dart';

import '../../core/services/auth_service.dart';

class AdvocateHome extends StatelessWidget {
  const AdvocateHome({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Advocate Console'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () => AuthService().signOut(),
          ),
        ],
      ),
      body: const Center(child: Text('advocate')),
    );
  }
}
