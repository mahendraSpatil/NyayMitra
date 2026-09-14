/// Shared lookup mechanism for any `Map<locale, Map<key, value>>` string
/// table: falls back to `en` for a missing or empty entry, so an
/// unfinished locale (mr/hi, until Bhashini wiring lands) never renders
/// blank — and finally to the key itself if even `en` has no entry, since
/// that's a real bug that should be visible and debuggable, not a thrown
/// exception mid-build.
String lookupLocalizedString(
  Map<String, Map<String, String>> table,
  String locale,
  String key,
) {
  final localized = table[locale]?[key];
  if (localized != null && localized.isNotEmpty) return localized;
  return table['en']?[key] ?? key;
}
