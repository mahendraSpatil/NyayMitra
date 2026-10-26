/// One key fact read from a case document — FIR number, a section, or a
/// date — with its own confidence and review state. Matches
/// backend/app/models/v2/document_field.py's DocumentFieldItem.
///
/// Fields read by OCR start as `needs_review`: until a person confirms
/// them, the AI is not shown their values (backend
/// app/services/field_extraction.py, render_for_model).
class DocumentField {
  const DocumentField({
    required this.id,
    required this.documentId,
    required this.kind,
    required this.role,
    required this.label,
    required this.rawText,
    required this.extractedValue,
    required this.value,
    required this.displayValue,
    required this.confidence,
    required this.source,
    required this.extractor,
    required this.roleBasis,
    required this.page,
    required this.issues,
    required this.status,
    required this.reviewedRole,
  });

  final String id;
  final String documentId;

  /// 'fir_number' | 'section' | 'date'
  final String kind;

  /// Dates only: 'arrest' | 'fir_registered' | 'hearing' | 'offence_date' |
  /// 'document_date'.
  final String? role;

  /// Human-readable, e.g. "arrest date".
  final String label;

  /// Exactly as read from the document; null when added by hand.
  final String? rawText;

  /// What the machine read (normalised). Never overwritten.
  final String? extractedValue;

  /// Current value — the reviewer's correction, if any.
  final String? value;
  final String displayValue;

  /// 0-100: the weakest word in the field.
  final double confidence;

  /// Where the text came from: 'text_layer' | 'ocr' | 'manual'.
  final String source;

  /// What found it: 'form' | 'pattern' | 'llm' | 'manual'.
  final String extractor;

  /// Why a date has its role: 'form_label' | 'keyword_near' (strong),
  /// 'keyword_far' | 'doc_type' | 'llm' (weak), 'reviewer'.
  final String? roleBasis;
  final int? page;
  final List<FieldIssue> issues;

  /// 'auto_accepted' | 'needs_review' | 'confirmed' | 'rejected'
  final String status;
  final String? reviewedRole;

  bool get needsReview => status == 'needs_review';
  bool get isScanned => source == 'ocr';
  bool get isManual => extractor == 'manual';
  bool get foundByAi => extractor == 'llm';
  bool get wasCorrected =>
      status == 'confirmed' && value != null && value != extractedValue;

  factory DocumentField.fromApi(Map<String, dynamic> json) {
    return DocumentField(
      id: json['id'] as String,
      documentId: json['documentId'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      role: json['role'] as String?,
      label: json['label'] as String? ?? '',
      rawText: json['rawText'] as String?,
      extractedValue: json['extractedValue'] as String?,
      value: json['value'] as String?,
      displayValue: json['displayValue'] as String? ?? '',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      source: json['source'] as String? ?? 'text_layer',
      extractor: json['extractor'] as String? ?? 'pattern',
      roleBasis: json['roleBasis'] as String?,
      page: json['page'] as int?,
      issues: (json['issues'] as List<dynamic>? ?? const [])
          .map((e) => FieldIssue.fromApi(Map<String, dynamic>.from(e as Map)))
          .toList(),
      status: json['status'] as String? ?? 'needs_review',
      reviewedRole: json['reviewedRole'] as String?,
    );
  }
}

class FieldIssue {
  const FieldIssue({
    required this.code,
    required this.message,
    required this.blocking,
  });

  final String code;
  final String message;
  final bool blocking;

  factory FieldIssue.fromApi(Map<String, dynamic> json) {
    return FieldIssue(
      code: json['code'] as String? ?? '',
      message: json['message'] as String? ?? '',
      blocking: json['blocking'] as bool? ?? false,
    );
  }
}

/// A fact this document type should contain that wasn't found — shown as
/// an "add it" prompt rather than failing silently.
class MissingFact {
  const MissingFact({required this.kind, required this.role, required this.label});

  final String kind;
  final String? role;
  final String label;

  factory MissingFact.fromApi(Map<String, dynamic> json) {
    return MissingFact(
      kind: json['kind'] as String? ?? '',
      role: json['role'] as String?,
      label: json['label'] as String? ?? '',
    );
  }
}

class FindFactsResult {
  const FindFactsResult({
    required this.added,
    required this.suggested,
    required this.dropped,
    required this.unparseableReply,
  });

  final List<DocumentField> added;
  final int suggested;
  final int dropped;
  final bool unparseableReply;

  factory FindFactsResult.fromApi(Map<String, dynamic> json) {
    return FindFactsResult(
      added: (json['added'] as List<dynamic>? ?? const [])
          .map((e) => DocumentField.fromApi(Map<String, dynamic>.from(e as Map)))
          .toList(),
      suggested: json['suggested'] as int? ?? 0,
      dropped: json['dropped'] as int? ?? 0,
      unparseableReply: json['unparseableReply'] as bool? ?? false,
    );
  }
}
