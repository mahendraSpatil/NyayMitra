import 'dart:async';
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

  // Above the backend's own LLM_TIMEOUT_S (120s default,
  // backend/app/config.py) — this must never fire first and hide a real
  // 503/response the server was about to send anyway.
  static const _requestTimeout = Duration(seconds: 150);

  /// [caseId] is optional: the chatbot FAB is still portal-home-level for
  /// Advocate/NGO (no single "current case" there), so only callers that
  /// do have one unambiguous case in scope (Family Portal) pass it.
  Future<ChatReply> sendMessage(String message, {String? caseId}) async {
    final response = await _apiClient
        .post(
          '/chat',
          body: {'message': message, if (caseId != null) 'caseId': caseId},
        )
        .timeout(
          _requestTimeout,
          onTimeout: () => throw ChatHttpException(
            'Chat request took too long and was cancelled.',
          ),
        );

    if (response.statusCode == 503) {
      // Distinct from the generic case below so the UI can show the
      // specific "offline/starting up" message instead of a raw HTTP
      // error — this is the backend's honest signal that the local
      // model is unreachable, never a fallback to a different one
      // (backend/app/routers/v2/chat.py).
      throw ChatUnavailableException();
    }
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

/// The local model is offline/unreachable right now (a 503 from
/// /chat) — never thrown for any other status, and never followed by a
/// silent retry against a different provider.
class ChatUnavailableException implements Exception {
  @override
  String toString() =>
      'NyayMitra AI is starting up or offline. Please try again in a minute.';
}
