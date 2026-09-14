import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Renders beneath every assistant chat message. Not built on StatusBadge:
/// that widget's pill sizing assumes short 1-3 word labels, and this is a
/// full sentence either way — reuses the same success/danger colour
/// tokens instead of stretching that widget's meaning.
class VerificationTag extends StatelessWidget {
  const VerificationTag({super.key, required this.verified, this.citedSections = const []});

  final bool verified;
  final List<String> citedSections;

  @override
  Widget build(BuildContext context) {
    final (icon, color, bg, label) = verified
        ? (
            Icons.check_circle,
            AppColors.success,
            AppColors.successBg,
            'Verified against ${citedSections.isEmpty ? "cited section" : citedSections.join(", ")}',
          )
        : (
            Icons.error_outline,
            AppColors.danger,
            AppColors.dangerBg,
            "Couldn't verify against your document — ask your lawyer",
          );

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(10)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              style: AppTextStyles.cardSubtitle.copyWith(color: color, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
