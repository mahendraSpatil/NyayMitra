import 'package:cloud_firestore/cloud_firestore.dart';

/// Matches tasks/{taskId}. taskType and priority stay free-form strings:
/// CLAUDE.md's demo data shows examples (translation, legal aid
/// coordination, verification visit; high/medium priority) but never
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

  const Task({
    required this.id,
    this.assignedToUid = '',
    this.caseId = '',
    this.taskType = '',
    this.priority = '',
    this.description = '',
    this.completed = false,
  });

  factory Task.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const {};
    return Task(
      id: doc.id,
      assignedToUid: data['assignedToUid'] as String? ?? '',
      caseId: data['caseId'] as String? ?? '',
      taskType: data['taskType'] as String? ?? '',
      priority: data['priority'] as String? ?? '',
      description: data['description'] as String? ?? '',
      completed: data['completed'] as bool? ?? false,
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
    };
  }
}
