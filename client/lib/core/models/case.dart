/// Matches the tones StatusBadge renders (Phase 3): info/warning/success.
enum CaseStageTone { info, warning, success }

CaseStageTone _stageToneFromString(String? value) {
  switch (value) {
    case 'warning':
      return CaseStageTone.warning;
    case 'success':
      return CaseStageTone.success;
    default:
      return CaseStageTone.info;
  }
}

DateTime? _dateFromValue(dynamic value) {
  if (value is DateTime) return value;
  // The API encodes datetimes as ISO 8601 strings.
  if (value is String) return DateTime.tryParse(value);
  return null;
}

class TimelineEntry {
  final String title;
  final DateTime? date;
  final bool done;

  const TimelineEntry({required this.title, this.date, this.done = false});

  factory TimelineEntry.fromMap(Map<String, dynamic> map) {
    return TimelineEntry(
      title: map['title'] as String? ?? '',
      date: _dateFromValue(map['date']),
      done: map['done'] as bool? ?? false,
    );
  }
}

/// Matches cases/{caseId}.
class Case {
  final String id;
  final String firNumber;
  final String court;
  final String undertrialName;
  // Null for a case with no lawyer attached — a family-owned self-managed
  // case. Never assume this is set; check ownerType instead of inferring
  // ownership from whether this happens to be null.
  final String? advocateUid;
  final String advocateName;
  final List<String> familyUids;
  final List<String> ngoUids;
  // Who created the case and what kind of owner they are. Null on
  // documents written before this field existed — treat as "legacy
  // advocate case" only when advocateUid is also non-null, never inferred
  // otherwise.
  final String? createdBy;
  final String? ownerType;
  final String stage;
  final String stageLabel;
  final CaseStageTone stageTone;
  final DateTime? nextHearingDate;
  final int documentCount;
  final List<TimelineEntry> timeline;

  const Case({
    required this.id,
    this.firNumber = '',
    this.court = '',
    this.undertrialName = '',
    this.advocateUid,
    this.advocateName = '',
    this.familyUids = const [],
    this.ngoUids = const [],
    this.createdBy,
    this.ownerType,
    this.stage = '',
    this.stageLabel = '',
    this.stageTone = CaseStageTone.info,
    this.nextHearingDate,
    this.documentCount = 0,
    this.timeline = const [],
  });

  /// GET /api/v2/cases and GET /api/v2/cases/{caseId}'s response shape —
  /// field names match app/models/v2/case.py's CaseItem exactly, by
  /// design: the client's parsing code didn't change from the
  /// Firestore-era model, only where the JSON comes from.
  factory Case.fromApi(Map<String, dynamic> json) {
    final rawTimeline = json['timeline'] as List<dynamic>? ?? const [];
    return Case(
      id: json['id'] as String,
      firNumber: json['firNumber'] as String? ?? '',
      court: json['court'] as String? ?? '',
      undertrialName: json['undertrialName'] as String? ?? '',
      advocateUid: json['advocateUid'] as String?,
      advocateName: json['advocateName'] as String? ?? '',
      familyUids: (json['familyUids'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
      ngoUids: (json['ngoUids'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
      createdBy: json['createdBy'] as String?,
      ownerType: json['ownerType'] as String?,
      stage: json['stage'] as String? ?? '',
      stageLabel: json['stageLabel'] as String? ?? '',
      stageTone: _stageToneFromString(json['stageTone'] as String?),
      nextHearingDate: _dateFromValue(json['nextHearingDate']),
      documentCount: (json['documentCount'] as num?)?.toInt() ?? 0,
      // Always [] from the API — cases.timeline doesn't exist in
      // Postgres (dropped for hearings + case_events, commit 1 of the
      // migration) and nothing has replaced it in the API yet. Parsed
      // here anyway rather than hardcoded to const [], so a future
      // endpoint that does populate it needs no client-side change.
      timeline: rawTimeline
          .map(
            (e) => TimelineEntry.fromMap(Map<String, dynamic>.from(e as Map)),
          )
          .toList(),
    );
  }
}
