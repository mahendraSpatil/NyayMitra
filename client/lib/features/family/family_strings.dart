import '../../core/localization/locale_lookup.dart';

/// Every fixed UI string this portal shows, keyed by locale then by name.
/// `mr`/`hi` ship empty on purpose — wiring real translations (via
/// Bhashini) comes later. FamilyStrings below falls back to `en` for any
/// missing/empty entry, so an unfinished locale never renders blank.
///
/// This does NOT cover dynamic Firestore content (case stage labels,
/// advocate name, court, FIR number) — that's server-authored text, not
/// fixed UI chrome, and translating it is Bhashini's job (NyayMitra.md's AI
/// pipeline), not a static lookup table.
///
/// Sign-out has its own strings in core/localization/portal_strings.dart
/// (PortalSignOutButton owns that string set, shared across all three
/// portals) rather than a key here.
const Map<String, Map<String, String>> _familyStringsTable = {
  'en': {
    'portalTitle': 'Family Portal',
    'portalSubtitle': 'Case & Hearing Tracker',
    'statNextHearing': 'Next Hearing',
    'statCurrentStage': 'Current Stage',
    'statDocumentsUploaded': 'Documents Uploaded',
    'activeCaseBadge': 'Active Case',
    'legalRepresentativeLabel': 'Legal Representative',
    'hearingPillLabel': 'Hearing',
    'noHearingScheduled': 'No hearing scheduled',
    'actionsSectionHeader': 'Actions & Submissions',
    'uploadButtonLabel': 'Upload Case Document / ID Proof',
    'caseTimelineSectionHeader': 'Case Timeline',
    'noCaseFound': 'No case found.',
    'joinCaseButtonLabel': 'Have an invite code? Join a case',
    'redeemInviteDialogTitle': 'Join a Case',
    'redeemInviteFieldLabel': 'Enter invite code',
    'redeemInviteSubmitLabel': 'Join',
    'createOwnCaseButtonLabel':
        "Don't have a lawyer yet? Track a case yourself",
    'createOwnCaseTitle': 'Track a Case Yourself',
    'createOwnCaseDisclaimer':
        'This is a personal record for your own use, not an official court '
        'record — NyayMitra does not pull this from any court system. It '
        "only shows what you enter. If you get a lawyer later, they can "
        'send you an invite code to switch to their case record instead.',
    'createOwnCaseNameFieldLabel': "Undertrial's name",
    'createOwnCaseSubmitLabel': 'Start Tracking',
  },
  'mr': {},
  'hi': {},
};

class FamilyStrings {
  const FamilyStrings(this.locale);

  final String locale;

  String _t(String key) =>
      lookupLocalizedString(_familyStringsTable, locale, key);

  String get portalTitle => _t('portalTitle');
  String get portalSubtitle => _t('portalSubtitle');
  String get statNextHearing => _t('statNextHearing');
  String get statCurrentStage => _t('statCurrentStage');
  String get statDocumentsUploaded => _t('statDocumentsUploaded');
  String get activeCaseBadge => _t('activeCaseBadge');
  String get legalRepresentativeLabel => _t('legalRepresentativeLabel');
  String get hearingPillLabel => _t('hearingPillLabel');
  String get noHearingScheduled => _t('noHearingScheduled');
  String get actionsSectionHeader => _t('actionsSectionHeader');
  String get uploadButtonLabel => _t('uploadButtonLabel');
  String get caseTimelineSectionHeader => _t('caseTimelineSectionHeader');
  String get noCaseFound => _t('noCaseFound');
  String get joinCaseButtonLabel => _t('joinCaseButtonLabel');
  String get redeemInviteDialogTitle => _t('redeemInviteDialogTitle');
  String get redeemInviteFieldLabel => _t('redeemInviteFieldLabel');
  String get redeemInviteSubmitLabel => _t('redeemInviteSubmitLabel');
  String get createOwnCaseButtonLabel => _t('createOwnCaseButtonLabel');
  String get createOwnCaseTitle => _t('createOwnCaseTitle');
  String get createOwnCaseDisclaimer => _t('createOwnCaseDisclaimer');
  String get createOwnCaseNameFieldLabel => _t('createOwnCaseNameFieldLabel');
  String get createOwnCaseSubmitLabel => _t('createOwnCaseSubmitLabel');
}

/// Supported locale codes, in the order NyayMitra.md lists them.
const supportedFamilyLocales = ['en', 'mr', 'hi'];

String resolveFamilyLocale(String? preferredLanguage) {
  if (preferredLanguage != null &&
      supportedFamilyLocales.contains(preferredLanguage)) {
    return preferredLanguage;
  }
  return 'en';
}
