/// One hearing on a case. Read-only from the client's perspective —
/// mutation is backend-mediated via CaseService, which also recomputes
/// the parent case's nextHearingDate.
class Hearing {
  final String id;
  final DateTime? date;
  final String court;
  final String purpose;
  final String status;
  final String notes;

  const Hearing({
    required this.id,
    this.date,
    this.court = '',
    this.purpose = '',
    this.status = 'scheduled',
    this.notes = '',
  });

  /// GET /api/v2/cases/{caseId}/hearings — field names match
  /// app/models/v2/hearing.py's HearingItem exactly.
  factory Hearing.fromApi(Map<String, dynamic> json) {
    final rawDate = json['date'] as String?;
    return Hearing(
      id: json['id'] as String,
      date: rawDate == null ? null : DateTime.tryParse(rawDate),
      court: json['court'] as String? ?? '',
      purpose: json['purpose'] as String? ?? '',
      status: json['status'] as String? ?? 'scheduled',
      notes: json['notes'] as String? ?? '',
    );
  }
}
