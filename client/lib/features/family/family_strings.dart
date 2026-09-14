/// Every fixed UI string this portal shows, keyed by locale then by name.
/// `mr`/`hi` ship empty on purpose — wiring real translations (via
/// Bhashini) comes later. FamilyStrings below falls back to `en` for any
/// missing/empty entry, so an unfinished locale never renders blank.
///
/// This does NOT cover dynamic Firestore content (case stage labels,
/// advocate name, court, FIR number) — that's server-authored text, not
/// fixed UI chrome, and translating it is Bhashini's job (CLAUDE.md's AI
/// pipeline), not a static lookup table.
const Map<String, Map<String, String>> _familyStringsTable = {
  'en': {
    'portalTitle': 'Family Portal',
    'portalSubtitle': 'Case & Hearing Tracker',
    'signOutTooltip': 'Sign out',
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
  },
  'mr': {},
  'hi': {},
};

class FamilyStrings {
  const FamilyStrings(this.locale);

  final String locale;

  String _t(String key) {
    final localized = _familyStringsTable[locale]?[key];
    if (localized != null && localized.isNotEmpty) return localized;
    return _familyStringsTable['en']?[key] ?? key;
  }

  String get portalTitle => _t('portalTitle');
  String get portalSubtitle => _t('portalSubtitle');
  String get signOutTooltip => _t('signOutTooltip');
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
}

/// Supported locale codes, in the order CLAUDE.md lists them.
const supportedFamilyLocales = ['en', 'mr', 'hi'];

String resolveFamilyLocale(String? preferredLanguage) {
  if (preferredLanguage != null && supportedFamilyLocales.contains(preferredLanguage)) {
    return preferredLanguage;
  }
  return 'en';
}
