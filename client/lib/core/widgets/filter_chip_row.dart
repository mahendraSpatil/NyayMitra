import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Horizontally scrolling, single-selection row of filter chips. The
/// selected chip is dark-filled with a leading check; others are outlined.
class FilterChipRow extends StatelessWidget {
  const FilterChipRow({
    super.key,
    required this.labels,
    required this.selectedIndex,
    required this.onSelected,
  });

  final List<String> labels;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 36,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: labels.length,
        separatorBuilder: (context, index) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final selected = index == selectedIndex;
          return ChoiceChip(
            label: Text(labels[index]),
            selected: selected,
            onSelected: (_) => onSelected(index),
            avatar: selected
                ? const Icon(Icons.check, size: 16, color: AppColors.surface)
                : null,
            showCheckmark: false,
            labelStyle: AppTextStyles.badgeLabel.copyWith(
              color: selected ? AppColors.surface : AppColors.ink,
              fontWeight: FontWeight.w500,
            ),
            backgroundColor: AppColors.surface,
            selectedColor: AppColors.ink,
            side: BorderSide(color: selected ? AppColors.ink : AppColors.border),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          );
        },
      ),
    );
  }
}
