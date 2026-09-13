import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// The universal FAB present on every portal, opening the AI chatbot.
class NyayMitraFab extends StatelessWidget {
  const NyayMitraFab({super.key, required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton(
      onPressed: onPressed,
      backgroundColor: AppColors.ink,
      foregroundColor: AppColors.surface,
      shape: const CircleBorder(),
      child: const Icon(Icons.balance),
    );
  }
}
