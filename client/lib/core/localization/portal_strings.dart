import 'locale_lookup.dart';

/// Strings for widgets shared across all three portals — currently just
/// PortalSignOutButton. Kept separate from FamilyStrings (which is scoped
/// to features/family) since core/widgets can't depend on a features/
/// package; this is the reverse direction, and the right one.
const Map<String, Map<String, String>> _portalStringsTable = {
  'en': {
    'signOutTooltip': 'Sign out',
    'signOutDialogTitle': 'Sign out?',
    'signOutDialogMessage': "You'll need to sign in again to continue.",
    'signOutDialogCancel': 'Cancel',
    'signOutDialogConfirm': 'Sign out',
  },
  'mr': {},
  'hi': {},
};

class PortalStrings {
  const PortalStrings(this.locale);

  final String locale;

  String _t(String key) => lookupLocalizedString(_portalStringsTable, locale, key);

  String get signOutTooltip => _t('signOutTooltip');
  String get signOutDialogTitle => _t('signOutDialogTitle');
  String get signOutDialogMessage => _t('signOutDialogMessage');
  String get signOutDialogCancel => _t('signOutDialogCancel');
  String get signOutDialogConfirm => _t('signOutDialogConfirm');
}
