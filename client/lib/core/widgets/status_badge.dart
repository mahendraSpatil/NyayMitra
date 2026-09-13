import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

enum StatusTone { info, warning, success, danger }

/// Small pill badge used for case stages, task priorities, and similar
/// short status labels.
class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.label, required this.tone});

  final String label;
  final StatusTone tone;

  (Color, Color) _colorsFor(StatusTone tone) {
    switch (tone) {
      case StatusTone.info:
        return (AppColors.info, AppColors.infoBg);
      case StatusTone.warning:
        return (AppColors.warning, AppColors.warningBg);
      case StatusTone.success:
        return (AppColors.success, AppColors.successBg);
      case StatusTone.danger:
        return (AppColors.danger, AppColors.dangerBg);
    }
  }

  @override
  Widget build(BuildContext context) {
    final (fg, bg) = _colorsFor(tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(label, style: AppTextStyles.badgeLabel.copyWith(color: fg)),
    );
  }
}
