import 'package:flutter/material.dart';

import '../../core/services/auth_service.dart';

class FamilyHome extends StatelessWidget {
  const FamilyHome({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Family Portal'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () => AuthService().signOut(),
          ),
        ],
      ),
      body: const Center(child: Text('family')),
    );
  }
}
