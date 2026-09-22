import 'dart:convert';

import '../../core/models/chat_message.dart' show CitedDocument;
import '../../core/services/api_client.dart';

/// One assistant reply from POST /chat, or the outcome of a failed call.
class ChatReply {
  const ChatReply({
    required this.text,
    required this.verified,
    this.citedSections = const [],
    this.citedDocuments = const [],
  });

  final String text;
  final bool verified;
  final List<String> citedSections;
  final List<CitedDocument> citedDocuments;
}

class ChatService {
  final _apiClient = ApiClient.instance;

  /// [caseId] is optional: the chatbot FAB is still portal-home-level for
  /// Advocate/NGO (no single "current case" there), so only callers that
  /// do have one unambiguous case in scope (Family Portal) pass it.
  Future<ChatReply> sendMessage(String message, {String? caseId}) async {
    final response = await _apiClient.post(
      '/chat',
      body: {'message': message, if (caseId != null) 'caseId': caseId},
    );

    if (response.statusCode != 200) {
      throw ChatHttpException(
        'Chat request failed (${response.statusCode}): ${response.body}',
      );
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return ChatReply(
      text: json['text'] as String? ?? '',
      verified: json['verificationStatus'] == 'verified',
      citedSections: (json['citedSections'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
      citedDocuments: (json['citedDocuments'] as List<dynamic>? ?? const [])
          .map((e) => CitedDocument.fromMap(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ChatHttpException implements Exception {
  ChatHttpException(this.message);
  final String message;

  @override
  String toString() => message;
}
