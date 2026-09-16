import 'package:cloud_firestore/cloud_firestore.dart';

/// Matches cases/{caseId}/hearings/{hearingId}. Read-only from the
/// client's perspective — mutation is backend-mediated via CaseService,
/// which also recomputes the parent case's nextHearingDate.
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

  factory Hearing.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const {};
    final rawDate = data['date'];
    return Hearing(
      id: doc.id,
      date: rawDate is Timestamp ? rawDate.toDate() : null,
      court: data['court'] as String? ?? '',
      purpose: data['purpose'] as String? ?? '',
      status: data['status'] as String? ?? 'scheduled',
      notes: data['notes'] as String? ?? '',
    );
  }
}
