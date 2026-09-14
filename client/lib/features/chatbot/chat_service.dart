import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

/// One assistant reply from POST /chat, or the outcome of a failed call.
class ChatReply {
  const ChatReply({required this.text, required this.verified, this.citedSections = const []});

  final String text;
  final bool verified;
  final List<String> citedSections;
}

/// TODO: this base URL is a dev-only placeholder. Before this ships to any
/// real device it needs real configuration (build-time --dart-define or
/// similar), not a hardcoded localhost address — a phone can't reach
/// "localhost" and mean this machine's backend.
const _baseUrl = 'http://localhost:8000';

class ChatService {
  Future<ChatReply> sendMessage(String message) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      throw StateError('sendMessage called with no signed-in user');
    }

    final token = await user.getIdToken();
    final response = await http.post(
      Uri.parse('$_baseUrl/chat'),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'message': message}),
    );

    if (response.statusCode != 200) {
      throw ChatHttpException('Chat request failed (${response.statusCode}): ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return ChatReply(
      text: json['text'] as String? ?? '',
      verified: json['verificationStatus'] == 'verified',
      citedSections: (json['citedSections'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
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
