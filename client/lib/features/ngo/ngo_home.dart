import 'package:flutter/material.dart';

import '../../core/services/auth_service.dart';

class NgoHome extends StatelessWidget {
  const NgoHome({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('NGO Portal'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () => AuthService().signOut(),
          ),
        ],
      ),
      body: const Center(child: Text('ngo')),
    );
  }
}
