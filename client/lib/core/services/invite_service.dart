import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

/// TODO: same dev-only placeholder as the other *_service.dart files'
/// _baseUrl — needs real build-time configuration before this reaches
/// any device but this machine.
const _baseUrl = 'http://localhost:8000';

class InviteServiceException implements Exception {
  InviteServiceException(this.message);

  final String message;

  @override
  String toString() => message;
}

class GeneratedInvite {
  const GeneratedInvite({required this.code, required this.expiresAt});

  final String code;
  final DateTime expiresAt;
}

/// Invite generation and redemption both go through the backend —
/// firestore.rules denies all client access to invites/ outright, so
/// there is no direct-Firestore path here the way there is for reads
/// elsewhere in this app.
class InviteService {
  Future<Map<String, String>> _authHeaders() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      throw StateError('InviteService called with no signed-in user');
    }
    final token = await user.getIdToken();
    return {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };
  }

  /// Only a case manager can call this successfully — the backend
  /// re-checks that independently, this is not a client-side gate.
  Future<GeneratedInvite> generateInvite(String caseId) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/cases/$caseId/invites'),
      headers: await _authHeaders(),
    );
    if (response.statusCode != 200) {
      throw InviteServiceException(_readableError(response));
    }
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return GeneratedInvite(
      code: json['code'] as String,
      expiresAt: DateTime.parse(json['expiresAt'] as String),
    );
  }

  /// Returns the caseId the code granted access to.
  Future<String> redeemInvite(String code) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/invites/redeem'),
      headers: await _authHeaders(),
      body: jsonEncode({'code': code}),
    );
    if (response.statusCode != 200) {
      throw InviteServiceException(_readableError(response));
    }
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['caseId'] as String;
  }

  String _readableError(http.Response response) {
    try {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return json['detail']?.toString() ?? response.body;
    } catch (_) {
      return 'Request failed (${response.statusCode}).';
    }
  }
}
