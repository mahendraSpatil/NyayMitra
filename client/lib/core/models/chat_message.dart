enum ChatRole { user, assistant }

/// Never defaults to verified: an unrecognized or missing value must read
/// as unverified, per NyayMitra.md's fail-closed rule for anything reaching a
/// user before it has passed verification.
enum VerificationStatus { verified, unverified }

/// Which of a case's documents were in scope for a reply — not the same
/// thing as citedSections (specific statute sections, once law-grounding
/// verification exists). This is "what was in context," independent of
/// whether any claim was verified against it. Backend-added ahead of
/// document_faithfulness verification existing, since that check will
/// need to know what was in scope to check claims against.
class CitedDocument {
  const CitedDocument({required this.docId, required this.docType});

  final String docId;
  final String docType;

  factory CitedDocument.fromMap(Map<String, dynamic> map) {
    return CitedDocument(
      docId: map['docId'] as String? ?? '',
      docType: map['docType'] as String? ?? '',
    );
  }
}

class ChatMessage {
  final String id;
  final ChatRole role;
  final String text;
  final String? language;
  final VerificationStatus verificationStatus;
  final List<String> citedSections;
  final List<CitedDocument> citedDocuments;

  const ChatMessage({
    required this.id,
    this.role = ChatRole.user,
    this.text = '',
    this.language,
    this.verificationStatus = VerificationStatus.unverified,
    this.citedSections = const [],
    this.citedDocuments = const [],
  });
}
