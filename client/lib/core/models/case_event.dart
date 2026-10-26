/// A non-hearing Case Timeline milestone (charge sheet filed, bail
/// application submitted, ...) — the other half of the merged timeline
/// alongside Hearing. Read-only from the client's perspective; mutation
/// (adding one) goes through CaseService, matching Hearing's split.
class CaseEvent {
  final String id;
  final String title;
  final DateTime? date;
  final String eventType;
  final bool done;

  const CaseEvent({
    required this.id,
    this.title = '',
    this.date,
    this.eventType = 'other',
    this.done = false,
  });

  /// GET /api/v2/cases/{caseId}/events — field names match
  /// app/models/v2/case_event.py's CaseEventItem exactly.
  factory CaseEvent.fromApi(Map<String, dynamic> json) {
    final rawDate = json['date'] as String?;
    return CaseEvent(
      id: json['id'] as String,
      title: json['title'] as String? ?? '',
      date: rawDate == null ? null : DateTime.tryParse(rawDate),
      eventType: json['eventType'] as String? ?? 'other',
      done: json['done'] as bool? ?? false,
    );
  }
}

/// Human-readable labels for the fixed event_type set
/// (app/db/models.py's CaseEvent.event_type CHECK constraint) — kept
/// separate from the raw value for the same reason DocTypeLabel is:
/// storage keys and UI copy change for different reasons. Falls back to
/// the raw value for anything unrecognized rather than hiding it behind
/// a generic label.
extension CaseEventTypeLabel on String {
  String get eventTypeLabel {
    switch (this) {
      case 'charge_sheet_filed':
        return 'Charge Sheet Filed';
      case 'bail_application_submitted':
        return 'Bail Application Submitted';
      case 'bail_order_issued':
        return 'Bail Order Issued';
      case 'remand_extended':
        return 'Remand Extended';
      case 'other':
        return 'Other';
      default:
        return this;
    }
  }
}

const caseEventTypeOptions = [
  'charge_sheet_filed',
  'bail_application_submitted',
  'bail_order_issued',
  'remand_extended',
  'other',
];
