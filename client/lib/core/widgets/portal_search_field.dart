import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Rounded search field with a leading search icon, used at the top of
/// each portal's list view.
class PortalSearchField extends StatelessWidget {
  const PortalSearchField({
    super.key,
    required this.hintText,
    this.controller,
    this.onChanged,
  });

  final String hintText;
  final TextEditingController? controller;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      onChanged: onChanged,
      style: AppTextStyles.body,
      decoration: InputDecoration(
        hintText: hintText,
        prefixIcon: const Icon(Icons.search, color: AppColors.inkMuted),
      ),
    );
  }
}
