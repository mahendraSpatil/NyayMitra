import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// A single stat tile: small icon, large value, small caption below.
/// Callers lay three of these out in a Row at the top of a portal.
class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.icon,
    required this.accentColor,
    required this.value,
    required this.caption,
  });

  final IconData icon;
  final Color accentColor;
  final String value;
  final String caption;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: accentColor, size: 22),
            const SizedBox(height: 10),
            Text(value, style: AppTextStyles.statValue.copyWith(color: accentColor)),
            const SizedBox(height: 2),
            Text(caption, style: AppTextStyles.statCaption),
          ],
        ),
      ),
    );
  }
}
