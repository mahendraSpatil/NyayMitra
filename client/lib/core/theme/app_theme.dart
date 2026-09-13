import 'package:flutter/material.dart';

/// The app's full colour palette, defined once. Widgets reference these
/// constants directly instead of inlining Color(...).
class AppColors {
  const AppColors._();

  static const background = Color(0xFFF3EEE5);
  static const surface = Color(0xFFFFFFFF);
  static const border = Color(0xFFE6DFD3);

  static const ink = Color(0xFF241B15);
  static const inkMuted = Color(0xFF8A8074);

  static const info = Color(0xFF3B6FA0);
  static const infoBg = Color(0xFFDCEAF6);

  static const warning = Color(0xFFC17F2A);
  static const warningBg = Color(0xFFF6E8D2);

  static const success = Color(0xFF2E8B57);
  static const successBg = Color(0xFFDCEFE2);

  /// Not a StatusBadge tone — a general-purpose accent for callers that
  /// want a warm red/orange StatCard icon (e.g. an upcoming hearing date).
  static const accentRed = Color(0xFFC0472E);
}

/// The app's full type scale, defined once. Widgets reference these
/// constants directly instead of inlining TextStyle(...).
class AppTextStyles {
  const AppTextStyles._();

  static const statValue = TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.bold,
    color: AppColors.ink,
    height: 1.2,
  );

  static const statCaption = TextStyle(
    fontSize: 12,
    color: AppColors.inkMuted,
  );

  static const portalTitle = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w700,
    color: AppColors.ink,
  );

  static const portalSubtitle = TextStyle(
    fontSize: 13,
    color: AppColors.inkMuted,
  );

  static const cardTitle = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
    color: AppColors.ink,
  );

  static const cardSubtitle = TextStyle(
    fontSize: 13,
    color: AppColors.inkMuted,
  );

  static const timelineTitle = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.normal,
    color: AppColors.ink,
  );

  static const body = TextStyle(
    fontSize: 14,
    color: AppColors.ink,
  );

  static const badgeLabel = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w600,
  );

  static const buttonLabel = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
    color: AppColors.surface,
  );
}

class AppTheme {
  const AppTheme._();

  static ThemeData light() {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.ink,
        brightness: Brightness.light,
        surface: AppColors.surface,
        error: AppColors.accentRed,
      ),
    );

    return base.copyWith(
      scaffoldBackgroundColor: AppColors.background,
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: AppTextStyles.portalTitle,
        iconTheme: IconThemeData(color: AppColors.ink),
      ),
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: AppColors.border, width: 1),
        ),
      ),
      textTheme: base.textTheme.copyWith(
        titleLarge: AppTextStyles.portalTitle,
        titleMedium: AppTextStyles.cardTitle,
        bodyMedium: AppTextStyles.body,
        bodySmall: AppTextStyles.cardSubtitle,
        labelLarge: AppTextStyles.buttonLabel,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.ink,
          foregroundColor: AppColors.surface,
          textStyle: AppTextStyles.buttonLabel,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          padding: const EdgeInsets.symmetric(vertical: 16),
        ),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: AppColors.ink,
        foregroundColor: AppColors.surface,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.ink),
        ),
        hintStyle: AppTextStyles.body.copyWith(color: AppColors.inkMuted),
      ),
      dividerTheme: const DividerThemeData(color: AppColors.border, space: 1),
    );
  }
}
