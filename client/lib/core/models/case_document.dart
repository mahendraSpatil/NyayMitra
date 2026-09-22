enum DocType {
  fir,
  chargeSheet,
  bailApplication,
  bailOrder,
  remandOrder,
  unknown,
}

/// Public wrapper so callers with just the raw API string (e.g. a chat
/// reply's CitedDocument) can get a human label without re-implementing
/// this mapping — _docTypeFromString itself stays private since
/// CaseDocument.fromApi is the normal entry point.
DocType docTypeFromApiValue(String? value) => _docTypeFromString(value);

DocType _docTypeFromString(String? value) {
  switch (value) {
    case 'fir':
      return DocType.fir;
    case 'charge_sheet':
      return DocType.chargeSheet;
    case 'bail_application':
      return DocType.bailApplication;
    case 'bail_order':
      return DocType.bailOrder;
    case 'remand_order':
      return DocType.remandOrder;
    default:
      return DocType.unknown;
  }
}

String _docTypeToString(DocType type) {
  switch (type) {
    case DocType.fir:
      return 'fir';
    case DocType.chargeSheet:
      return 'charge_sheet';
    case DocType.bailApplication:
      return 'bail_application';
    case DocType.bailOrder:
      return 'bail_order';
    case DocType.remandOrder:
      return 'remand_order';
    case DocType.unknown:
      return 'unknown';
  }
}

/// Human-readable labels, kept separate from _docTypeToString (the API
/// field value) since UI copy and storage keys change for different
/// reasons.
extension DocTypeLabel on DocType {
  String get label {
    switch (this) {
      case DocType.fir:
        return 'FIR';
      case DocType.chargeSheet:
        return 'Charge Sheet';
      case DocType.bailApplication:
        return 'Bail Application';
      case DocType.bailOrder:
        return 'Bail Order';
      case DocType.remandOrder:
        return 'Remand Order';
      case DocType.unknown:
        return 'Document';
    }
  }

  /// The raw API field value — same mapping _docTypeToString uses,
  /// exposed publicly for callers outside this model (the upload flow
  /// needs to send this to the backend) rather than duplicating the
  /// switch statement.
  String get apiValue => _docTypeToString(this);
}

class Statute {
  final String code;
  final String? bnsEquivalent;

  const Statute({required this.code, this.bnsEquivalent});

  factory Statute.fromMap(Map<String, dynamic> map) {
    return Statute(
      code: map['code'] as String? ?? '',
      bnsEquivalent: map['bnsEquivalent'] as String?,
    );
  }
}

/// Matches cases/{caseId}/documents/{docId}.
class CaseDocument {
  final String id;
  final DocType docType;
  final String? storagePath;
  final String? uploadedBy;
  final DateTime? uploadedAt;
  final String? ocrStatus;
  final String? rawText;
  final List<Statute> statutes;

  const CaseDocument({
    required this.id,
    this.docType = DocType.unknown,
    this.storagePath,
    this.uploadedBy,
    this.uploadedAt,
    this.ocrStatus,
    this.rawText,
    this.statutes = const [],
  });

  /// GET /api/v2/cases/{caseId}/documents — field names match
  /// app/models/v2/document.py's DocumentItem exactly.
  factory CaseDocument.fromApi(Map<String, dynamic> json) {
    final rawStatutes = json['statutes'] as List<dynamic>? ?? const [];
    final uploadedAtValue = json['uploadedAt'] as String?;
    return CaseDocument(
      id: json['id'] as String,
      docType: _docTypeFromString(json['docType'] as String?),
      storagePath: json['storagePath'] as String?,
      uploadedBy: json['uploadedBy'] as String?,
      uploadedAt: uploadedAtValue == null
          ? null
          : DateTime.tryParse(uploadedAtValue),
      ocrStatus: json['ocrStatus'] as String?,
      rawText: json['rawText'] as String?,
      statutes: rawStatutes
          .map((e) => Statute.fromMap(Map<String, dynamic>.from(e as Map)))
          .toList(),
    );
  }
}
