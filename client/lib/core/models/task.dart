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

/// One field task. taskType and priority stay free-form strings:
/// NyayMitra.md's demo data shows examples (translation, legal aid
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

  /// GET /api/v2/tasks — field names match app/models/v2/task.py's
  /// TaskItem exactly.
  factory Task.fromApi(Map<String, dynamic> json) {
    final completedAtValue = json['completedAt'] as String?;
    return Task(
      id: json['id'] as String,
      assignedToUid: json['assignedToUid'] as String? ?? '',
      caseId: json['caseId'] as String? ?? '',
      taskType: json['taskType'] as String? ?? '',
      priority: json['priority'] as String? ?? '',
      description: json['description'] as String? ?? '',
      completed: json['completed'] as bool? ?? false,
      completedAt: completedAtValue == null
          ? null
          : DateTime.tryParse(completedAtValue),
    );
  }
}
