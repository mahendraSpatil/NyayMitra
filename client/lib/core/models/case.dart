import 'package:cloud_firestore/cloud_firestore.dart';

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

String _stageToneToString(CaseStageTone tone) {
  switch (tone) {
    case CaseStageTone.warning:
      return 'warning';
    case CaseStageTone.success:
      return 'success';
    case CaseStageTone.info:
      return 'info';
  }
}

DateTime? _dateFromValue(dynamic value) {
  if (value is Timestamp) return value.toDate();
  if (value is DateTime) return value;
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

  Map<String, dynamic> toMap() {
    return {
      'title': title,
      'date': date == null ? null : Timestamp.fromDate(date!),
      'done': done,
    };
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

  factory Case.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const {};
    final rawTimeline = data['timeline'] as List<dynamic>? ?? const [];
    return Case(
      id: doc.id,
      firNumber: data['firNumber'] as String? ?? '',
      court: data['court'] as String? ?? '',
      undertrialName: data['undertrialName'] as String? ?? '',
      advocateUid: data['advocateUid'] as String?,
      advocateName: data['advocateName'] as String? ?? '',
      familyUids: (data['familyUids'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
      ngoUids: (data['ngoUids'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
      createdBy: data['createdBy'] as String?,
      ownerType: data['ownerType'] as String?,
      stage: data['stage'] as String? ?? '',
      stageLabel: data['stageLabel'] as String? ?? '',
      stageTone: _stageToneFromString(data['stageTone'] as String?),
      nextHearingDate: _dateFromValue(data['nextHearingDate']),
      documentCount: (data['documentCount'] as num?)?.toInt() ?? 0,
      timeline: rawTimeline
          .map((e) => TimelineEntry.fromMap(Map<String, dynamic>.from(e as Map)))
          .toList(),
    );
  }

  Map<String, dynamic> toFirestore() {
    return {
      'firNumber': firNumber,
      'court': court,
      'undertrialName': undertrialName,
      'advocateUid': advocateUid,
      'advocateName': advocateName,
      'familyUids': familyUids,
      'ngoUids': ngoUids,
      'createdBy': createdBy,
      'ownerType': ownerType,
      'stage': stage,
      'stageLabel': stageLabel,
      'stageTone': _stageToneToString(stageTone),
      'nextHearingDate':
          nextHearingDate == null ? null : Timestamp.fromDate(nextHearingDate!),
      'documentCount': documentCount,
      'timeline': timeline.map((e) => e.toMap()).toList(),
    };
  }
}
