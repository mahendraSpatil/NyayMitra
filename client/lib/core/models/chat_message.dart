import 'package:cloud_firestore/cloud_firestore.dart';

enum ChatRole { user, assistant }

ChatRole _chatRoleFromString(String? value) {
  return value == 'assistant' ? ChatRole.assistant : ChatRole.user;
}

String _chatRoleToString(ChatRole role) {
  return role == ChatRole.assistant ? 'assistant' : 'user';
}

/// Never defaults to verified: an unrecognized or missing value must read
/// as unverified, per CLAUDE.md's fail-closed rule for anything reaching a
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

/// Matches cases/{caseId}/messages/{messageId}.
class ChatMessage {
  final String id;
  final ChatRole role;
  final String text;
  final String? language;
  final VerificationStatus verificationStatus;
  final List<String> citedSections;

  const ChatMessage({
    required this.id,
    this.role = ChatRole.user,
    this.text = '',
    this.language,
    this.verificationStatus = VerificationStatus.unverified,
    this.citedSections = const [],
  });

  factory ChatMessage.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const {};
    return ChatMessage(
      id: doc.id,
      role: _chatRoleFromString(data['role'] as String?),
      text: data['text'] as String? ?? '',
      language: data['language'] as String?,
      verificationStatus:
          _verificationStatusFromString(data['verificationStatus'] as String?),
      citedSections: (data['citedSections'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
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
    };
  }
}
