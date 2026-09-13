import 'package:cloud_firestore/cloud_firestore.dart';

/// Human-readable category labels, kept separate from the raw taskType
/// value for the same reason DocTypeLabel is separate from _docTypeToString:
/// UI copy and storage keys change for different reasons. Falls back to the
/// raw value for any taskType this list doesn't know about, rather than a
/// generic "Task" label that would hide new/unexpected values.
extension TaskTypeLabel on String {
  String get taskCategoryLabel {
    switch (this) {
      case 'translation':
        return 'Document Help';
      case 'legal_aid_coordination':
        return 'Legal Aid';
      case 'verification_visit':
        return 'Field Visit';
      default:
        return this;
    }
  }
}

/// Matches tasks/{taskId}. taskType and priority stay free-form strings:
/// CLAUDE.md's demo data shows examples (translation, legal aid
/// coordination, verification visit; high/medium/scheduled) but never
/// defines a fixed enum for either, so pinning one down here would be a
/// guess rather than something the spec actually states.
class Task {
  final String id;
  final String assignedToUid;
  final String caseId;
  final String taskType;
  final String priority;
  final String description;
  final bool completed;
  final DateTime? completedAt;

  const Task({
    required this.id,
    this.assignedToUid = '',
    this.caseId = '',
    this.taskType = '',
    this.priority = '',
    this.description = '',
    this.completed = false,
    this.completedAt,
  });

  factory Task.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const {};
    final completedAtValue = data['completedAt'];
    return Task(
      id: doc.id,
      assignedToUid: data['assignedToUid'] as String? ?? '',
      caseId: data['caseId'] as String? ?? '',
      taskType: data['taskType'] as String? ?? '',
      priority: data['priority'] as String? ?? '',
      description: data['description'] as String? ?? '',
      completed: data['completed'] as bool? ?? false,
      completedAt: completedAtValue is Timestamp ? completedAtValue.toDate() : null,
    );
  }

  Map<String, dynamic> toFirestore() {
    return {
      'assignedToUid': assignedToUid,
      'caseId': caseId,
      'taskType': taskType,
      'priority': priority,
      'description': description,
      'completed': completed,
      'completedAt': completedAt == null ? null : Timestamp.fromDate(completedAt!),
    };
  }
}
