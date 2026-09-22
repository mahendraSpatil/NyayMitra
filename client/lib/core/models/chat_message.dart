import 'package:cloud_firestore/cloud_firestore.dart';

enum ChatRole { user, assistant }

ChatRole _chatRoleFromString(String? value) {
  return value == 'assistant' ? ChatRole.assistant : ChatRole.user;
}

String _chatRoleToString(ChatRole role) {
  return role == ChatRole.assistant ? 'assistant' : 'user';
}

/// Never defaults to verified: an unrecognized or missing value must read
/// as unverified, per NyayMitra.md's fail-closed rule for anything reaching a
/// user before it has passed verification.
enum VerificationStatus { verified, unverified }

VerificationStatus _verificationStatusFromString(String? value) {
  return value == 'verified'
      ? VerificationStatus.verified
      : VerificationStatus.unverified;
}

String _verificationStatusToString(VerificationStatus status) {
  return status == VerificationStatus.verified ? 'verified' : 'unverified';
}

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

  Map<String, dynamic> toMap() => {'docId': docId, 'docType': docType};
}

/// Matches cases/{caseId}/messages/{messageId}.
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

  factory ChatMessage.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? const {};
    final rawCitedDocuments =
        data['citedDocuments'] as List<dynamic>? ?? const [];
    return ChatMessage(
      id: doc.id,
      role: _chatRoleFromString(data['role'] as String?),
      text: data['text'] as String? ?? '',
      language: data['language'] as String?,
      verificationStatus: _verificationStatusFromString(
        data['verificationStatus'] as String?,
      ),
      citedSections: (data['citedSections'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
      citedDocuments: rawCitedDocuments
          .map(
            (e) => CitedDocument.fromMap(Map<String, dynamic>.from(e as Map)),
          )
          .toList(),
    );
  }

  Map<String, dynamic> toFirestore() {
    return {
      'role': _chatRoleToString(role),
      'text': text,
      'language': language,
      'verificationStatus': _verificationStatusToString(verificationStatus),
      'citedSections': citedSections,
      'citedDocuments': citedDocuments.map((e) => e.toMap()).toList(),
    };
  }
}
